// ASkyCourseMode: the Course Builder's director (see SkyCourse.h and Design/CourseBuilder.md).
// It reads the build area (Content/SkyCity/Data/course_area.json), lays the flat build pad, spawns the track, the race and
// the builder pawn, keeps the course (validated, baked, undoable, autosaved), reads and writes course files, hands the
// wheel between the builder and the player's car for test drives, and runs the optional local MCP server.
// The editor itself (camera, cursor, palette, menus) is ASkyCourseBuilderPawn in SkyCourseBuilder.cpp.
#include "SkyCourse.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "SkysterCar.h"

DEFINE_LOG_CATEGORY_STATIC(LogSkyCourseMode, Log, All);

void SkyCourseBuilderToast(ASkyCourseBuilderPawn* Pawn, const FString& Title, const FString& Sub, bool bBad);   // SkyCourseBuilder.cpp

/** What the director keeps beside the course: the car, where it parks, the area file, the pad, input edges. */
struct FSkyCourseModeState
{
	TWeakObjectPtr<ASkysterCar> Car;
	FVector ParkUE = FVector::ZeroVector;      // where the car waits while you build (Unreal cm)
	double ParkYaw = 0;
	double ParkAt = -1;                        // world time to put the car back at ParkUE (after the camera has flown home)
	bool bStarted = false;
	// the build area (course_area.json)
	double GroundZ = 10.75;
	FVector Start = FVector(1640, -3340, 11.25);
	double Yaw = 0;
	double PadMargin = 100, Grid = 50;
	bool bPad = true, bAreaFromFile = false, bPadFlip = false;   // bPadFlip: course_area.json "pad_flip" turns the pad's triangles over (a test switch)
	// the pad
	TWeakObjectPtr<UProceduralMeshComponent> Pad;
	int32 PadVerts = 0, PadRingMisses = 0, PadSamples = 0;
	double PadMs = 0, PadTerrainMin = 0, PadTerrainMax = 0;
	// input edges while driving (Y or T back to building)
	TMap<FKey, bool> Prev;
	double LastCarSim = -1;
	int32 FrozenFrames = 0;
	double LastBakeMs = 0;
};

// ============================================================================================ the build area

static void LoadArea(FSkyCourseModeState& S, FBox& Area)
{
	// the numbers in course_area.json, kept here too in case the file isn't there
	double MinX = 1580, MinY = -3640, MaxX = 2180, MaxY = -3040;
	FString Text;
	TSharedPtr<FJsonObject> Obj;
	const FString Path = FPaths::ProjectContentDir() / TEXT("SkyCity/Data/course_area.json");
	if (FFileHelper::LoadFileToString(Text, *Path) && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Obj) && Obj.IsValid())
	{
		auto Nums = [&Obj](const TCHAR* Key, TArray<double>& Out)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			if (!Obj->TryGetArrayField(Key, A)) return false;
			for (const TSharedPtr<FJsonValue>& V : *A) Out.Add(V->AsNumber());
			return true;
		};
		TArray<double> Mn, Mx, St;
		if (Nums(TEXT("min"), Mn) && Mn.Num() >= 2) { MinX = Mn[0]; MinY = Mn[1]; }
		if (Nums(TEXT("max"), Mx) && Mx.Num() >= 2) { MaxX = Mx[0]; MaxY = Mx[1]; }
		Obj->TryGetNumberField(TEXT("ground_z"), S.GroundZ);
		if (Nums(TEXT("start"), St) && St.Num() >= 3) S.Start = FVector(St[0], St[1], St[2]);
		Obj->TryGetNumberField(TEXT("yaw"), S.Yaw);
		Obj->TryGetBoolField(TEXT("pad"), S.bPad);
		Obj->TryGetBoolField(TEXT("pad_flip"), S.bPadFlip);
		Obj->TryGetNumberField(TEXT("pad_margin"), S.PadMargin);
		Obj->TryGetNumberField(TEXT("grid"), S.Grid);
		S.bAreaFromFile = true;
	}
	else
	{
		UE_LOG(LogSkyCourseMode, Warning, TEXT("course_area.json not found or unreadable at %s: using the built-in area"), *Path);
	}
	if (MaxX < MinX) Swap(MinX, MaxX);
	if (MaxY < MinY) Swap(MinY, MaxY);
	S.Start.X = FMath::Clamp(S.Start.X, MinX + 40.0, MaxX - 40.0);
	S.Start.Y = FMath::Clamp(S.Start.Y, MinY + 40.0, MaxY - 40.0);
	Area = FBox(FVector(MinX, MinY, S.GroundZ), FVector(MaxX, MaxY, S.GroundZ + 400.0));
}

namespace
{
	// triangles and quads facing up in Unreal space. Unreal's front face is the one where (b - a) x (c - a) points AWAY from the viewer
	// (checked in the editor: the other way round the pad was culled from above). bFlip turns them over.
	struct FPadBuf
	{
		TArray<FVector> V, N;
		TArray<int32> T;
		TArray<FVector2D> UV;
		bool bFlip = false;
		int32 Add(const FVector& P, const FVector& Nrm, const FVector2D& Uv) { V.Add(P); N.Add(Nrm); UV.Add(Uv); return V.Num() - 1; }
		void Tri(int32 A, int32 B, int32 C)
		{
			if ((FVector::CrossProduct(V[B] - V[A], V[C] - V[A]).Z > 0) != bFlip) Swap(B, C);
			T.Add(A); T.Add(B); T.Add(C);
		}
		// both ways round, for thin painted strips that must be seen from either side
		void Tri2(int32 A, int32 B, int32 C) { T.Add(A); T.Add(B); T.Add(C); T.Add(A); T.Add(C); T.Add(B); }
		// a flat strip between two course points (m), Width wide, at height Z
		void Strip(const FVector2D& A, const FVector2D& B, double Width, double Z)
		{
			const FVector2D D = (B - A).GetSafeNormal(), Nn(-D.Y, D.X), O = Nn * Width * 0.5;
			const FVector Up(0, 0, 1);
			const int32 I0 = Add(SkyCourse::ToUE(FVector(A.X - O.X, A.Y - O.Y, Z)), Up, FVector2D(0, 0));
			const int32 I1 = Add(SkyCourse::ToUE(FVector(B.X - O.X, B.Y - O.Y, Z)), Up, FVector2D(1, 0));
			const int32 I2 = Add(SkyCourse::ToUE(FVector(B.X + O.X, B.Y + O.Y, Z)), Up, FVector2D(1, 1));
			const int32 I3 = Add(SkyCourse::ToUE(FVector(A.X + O.X, A.Y + O.Y, Z)), Up, FVector2D(0, 1));
			Tri2(I0, I1, I2);
			Tri2(I0, I2, I3);
		}
	};
}

// The terrain round the build area rolls by about 5 m, so a flat pad (a plane at ground_z) covers the area and eases down
// to the terrain over PadMargin m. Ring heights come from traces at BeginPlay, so the pad follows whatever the map holds.
static void BuildPad(AActor* Owner, FSkyCourseModeState& S, const FBox& Area)
{
	UWorld* World = Owner->GetWorld();
	if (!World || !S.bPad) return;
	const double T0 = FPlatformTime::Seconds();
	const double X0 = Area.Min.X, X1 = Area.Max.X, Y0 = Area.Min.Y, Y1 = Area.Max.Y;
	const double M = FMath::Max(0.0, S.PadMargin), G = S.GroundZ;
	const double Step = 20.0;
	const double LX0 = X0 - M, LX1 = X1 + M, LY0 = Y0 - M, LY1 = Y1 + M;
	const int32 NX = FMath::Max(1, FMath::CeilToInt((LX1 - LX0) / Step)), NY = FMath::Max(1, FMath::CeilToInt((LY1 - LY0) / Step));
	FCollisionQueryParams Q(SCENE_QUERY_STAT(SkyCoursePad), true);
	auto Terrain = [&](double X, double Y, bool& bHit)
	{
		FHitResult Hit;
		bHit = World->LineTraceSingleByChannel(Hit, SkyCourse::ToUE(FVector(X, Y, G + 80.0)), SkyCourse::ToUE(FVector(X, Y, G - 80.0)), ECC_Visibility, Q);
		return bHit ? Hit.ImpactPoint.Z / 100.0 : G - 4.0;
	};
	// does the terrain stay under the pad inside the area? (a few samples, for the log and the test state)
	S.PadTerrainMin = 1e9; S.PadTerrainMax = -1e9; S.PadSamples = 0;
	for (int32 i = 0; i <= 8; ++i)
		for (int32 j = 0; j <= 8; ++j)
		{
			bool bHit;
			const double H = Terrain(X0 + (X1 - X0) * i / 8.0, Y0 + (Y1 - Y0) * j / 8.0, bHit);
			if (!bHit) continue;
			++S.PadSamples;
			S.PadTerrainMin = FMath::Min(S.PadTerrainMin, H);
			S.PadTerrainMax = FMath::Max(S.PadTerrainMax, H);
		}
	if (S.PadSamples > 0 && S.PadTerrainMax > G + 0.05)
		UE_LOG(LogSkyCourseMode, Warning, TEXT("build pad: terrain reaches %.2f m, above ground_z %.2f m: it will poke through the pad"), S.PadTerrainMax, G);

	// the lattice heights
	TArray<double> Z;
	Z.SetNumUninitialized((NX + 1) * (NY + 1));
	S.PadRingMisses = 0;
	for (int32 j = 0; j <= NY; ++j)
		for (int32 i = 0; i <= NX; ++i)
		{
			const double X = LX0 + (LX1 - LX0) * i / NX, Y = LY0 + (LY1 - LY0) * j / NY;
			const double Dx = FMath::Max3(X0 - X, 0.0, X - X1), Dy = FMath::Max3(Y0 - Y, 0.0, Y - Y1);
			const double Dist = FMath::Sqrt(Dx * Dx + Dy * Dy);
			double H = G;
			if (Dist > 1e-6)
			{
				bool bHit;
				const double Ter = Terrain(X, Y, bHit) + 0.15;
				if (!bHit) ++S.PadRingMisses;
				const double T = M > 0 ? FMath::Clamp(Dist / M, 0.0, 1.0) : 1.0;
				H = FMath::Max(FMath::Lerp(G, Ter, T * T * (3.0 - 2.0 * T)), Ter);
			}
			Z[j * (NX + 1) + i] = H;
		}
	FPadBuf B;
	B.bFlip = S.bPadFlip;
	auto ZAt = [&](int32 i, int32 j) { return Z[FMath::Clamp(j, 0, NY) * (NX + 1) + FMath::Clamp(i, 0, NX)]; };
	const double Sx = (LX1 - LX0) / NX, Sy = (LY1 - LY0) / NY;
	for (int32 j = 0; j <= NY; ++j)
		for (int32 i = 0; i <= NX; ++i)
		{
			const double X = LX0 + Sx * i, Y = LY0 + Sy * j;
			const double Dzx = (ZAt(i + 1, j) - ZAt(i - 1, j)) / (2 * Sx), Dzy = (ZAt(i, j + 1) - ZAt(i, j - 1)) / (2 * Sy);
			const FVector Nrm = SkyCourse::DirToUE(FVector(-Dzx, -Dzy, 1).GetSafeNormal());
			B.Add(SkyCourse::ToUE(FVector(X, Y, ZAt(i, j))), Nrm, FVector2D(X / 20.0, Y / 20.0));
		}
	for (int32 j = 0; j < NY; ++j)
		for (int32 i = 0; i < NX; ++i)
		{
			const int32 A = j * (NX + 1) + i, Bv = A + 1, C = A + NX + 2, D = A + NX + 1;
			B.Tri(A, Bv, C);
			B.Tri(A, C, D);
		}
	FPadBuf Grid;
	if (S.Grid >= 5.0)
	{
		for (double X = X0; X <= X1 + 0.01; X += S.Grid) Grid.Strip(FVector2D(X, Y0), FVector2D(X, Y1), 0.5, G + 0.03);
		for (double Y = Y0; Y <= Y1 + 0.01; Y += S.Grid) Grid.Strip(FVector2D(X0, Y), FVector2D(X1, Y), 0.5, G + 0.03);
	}
	FPadBuf Edge;
	const double In = 1.6, W = 3.0;
	Edge.Strip(FVector2D(X0, Y0 + In), FVector2D(X1, Y0 + In), W, G + 0.05);
	Edge.Strip(FVector2D(X0, Y1 - In), FVector2D(X1, Y1 - In), W, G + 0.05);
	Edge.Strip(FVector2D(X0 + In, Y0), FVector2D(X0 + In, Y1), W, G + 0.05);
	Edge.Strip(FVector2D(X1 - In, Y0), FVector2D(X1 - In, Y1), W, G + 0.05);

	UProceduralMeshComponent* Pad = NewObject<UProceduralMeshComponent>(Owner, TEXT("BuildPad"));
	Pad->bUseComplexAsSimpleCollision = true;
	Pad->SetupAttachment(Owner->GetRootComponent());
	Pad->RegisterComponent();
	Pad->SetWorldLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);
	const TArray<FColor> NoColors;
	const TArray<FProcMeshTangent> NoTangents;
	Pad->CreateMeshSection(0, B.V, B.T, B.N, B.UV, NoColors, NoTangents, true);
	if (Grid.T.Num() > 0) Pad->CreateMeshSection(1, Grid.V, Grid.T, Grid.N, Grid.UV, NoColors, NoTangents, false);
	Pad->CreateMeshSection(2, Edge.V, Edge.T, Edge.N, Edge.UV, NoColors, NoTangents, false);
	Pad->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Pad->SetCollisionResponseToAllChannels(ECR_Block);
	Pad->SetCastShadow(false);
	if (UMaterialInterface* M0 = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/McGregor/Materials/MI_SiteBerm.MI_SiteBerm"))) Pad->SetMaterial(0, M0);
	if (UMaterialInterface* M1 = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/McGregor/Materials/MI_LinePaint.MI_LinePaint"))) Pad->SetMaterial(1, M1);
	if (UMaterialInterface* M2 = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/McGregor/Materials/MI_LEDRed.MI_LEDRed")))
	{
		UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(M2, Owner);
		Mid->SetVectorParameterValue(TEXT("EmissiveColor"), FLinearColor(0.1f, 0.8f, 1.f));
		Pad->SetMaterial(2, Mid);
	}
	S.Pad = Pad;
	S.PadVerts = B.V.Num();
	S.PadMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	UE_LOG(LogSkyCourseMode, Log, TEXT("build pad: %d verts, area %.0f x %.0f m at z %.2f (terrain %.2f to %.2f m in the area, %d ring misses), %.1f ms"),
		B.V.Num(), X1 - X0, Y1 - Y0, G, S.PadTerrainMin, S.PadTerrainMax, S.PadRingMisses, S.PadMs);
}

// Course files are plain JSON in SkyCourse::CoursesDir(); Name is already a SafeName (or _autosave).
static bool WriteCourseFile(const FString& Name, const FSkyCourse& C)
{
	const FString Dir = SkyCourse::CoursesDir();
	IFileManager::Get().MakeDirectory(*Dir, true);
	return FFileHelper::SaveStringToFile(SkyCourse::Write(C), *(Dir / Name + TEXT(".json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

// ============================================================================================ the director

ASkyCourseMode::ASkyCourseMode()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	State = MakeShared<FSkyCourseModeState>();
}

ASkyCourseMode* ASkyCourseMode::Get(const UWorld* World)
{
	if (!World) return nullptr;
	TActorIterator<ASkyCourseMode> It(const_cast<UWorld*>(World));
	return It ? *It : nullptr;
}

double ASkyCourseMode::GroundZ() const { return State ? State->GroundZ : 0.0; }

FSkyCourse ASkyCourseMode::StarterCourse(const FVector* Near, double YawDeg) const
{
	FSkyCourse C;
	C.Name = TEXT("New Course");
	FVector P = State->Start;
	double Y = State->Yaw;
	if (Near)
	{
		P = *Near;
		Y = YawDeg;
		if (Area.IsValid)
		{
			P.X = FMath::Clamp(P.X, Area.Min.X + 40.0, Area.Max.X - 40.0);
			P.Y = FMath::Clamp(P.Y, Area.Min.Y + 40.0, Area.Max.Y - 40.0);
		}
		P.Z = State->GroundZ + 0.5;
	}
	C.Start = P;
	C.Yaw = Y;
	C.Lanes = SkyCourse::DefaultLanes;
	FSkyPiece Start;
	Start.Type = ESkyPiece::Start;
	FSkyPiece Straight = SkyCourse::DefaultPiece(ESkyPiece::Straight, C.Lanes);
	Straight.Type = ESkyPiece::Straight;
	Straight.Length = 60;
	C.Seqs[0].Pieces = { Start, Straight };
	return C;
}

const FSkyBaked& ASkyCourseMode::GetBaked() const
{
	static FSkyBaked Empty;
	return Track ? Track->GetBaked() : Empty;
}

void ASkyCourseMode::BeginPlay()
{
	Super::BeginPlay();
	UWorld* World = GetWorld();
	if (!World) return;
	LoadArea(*State, Area);
	UE_LOG(LogSkyCourseMode, Log, TEXT("Course Builder: area x %.0f..%.0f y %.0f..%.0f m, ground z %.2f (%s)"), Area.Min.X, Area.Max.X, Area.Min.Y, Area.Max.Y,
		State->GroundZ, State->bAreaFromFile ? TEXT("course_area.json") : TEXT("built in"));
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Track = World->SpawnActor<ASkyCourseTrack>(ASkyCourseTrack::StaticClass(), FTransform::Identity, P);
	Race = World->SpawnActor<ASkyCourseRace>(ASkyCourseRace::StaticClass(), FTransform::Identity, P);
	Builder = World->SpawnActor<ASkyCourseBuilderPawn>(ASkyCourseBuilderPawn::StaticClass(), SkyCourse::ToUE(State->Start), FRotator::ZeroRotator, P);
	if (Builder) Builder->Mode = this;
	BuildPad(this, *State, Area);
	GetCar();   // the player's car, found once

	// the course to start on: last session's autosave, else a new starter
	TArray<FString> Errors;
	bool bLoaded = false;
	FString Json;
	if (FFileHelper::LoadFileToString(Json, *(SkyCourse::CoursesDir() / TEXT("_autosave.json"))))
	{
		FSkyCourse Saved;
		TArray<FString> ParseErrors;
		if (SkyCourse::Parse(Json, Saved, ParseErrors) && SetCourse(Saved, Errors)) bLoaded = true;
		else UE_LOG(LogSkyCourseMode, Log, TEXT("autosave not used: %s"), ParseErrors.Num() > 0 ? *ParseErrors[0] : Errors.Num() > 0 ? *Errors[0] : TEXT("?"));
	}
	if (!bLoaded)
	{
		Errors.Reset();
		if (!SetCourse(StarterCourse(), Errors))
			UE_LOG(LogSkyCourseMode, Warning, TEXT("the starter course doesn't bake: %s"), Errors.Num() > 0 ? *Errors[0] : TEXT("?"));
	}
	UndoStack.Reset();   // the course you start on isn't an edit
	if (FParse::Param(FCommandLine::Get(), TEXT("SkyCourseMcp"))) SetMcpEnabled(true);
}

void ASkyCourseMode::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Mcp) { Mcp->Stop(); Mcp.Reset(); }
	if (bDriving && Race) Race->End();
	bDriving = false;
	Super::EndPlay(Reason);
}

void ASkyCourseMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TArray<TFunction<void()>> Work;
	{ FScopeLock L(&PendingLock); Work = MoveTemp(Pending); Pending.Reset(); }
	for (TFunction<void()>& W : Work) W();

	FSkyCourseModeState& S = *State;
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	ASkysterCar* Car = GetCar();
	// the first tick: the car has finished its own BeginPlay, so remember where it parks, then the builder takes the wheel
	if (!S.bStarted)
	{
		if (!PC || !Builder) return;
		if (Car) { S.ParkUE = Car->GetActorLocation(); S.ParkYaw = Car->GetActorRotation().Yaw; }
		PC->Possess(Builder);
		S.bStarted = true;
	}
	// the car waits at its parking spot while you build (after the camera has flown home from a test drive)
	if (S.ParkAt > 0 && GetWorld()->GetTimeSeconds() >= S.ParkAt)
	{
		S.ParkAt = -1;
		if (Car && !bDriving) Car->TestTeleport(S.ParkUE + FVector(0, 0, 50), (float)S.ParkYaw);
	}
	// Y (or T) in a test drive: back to building. Edges are tracked every frame so a Y still held from the editor can't bounce straight back.
	bool bBack = false;
	if (PC)
	{
		for (const FKey& K : { EKeys::Gamepad_FaceButton_Top, EKeys::T })
		{
			const bool bNow = PC->IsInputKeyDown(K);
			bool& Prev = S.Prev.FindOrAdd(K);
			if (bNow && !Prev) bBack = true;
			Prev = bNow;
		}
	}
	if (bDriving && Car)
	{
		// the car's Garage (Menu) stops its clock: Y belongs to the Garage then (its Y resets the challenges)
		if (FMath::IsNearlyEqual(Car->SimTime, S.LastCarSim, 1e-9)) ++S.FrozenFrames; else S.FrozenFrames = 0;
		S.LastCarSim = Car->SimTime;
		if (bBack && S.FrozenFrames < 2) StopTestDrive();
	}
	else S.FrozenFrames = 0;
}

// ============================================================================================ the course

bool ASkyCourseMode::SetCourse(const FSkyCourse& NewCourse, TArray<FString>& Errors)
{
	if (!Track) { Errors.Add(TEXT("the track isn't ready yet")); return false; }
	if (bDriving) { Errors.Add(TEXT("a race is running: stop it first (Y)")); return false; }
	const double T0 = FPlatformTime::Seconds();
	const FSkyBaked& B = Track->Build(NewCourse, Area);
	if (!B.bValid)
	{
		Errors = B.Errors;
		if (Errors.Num() == 0) Errors.Add(TEXT("the course isn't valid"));
		if (Course.Seqs.Num() > 0 && Course.Seqs[0].Pieces.Num() > 0) Track->Build(Course, Area);   // put the last good course back
		return false;
	}
	State->LastBakeMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	UndoStack.Add(Course);
	if (UndoStack.Num() > 50) UndoStack.RemoveAt(0);
	Course = NewCourse;
	++CourseRevision;
	WriteCourseFile(TEXT("_autosave"), Course);   // the next session picks up where this one stopped
	return true;
}

bool ASkyCourseMode::Edit(TFunctionRef<void(FSkyCourse&)> Change, TArray<FString>& Errors)
{
	FSkyCourse Trial = Course;
	Change(Trial);
	return SetCourse(Trial, Errors);
}

bool ASkyCourseMode::Undo()
{
	if (bDriving || !Track || UndoStack.Num() == 0) return false;
	const FSkyCourse Prev = UndoStack.Pop();
	const FSkyBaked& B = Track->Build(Prev, Area);
	if (!B.bValid)
	{
		Track->Build(Course, Area);   // it was valid when it went on the stack, so this shouldn't happen; keep what we have
		return false;
	}
	Course = Prev;
	++CourseRevision;
	WriteCourseFile(TEXT("_autosave"), Course);
	return true;
}

// ============================================================================================ files

TArray<FString> ASkyCourseMode::ListCourses() const
{
	TArray<FString> Files, Out;
	IFileManager::Get().FindFiles(Files, *(SkyCourse::CoursesDir() / TEXT("*.json")), true, false);
	for (const FString& F : Files)
	{
		const FString Name = FPaths::GetBaseFilename(F);
		if (Name.IsEmpty() || Name.StartsWith(TEXT("_"))) continue;   // _autosave and friends
		if (Name.EndsWith(TEXT(".times"))) continue;                   // the race's best-times file beside each course
		Out.Add(Name);
	}
	Out.Sort([](const FString& A, const FString& B) { return A.Compare(B, ESearchCase::IgnoreCase) < 0; });
	return Out;
}

bool ASkyCourseMode::SaveCourse(const FString& Name, FString& Error)
{
	const FString Safe = SkyCourse::SafeName(Name);
	if (Safe.IsEmpty()) { Error = TEXT("a course name needs letters or digits"); return false; }
	Course.Name = Safe;   // the file and the course agree on the name
	if (!WriteCourseFile(Safe, Course)) { Error = TEXT("couldn't write the file"); return false; }
	WriteCourseFile(TEXT("_autosave"), Course);
	++CourseRevision;
	return true;
}

bool ASkyCourseMode::LoadCourse(const FString& Name, FString& Error)
{
	const FString Safe = SkyCourse::SafeName(Name);
	if (Safe.IsEmpty()) { Error = TEXT("a course name needs letters or digits"); return false; }
	FString Json;
	if (!FFileHelper::LoadFileToString(Json, *(SkyCourse::CoursesDir() / Safe + TEXT(".json")))) { Error = FString::Printf(TEXT("no course called \"%s\""), *Safe); return false; }
	FSkyCourse Loaded;
	TArray<FString> Errors;
	if (!SkyCourse::Parse(Json, Loaded, Errors)) { Error = Errors.Num() > 0 ? Errors[0] : FString(TEXT("not a course file")); return false; }
	if (SetCourse(Loaded, Errors)) return true;
	// a course saved elsewhere starts somewhere else: try it from this area's start spot
	{
		FSkyCourse Moved = Loaded;
		Moved.Start = State->Start;
		Moved.Yaw = State->Yaw;
		TArray<FString> MovedErrors;
		if (SetCourse(Moved, MovedErrors)) { ShowToast(TEXT("Moved to the start spot"), TEXT("it didn't fit where it was saved")); return true; }
	}
	Error = Errors.Num() > 0 ? Errors[0] : FString(TEXT("the course doesn't fit the build area"));
	return false;
}

// ============================================================================================ driving

ASkysterCar* ASkyCourseMode::GetCar() const
{
	if (!State) return nullptr;
	if (ASkysterCar* C = State->Car.Get()) return C;
	UWorld* World = GetWorld();
	if (!World) return nullptr;
	ASkysterCar* Found = Cast<ASkysterCar>(UGameplayStatics::GetPlayerPawn(World, 0));
	if (!Found)
	{
		TActorIterator<ASkysterCar> It(World);
		if (It) Found = *It;
	}
	State->Car = Found;
	return Found;
}

void ASkyCourseMode::StartTestDrive(int32 Opponents)
{
	if (bDriving) return;
	ASkysterCar* Car = GetCar();
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	if (!Car || !PC || !Track || !Race) { ShowToast(TEXT("Can't start a test drive"), TEXT("no car in this world"), true); return; }
	if (!Track->GetBaked().bValid) { ShowToast(TEXT("Fix the course first"), TEXT("it doesn't bake"), true); return; }
	Opponents = Opponents < 0 ? Course.Opponents : Opponents;
	Opponents = FMath::Clamp(Opponents, 0, SkyCourse::MaxOpponents);
	State->ParkAt = -1;
	State->FrozenFrames = 0;
	State->LastCarSim = -1;
	bDriving = true;
	Track->ShowPreview(nullptr, FSkyFrame(), SkyCourse::DefaultLanes, true);
	PC->Possess(Car);
	PC->SetViewTargetWithBlend(Car, 0.7f, VTBlend_EaseInOut, 2.f);
	Race->Begin(Track, Course, Car, Opponents, Course.Skill);
}

void ASkyCourseMode::StopTestDrive()
{
	if (!bDriving) return;
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	if (Race) Race->End();
	bDriving = false;
	if (PC && Builder)
	{
		PC->Possess(Builder);
		PC->SetViewTargetWithBlend(Builder, 0.7f, VTBlend_EaseInOut, 2.f);   // the builder's camera is already back over the cursor
	}
	// the car goes back to its parking spot once the view has left it
	State->ParkAt = GetWorld()->GetTimeSeconds() + 0.9;
}

// ============================================================================================ the MCP server

bool ASkyCourseMode::SetMcpEnabled(bool bOn)
{
	if (bOn)
	{
		if (!Mcp) Mcp = MakeShared<FSkyCourseMcp>(this);
		if (!Mcp->IsRunning()) Mcp->Start();
		if (!Mcp->IsRunning())
		{
			Mcp.Reset();
			UE_LOG(LogSkyCourseMode, Warning, TEXT("the MCP server couldn't start on port %d"), SkyCourse::McpPort);
			return false;
		}
		UE_LOG(LogSkyCourseMode, Log, TEXT("the MCP server is listening at %s"), *Mcp->Url());
		return true;
	}
	if (Mcp) { Mcp->Stop(); Mcp.Reset(); }
	return false;
}

bool ASkyCourseMode::IsMcpEnabled() const { return Mcp.IsValid() && Mcp->IsRunning(); }

FString ASkyCourseMode::McpClient() const
{
	if (!IsMcpEnabled()) return FString();
	const FString N = Mcp->ClientName();
	// a client counts as connected while it has been heard from in the last 10 minutes (an idle chat stays open)
	if (N.IsEmpty() || Mcp->SecondsSinceClient() > 600.0) return FString();
	if (N.Equals(TEXT("claude-ai"), ESearchCase::IgnoreCase) || N.Contains(TEXT("Claude Desktop"))) return TEXT("Claude Desktop");
	if (N.Contains(TEXT("claude-code"), ESearchCase::IgnoreCase)) return TEXT("Claude Code");
	if (N.Contains(TEXT("cursor"), ESearchCase::IgnoreCase)) return TEXT("Cursor");
	return N;
}

void ASkyCourseMode::RunOnGameThread(TFunction<void()> Work)
{
	FScopeLock L(&PendingLock);
	Pending.Add(MoveTemp(Work));
}

// ============================================================================================ screen

void ASkyCourseMode::DrawHud(AHUD* Hud, UCanvas* Canvas, float S)
{
	// while driving: the race's HUD, then the builder's "Y: back to building" strip; while building: the editor
	if (bDriving && Race) Race->DrawHud(Hud, Canvas, S);
	if (Builder) Builder->DrawHud(Hud, Canvas, S);
}

void ASkyCourseMode::ShowToast(const FString& Title, const FString& Sub, bool bBad)
{
	if (Builder) SkyCourseBuilderToast(Builder, Title, Sub, bBad);
}

// ============================================================================================ test hooks

bool ASkyCourseMode::TestSetCourseJson(const FString& Json, FString& OutErrors)
{
	FSkyCourse C;
	TArray<FString> Errors;
	if (!SkyCourse::Parse(Json, C, Errors) || !SetCourse(C, Errors)) { OutErrors = FString::Join(Errors, TEXT("\n")); return false; }
	return true;
}

FString ASkyCourseMode::TestGetCourseJson() const { return SkyCourse::Write(Course); }

FString ASkyCourseMode::TestStateJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	auto Vec = [](const FVector& V) { TArray<TSharedPtr<FJsonValue>> A; A.Add(MakeShared<FJsonValueNumber>(V.X)); A.Add(MakeShared<FJsonValueNumber>(V.Y)); A.Add(MakeShared<FJsonValueNumber>(V.Z)); return A; };
	O->SetArrayField(TEXT("areaMin"), Vec(Area.Min));
	O->SetArrayField(TEXT("areaMax"), Vec(Area.Max));
	O->SetNumberField(TEXT("groundZ"), State->GroundZ);
	O->SetBoolField(TEXT("areaFromFile"), State->bAreaFromFile);
	O->SetBoolField(TEXT("driving"), bDriving);
	O->SetBoolField(TEXT("mcp"), IsMcpEnabled());
	O->SetNumberField(TEXT("revision"), CourseRevision);
	O->SetNumberField(TEXT("undoDepth"), UndoStack.Num());
	O->SetNumberField(TEXT("seqs"), Course.Seqs.Num());
	int32 Pieces = 0;
	for (const FSkySeq& S : Course.Seqs) Pieces += S.Pieces.Num();
	O->SetNumberField(TEXT("pieces"), Pieces);
	O->SetStringField(TEXT("name"), Course.Name);
	O->SetBoolField(TEXT("started"), State->bStarted);
	O->SetNumberField(TEXT("lastBakeMs"), State->LastBakeMs);
	const FSkyBaked& B = GetBaked();
	TSharedRef<FJsonObject> Bk = MakeShared<FJsonObject>();
	Bk->SetBoolField(TEXT("valid"), B.bValid);
	Bk->SetNumberField(TEXT("length"), B.Length);
	Bk->SetNumberField(TEXT("segments"), B.Segs.Num());
	TArray<TSharedPtr<FJsonValue>> Er;
	for (int32 i = 0; i < B.Errors.Num() && i < 5; ++i) Er.Add(MakeShared<FJsonValueString>(B.Errors[i]));
	Bk->SetArrayField(TEXT("errors"), Er);
	TArray<TSharedPtr<FJsonValue>> Wa;
	for (int32 i = 0; i < B.Warnings.Num() && i < 5; ++i) Wa.Add(MakeShared<FJsonValueString>(B.Warnings[i]));
	Bk->SetArrayField(TEXT("warnings"), Wa);
	O->SetObjectField(TEXT("baked"), Bk);
	TSharedRef<FJsonObject> Pd = MakeShared<FJsonObject>();
	Pd->SetBoolField(TEXT("built"), State->Pad.IsValid());
	Pd->SetNumberField(TEXT("verts"), State->PadVerts);
	Pd->SetNumberField(TEXT("ringMisses"), State->PadRingMisses);
	Pd->SetNumberField(TEXT("terrainMinInArea"), State->PadTerrainMin);
	Pd->SetNumberField(TEXT("terrainMaxInArea"), State->PadTerrainMax);
	Pd->SetNumberField(TEXT("samples"), State->PadSamples);
	Pd->SetNumberField(TEXT("ms"), State->PadMs);
	O->SetObjectField(TEXT("pad"), Pd);
	if (const ASkysterCar* Car = GetCar())
	{
		O->SetArrayField(TEXT("car"), Vec(SkyCourse::FromUE(Car->GetActorLocation())));
		O->SetBoolField(TEXT("carPossessed"), Car->GetController() != nullptr);
	}
	if (Builder) O->SetStringField(TEXT("builder"), Builder->TestStateJson());
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(O, W);
	return Out;
}
