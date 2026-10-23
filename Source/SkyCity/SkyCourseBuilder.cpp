// ASkyCourseBuilderPawn: the Course Builder's editor (see SkyCourse.h and Design/CourseBuilder.md, "Player experience").
// An orbit / top-down camera over a glowing cursor at the end of the sequence being edited, the piece palette, the fit
// test (bake the course with the piece added), splits and their branches, the course menu, the name box and the
// map list that stands in for the Garage while the car isn't possessed. SkyCourseBuilderHud.cpp draws all of it.
#include "SkyCourseBuilderImpl.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/Paths.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformProcess.h"
#include "ProceduralMeshComponent.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "SkysterCar.h"

DEFINE_LOG_CATEGORY_STATIC(LogSkyBuilder, Log, All);

using namespace SkyBuilder;

// ============================================================================================ pieces and settings

const ESkyPiece SkyBuilder::Palette[] = {
	ESkyPiece::Straight, ESkyPiece::Curve, ESkyPiece::Ramp, ESkyPiece::Jump, ESkyPiece::Loop, ESkyPiece::Corkscrew, ESkyPiece::WallRide,
	ESkyPiece::Booster, ESkyPiece::Lanes, ESkyPiece::Split, ESkyPiece::Checkpoint, ESkyPiece::Finish, ESkyPiece::Close };
static_assert(UE_ARRAY_COUNT(SkyBuilder::Palette) == SkyBuilder::NumPalette, "palette size");

void SkyBuilder::FieldsFor(ESkyPiece T, EF O[3])
{
	O[0] = O[1] = O[2] = EF::None;
	switch (T)
	{
	case ESkyPiece::Straight:  O[0] = EF::Length; break;
	case ESkyPiece::Curve:     O[0] = EF::Angle; O[1] = EF::Radius; O[2] = EF::Bank; break;
	case ESkyPiece::Ramp:      O[0] = EF::Length; O[1] = EF::Rise; break;
	case ESkyPiece::Jump:      O[0] = EF::Gap; O[1] = EF::Drop; break;
	case ESkyPiece::Loop:      O[0] = EF::Radius; O[1] = EF::Offset; break;
	case ESkyPiece::Corkscrew: O[0] = EF::Length; O[1] = EF::Turns; break;
	case ESkyPiece::WallRide:  O[0] = EF::Length; O[1] = EF::Side; break;
	case ESkyPiece::Booster:   O[0] = EF::Length; break;
	case ESkyPiece::Lanes:     O[0] = EF::Length; O[1] = EF::Lanes; O[2] = EF::Align; break;
	case ESkyPiece::Split:     O[0] = EF::Length; O[1] = EF::Branches; O[2] = EF::Gate; break;
	default: break;
	}
}

// the hard limits of Design/CourseBuilder.md and the steps the controls move by
FFieldInfo SkyBuilder::InfoFor(ESkyPiece T, EF F)
{
	switch (F)
	{
	case EF::Length:
		switch (T)
		{
		case ESkyPiece::Ramp: return { TEXT("LENGTH"), TEXT("m"), 5, 4, 150 };
		case ESkyPiece::Corkscrew: return { TEXT("LENGTH"), TEXT("m"), 5, 20, 260 };
		case ESkyPiece::WallRide: return { TEXT("LENGTH"), TEXT("m"), 5, 15, 150 };
		case ESkyPiece::Booster: return { TEXT("LENGTH"), TEXT("m"), 5, 4, 30 };
		case ESkyPiece::Lanes: return { TEXT("LENGTH"), TEXT("m"), 5, 10, 80 };
		case ESkyPiece::Split: return { TEXT("LENGTH"), TEXT("m"), 5, 15, 80 };
		default: return { TEXT("LENGTH"), TEXT("m"), 5, 2, 300 };
		}
	case EF::Angle:    return { TEXT("ANGLE"), TEXT("°"), 15, -270, 270 };
	case EF::Radius:   return T == ESkyPiece::Loop ? FFieldInfo{ TEXT("RADIUS"), TEXT("m"), 5, 6, 30 } : FFieldInfo{ TEXT("RADIUS"), TEXT("m"), 5, 8, 300 };
	case EF::Bank:     return { TEXT("BANK"), TEXT("°"), 5, -45, 45 };
	case EF::Rise:     return { TEXT("RISE"), TEXT("m"), 2, -60, 60 };
	case EF::Gap:      return { TEXT("GAP"), TEXT("m"), 2, 4, 80 };
	case EF::Drop:     return { TEXT("DROP"), TEXT("m"), 2, -30, 30 };
	case EF::Offset:   return { TEXT("OFFSET"), TEXT("m"), 1, 0, SkyCourse::MaxLanes * SkyCourse::MaxLaneWidth + 1 };
	case EF::Turns:    return { TEXT("TURNS"), TEXT(""), 0.5, 0.5, 2 };
	case EF::Side:     return { TEXT("SIDE"), TEXT(""), 1, -1, 1 };
	case EF::Lanes:    return { TEXT("LANES"), TEXT(""), 1, 1, 4 };
	case EF::Align:    return { TEXT("ALIGN"), TEXT(""), 1, -1, 1 };
	case EF::Branches: return { TEXT("BRANCHES"), TEXT(""), 1, 2, 4 };
	case EF::Gate:     return { TEXT("GATE"), TEXT(""), 1, 0, 2 };
	default:           return { TEXT(""), TEXT(""), 1, 0, 0 };
	}
}

double SkyBuilder::GetField(const FSkyPiece& P, EF F)
{
	switch (F)
	{
	case EF::Length: return P.Length;
	case EF::Angle: return P.Angle;
	case EF::Radius: return P.Radius;
	case EF::Bank: return P.Bank;
	case EF::Rise: return P.Rise;
	case EF::Gap: return P.Gap;
	case EF::Drop: return P.Drop;
	case EF::Offset: return P.Offset;
	case EF::Turns: return P.Turns;
	case EF::Side: return P.Side;
	case EF::Lanes: return P.Lanes;
	case EF::Align: return P.Align;
	case EF::Branches: return P.Branches.Num();
	case EF::Gate: return (double)(int32)P.Gate;
	default: return 0;
	}
}

void SkyBuilder::SetField(FSkyPiece& P, EF F, double V)
{
	switch (F)
	{
	case EF::Length: P.Length = V; break;
	case EF::Angle: P.Angle = V; break;
	case EF::Radius: P.Radius = V; break;
	case EF::Bank: P.Bank = V; break;
	case EF::Rise: P.Rise = V; break;
	case EF::Gap: P.Gap = V; break;
	case EF::Drop: P.Drop = V; break;
	case EF::Offset: P.Offset = V; break;
	case EF::Turns: P.Turns = V; break;
	case EF::Side: P.Side = V < 0 ? -1 : 1; break;
	case EF::Lanes: P.Lanes = FMath::RoundToInt(V); break;
	case EF::Align: P.Align = FMath::RoundToInt(V); break;
	case EF::Branches: P.Branches.SetNum(FMath::Clamp(FMath::RoundToInt(V), 2, SkyCourse::MaxBranches)); break;
	case EF::Gate: P.Gate = (ESkyGate)FMath::Clamp(FMath::RoundToInt(V), 0, 2); break;
	default: break;
	}
}

static FString Num(double V)
{
	return FMath::IsNearlyEqual(V, FMath::RoundToDouble(V), 0.001) ? FString::FromInt(FMath::RoundToInt(V)) : FString::Printf(TEXT("%.1f"), V);
}

FString SkyBuilder::FormatField(const FSkyPiece& P, EF F)
{
	const double V = GetField(P, F);
	switch (F)
	{
	case EF::Angle: return FString::Printf(TEXT("%s%s°"), V > 0 ? TEXT("+") : TEXT(""), *Num(V));
	case EF::Rise: case EF::Drop: return FString::Printf(TEXT("%s%s m"), V > 0 ? TEXT("+") : TEXT(""), *Num(V));
	case EF::Bank: return FString::Printf(TEXT("%s°"), *Num(V));
	case EF::Turns: return Num(V);
	case EF::Side: return P.Side > 0 ? TEXT("LEFT") : TEXT("RIGHT");
	case EF::Align: return P.Align < 0 ? TEXT("LEFT") : P.Align > 0 ? TEXT("RIGHT") : TEXT("CENTRE");
	case EF::Gate: return P.Gate == ESkyGate::Lights ? TEXT("LIGHTS") : P.Gate == ESkyGate::Wall ? TEXT("WALL") : TEXT("NONE");
	case EF::Lanes: case EF::Branches: return Num(V);
	case EF::None: return FString();
	default: return FString::Printf(TEXT("%s m"), *Num(V));
	}
}

// the next multiple of Step in a direction (so 2 -> 5 -> 10 and 60 -> 55 -> 50), kept inside the limits
static double StepSnap(double V, int32 Dir, double Step, double Lo, double Hi)
{
	const double R = V / Step, Rn = FMath::RoundToDouble(R);
	const double N = FMath::IsNearlyEqual(R, Rn, 1e-6) ? (Rn + Dir) * Step : (Dir > 0 ? FMath::CeilToDouble(R) : FMath::FloorToDouble(R)) * Step;
	return FMath::Clamp(N, Lo, Hi);
}

void SkyBuilder::AdjustField(FSkyPiece& P, EF F, int32 Dir)
{
	const FFieldInfo I = InfoFor(P.Type, F);
	double V = GetField(P, F);
	switch (F)
	{
	case EF::Side: V = -V; break;
	case EF::Align: V = V + Dir > 1 ? -1 : V + Dir < -1 ? 1 : V + Dir; break;
	case EF::Gate: V = V + Dir > 2 ? 0 : V + Dir < 0 ? 2 : V + Dir; break;
	default:
		V = StepSnap(V, Dir, I.Step, I.Lo, I.Hi);
		if (F == EF::Angle && FMath::Abs(V) < 1.0) V = Dir > 0 ? 15 : -15;   // a curve of 0 degrees is a straight
		break;
	}
	SetField(P, F, V);
}

FSkyPiece SkyBuilder::MakeDefault(ESkyPiece Type, int32 LanesHere)
{
	FSkyPiece P = SkyCourse::DefaultPiece(Type, LanesHere);
	P.Type = Type;
	LanesHere = FMath::Clamp(LanesHere, SkyCourse::MinLanes, SkyCourse::MaxLanes);
	// fill in what the geometry's defaults leave at zero, so the editor works against any model
	auto Fill = [](double& V, double Def, double Lo) { if (V < Lo) V = Def; };
	switch (Type)
	{
	case ESkyPiece::Straight: Fill(P.Length, 60, 2); break;
	case ESkyPiece::Curve: if (FMath::Abs(P.Angle) < 1) P.Angle = 90; Fill(P.Radius, 40, 8); break;
	case ESkyPiece::Ramp: Fill(P.Length, 30, 4); if (FMath::Abs(P.Rise) < 0.01) P.Rise = 8; break;
	case ESkyPiece::Jump: Fill(P.Gap, 20, 4); break;
	case ESkyPiece::Loop: Fill(P.Radius, 10, 6); P.Offset = FMath::Clamp(P.Offset > 0 ? P.Offset : SkyCourse::DefaultLaneWidth * LanesHere + 1.0, 0.0, SkyCourse::MaxLanes * SkyCourse::MaxLaneWidth + 1.0); break;
	case ESkyPiece::Corkscrew: Fill(P.Length, 60, 20); Fill(P.Turns, 1, 0.5); break;
	case ESkyPiece::WallRide: Fill(P.Length, 50, 15); if (P.Side == 0) P.Side = 1; break;
	case ESkyPiece::Booster: Fill(P.Length, 10, 4); break;
	case ESkyPiece::Lanes:
		Fill(P.Length, 25, 10);
		if (P.Lanes < 1 || P.Lanes == LanesHere) P.Lanes = LanesHere < SkyCourse::MaxLanes ? LanesHere + 1 : LanesHere - 1;
		break;
	case ESkyPiece::Split:
		Fill(P.Length, 30, 15);
		if (P.MergeLength < 15) P.MergeLength = 30;
		P.Gate = ESkyGate::Lights;
		break;
	default: break;
	}
	if (Type != ESkyPiece::Split) P.Branches.Reset();
	else FillBranches(P, LanesHere);
	return P;
}

const TCHAR* SkyBuilder::PieceLabel(ESkyPiece T)
{
	switch (T)
	{
	case ESkyPiece::Straight: return TEXT("STRAIGHT");
	case ESkyPiece::Curve: return TEXT("CURVE");
	case ESkyPiece::Ramp: return TEXT("RAMP");
	case ESkyPiece::Jump: return TEXT("JUMP");
	case ESkyPiece::Loop: return TEXT("LOOP");
	case ESkyPiece::Corkscrew: return TEXT("CORKSCREW");
	case ESkyPiece::WallRide: return TEXT("WALL RIDE");
	case ESkyPiece::Booster: return TEXT("BOOSTER");
	case ESkyPiece::Lanes: return TEXT("LANES");
	case ESkyPiece::Split: return TEXT("SPLIT");
	case ESkyPiece::Checkpoint: return TEXT("CHECKPOINT");
	case ESkyPiece::Finish: return TEXT("FINISH");
	case ESkyPiece::Close: return TEXT("CLOSE LAP");
	case ESkyPiece::Start: return TEXT("START");
	default: return TEXT("?");
	}
}

const TCHAR* SkyBuilder::PieceHelp(ESkyPiece T)
{
	switch (T)
	{
	case ESkyPiece::Straight: return TEXT("A flat straight run.");
	case ESkyPiece::Curve: return TEXT("A banked curve: left is +, right is -.");
	case ESkyPiece::Ramp: return TEXT("Climbs or drops, level at both ends.");
	case ESkyPiece::Jump: return TEXT("A lip, an open gap, a landing pad.");
	case ESkyPiece::Loop: return TEXT("A vertical loop: carry speed into it.");
	case ESkyPiece::Corkscrew: return TEXT("The track rolls round its own axis.");
	case ESkyPiece::WallRide: return TEXT("Twists up the wall on one side and back.");
	case ESkyPiece::Booster: return TEXT("A speed strip.");
	case ESkyPiece::Lanes: return TEXT("Widens or narrows the track.");
	case ESkyPiece::Split: return TEXT("Forks the track; the branches rejoin by themselves. View switches branch.");
	case ESkyPiece::Checkpoint: return TEXT("A gate to pass, in order.");
	case ESkyPiece::Finish: return TEXT("Ends a point-to-point course.");
	case ESkyPiece::Close: return TEXT("Joins the end back into the start gate: a lap course.");
	default: return TEXT("");
	}
}

// ============================================================================================ editing the course

// N branches fanned out from a split, each with its share of the lanes (2 lanes, 2 branches: 1 lane each)
void SkyBuilder::FillBranches(FSkyPiece& Split, int32 LanesHere)
{
	const int32 N = FMath::Clamp(Split.Branches.Num() > 0 ? Split.Branches.Num() : 2, 2, SkyCourse::MaxBranches);
	static const double A2[] = { 12, -12 }, A3[] = { 16, 0, -16 }, A4[] = { 24, 8, -8, -24 };
	const double* Angles = N == 2 ? A2 : N == 3 ? A3 : A4;
	const int32 BranchLanes = FMath::Clamp(LanesHere / N, SkyCourse::MinLanes, SkyCourse::MaxLanes);
	Split.Branches.Reset();
	for (int32 i = 0; i < N; ++i)
	{
		FSkyBranch B;
		B.Lanes = BranchLanes;
		B.Angle = Angles[i];
		Split.Branches.Add(B);
	}
}

int32 SkyBuilder::ApplyPlace(FSkyCourse& C, int32 Seq, const FSkyPiece& In, int32 LanesHere)
{
	if (!C.Seqs.IsValidIndex(Seq)) return INDEX_NONE;
	FSkyPiece Piece = In;
	int32 First = INDEX_NONE;
	if (Piece.Type == ESkyPiece::Split)
	{
		FillBranches(Piece, LanesHere);
		for (FSkyBranch& B : Piece.Branches)
		{
			B.Seq = C.Seqs.Num();
			C.Seqs.AddDefaulted();
			if (First == INDEX_NONE) First = B.Seq;
		}
	}
	else
	{
		Piece.Branches.Reset();
	}
	C.Seqs[Seq].Pieces.Add(Piece);
	return First;
}

bool SkyBuilder::FindOwner(const FSkyCourse& C, int32 Seq, FOwner& Out)
{
	for (int32 s = 0; s < C.Seqs.Num(); ++s)
		for (int32 p = 0; p < C.Seqs[s].Pieces.Num(); ++p)
		{
			const FSkyPiece& Pc = C.Seqs[s].Pieces[p];
			for (int32 b = 0; b < Pc.Branches.Num(); ++b)
				if (Pc.Branches[b].Seq == Seq) { Out.ParentSeq = s; Out.PieceIdx = p; Out.BranchIdx = b; return true; }
		}
	return false;
}

bool SkyBuilder::IsRoutineWarning(const FString& W)
{
	return W.Contains(TEXT("doesn't end with finish or close"));
}

bool SkyBuilder::EndsClosed(const FSkyCourse& C, int32 Seq)
{
	if (!C.Seqs.IsValidIndex(Seq) || C.Seqs[Seq].Pieces.Num() == 0) return false;
	const ESkyPiece T = C.Seqs[Seq].Pieces.Last().Type;
	return T == ESkyPiece::Finish || T == ESkyPiece::Close;
}

// every sequence a split owns, branches inside branches included
static void CollectSeqs(const FSkyCourse& C, const FSkyPiece& Split, TArray<int32>& Out)
{
	for (const FSkyBranch& B : Split.Branches)
	{
		if (!C.Seqs.IsValidIndex(B.Seq)) continue;
		Out.AddUnique(B.Seq);
		for (const FSkyPiece& Inner : C.Seqs[B.Seq].Pieces) CollectSeqs(C, Inner, Out);
	}
}

// drop sequences and renumber every branch that pointed past them; Follow is a sequence index kept pointing at the same one
static void RemoveSeqs(FSkyCourse& C, TArray<int32> Dead, int32& Follow)
{
	Dead.Sort([](int32 A, int32 B) { return A > B; });
	for (const int32 Idx : Dead)
	{
		if (!C.Seqs.IsValidIndex(Idx)) continue;
		C.Seqs.RemoveAt(Idx);
		for (FSkySeq& S : C.Seqs)
			for (FSkyPiece& Pc : S.Pieces)
				for (FSkyBranch& B : Pc.Branches)
					if (B.Seq > Idx) --B.Seq;
		if (Follow > Idx) --Follow;
	}
}

FString SkyBuilder::RemoveLast(FSkyCourse& C, int32& Seq)
{
	if (!C.Seqs.IsValidIndex(Seq)) return TEXT("Nothing to remove here");
	if (C.Seqs[Seq].Pieces.Num() == 0)
	{
		// an empty branch: B takes the whole split away (when nothing was built after it)
		FOwner O;
		if (!FindOwner(C, Seq, O)) return TEXT("Nothing to remove here");
		FSkySeq& Parent = C.Seqs[O.ParentSeq];
		if (O.PieceIdx != Parent.Pieces.Num() - 1) return TEXT("Remove what comes after the split first (View switches line)");
		const FSkyPiece SplitPiece = Parent.Pieces.Last();
		TArray<int32> Dead;
		CollectSeqs(C, SplitPiece, Dead);
		const int32 Back = O.ParentSeq;
		Parent.Pieces.Pop();
		int32 Follow = Back;
		RemoveSeqs(C, Dead, Follow);
		Seq = Follow;
		return FString();
	}
	if (Seq == 0 && C.Seqs[0].Pieces.Num() <= 1 && C.Seqs[0].Pieces[0].Type == ESkyPiece::Start) return TEXT("The start piece stays");
	const FSkyPiece Last = C.Seqs[Seq].Pieces.Last();
	C.Seqs[Seq].Pieces.Pop();
	if (Last.Type == ESkyPiece::Split)
	{
		TArray<int32> Dead;
		CollectSeqs(C, Last, Dead);
		int32 Follow = Seq;
		RemoveSeqs(C, Dead, Follow);
		Seq = Follow;
	}
	return FString();
}

FString SkyBuilder::SeqLabel(const FSkyCourse& C, const FSkyBaked& B, int32 Seq)
{
	if (Seq == 0 || !C.Seqs.IsValidIndex(Seq)) return TEXT("MAIN LINE");
	FOwner O;
	if (!FindOwner(C, Seq, O)) return TEXT("BRANCH");
	int32 SplitNo = 0;
	for (int32 i = 0; i < B.Splits.Num(); ++i)
		if (B.Splits[i].Seq == O.ParentSeq && B.Splits[i].Piece == O.PieceIdx) { SplitNo = i + 1; break; }
	const FSkyPiece& Sp = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx];
	const FSkyBranch& Br = Sp.Branches[O.BranchIdx];
	const TCHAR* Side = Br.Angle > 0.5 ? TEXT("LEFT") : Br.Angle < -0.5 ? TEXT("RIGHT") : TEXT("STRAIGHT");
	return FString::Printf(TEXT("%s · BRANCH %d OF %d · %s · %d LANE%s"), SplitNo ? *FString::Printf(TEXT("SPLIT %d"), SplitNo) : TEXT("SPLIT"),
		O.BranchIdx + 1, Sp.Branches.Num(), Side, Br.Lanes, Br.Lanes == 1 ? TEXT("") : TEXT("S"));
}

// ============================================================================================ the pawn

ASkyCourseBuilderPawn::ASkyCourseBuilderPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bTickEvenWhenPaused = false;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->SetFieldOfView(60.f);
	Camera->bUsePawnControlRotation = false;
	bUseControllerRotationPitch = bUseControllerRotationYaw = bUseControllerRotationRoll = false;
	SetCanBeDamaged(false);
}

void ASkyCourseBuilderPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Impl) Impl = MakeShared<FSkyCourseBuilderImpl>(this);
	Impl->Tick(DeltaSeconds);
}

void ASkyCourseBuilderPawn::DrawHud(AHUD* Hud, UCanvas* Canvas, float S)
{
	if (!Impl) Impl = MakeShared<FSkyCourseBuilderImpl>(this);
	Impl->DrawHud(Hud, Canvas, S);
}

void ASkyCourseBuilderPawn::TestPress(const FString& Button)
{
	if (!Impl) Impl = MakeShared<FSkyCourseBuilderImpl>(this);
	Impl->Press(Button);
}

void ASkyCourseBuilderPawn::TestType(const FString& Text)
{
	if (!Impl) Impl = MakeShared<FSkyCourseBuilderImpl>(this);
	Impl->TypeText(Text);
}

void ASkyCourseBuilderPawn::TestCamera(double Yaw, double Pitch, double Distance, bool bSnap)
{
	if (!Impl) Impl = MakeShared<FSkyCourseBuilderImpl>(this);
	Impl->SetCamera(Yaw, Pitch, Distance, bSnap);
}

FString ASkyCourseBuilderPawn::TestStateJson() const
{
	return Impl ? Impl->StateJson() : TEXT("{}");
}

void SkyCourseBuilderToast(ASkyCourseBuilderPawn* Pawn, const FString& Title, const FString& Sub, bool bBad)
{
	FSkyCourseBuilderImpl::ToastFor(Pawn, Title, Sub, bBad);
}

void FSkyCourseBuilderImpl::ToastFor(ASkyCourseBuilderPawn* Pawn, const FString& Title, const FString& Sub, bool bBad)
{
	if (!Pawn) return;
	if (!Pawn->Impl) Pawn->Impl = MakeShared<FSkyCourseBuilderImpl>(Pawn);
	Pawn->Impl->Toast(Title, Sub, bBad);
}

// ============================================================================================ the editor

FSkyCourseBuilderImpl::FSkyCourseBuilderImpl(ASkyCourseBuilderPawn* InPawn) : P(InPawn)
{
	Stored.SetNum((int32)ESkyPiece::Count);
	for (int32 i = 0; i < NumPalette; ++i) Stored[(int32)Palette[i]] = MakeDefault(Palette[i], SkyCourse::DefaultLanes);
	DefaultsLanes = SkyCourse::DefaultLanes;
	P->PaletteIndex = 0;
	P->Pending = Stored[(int32)Palette[0]];
}

void FSkyCourseBuilderImpl::Toast(const FString& Title, const FString& Sub, bool bBad)
{
	// the same message twice in a row only refreshes the first
	if (Toasts.Num() > 0 && Toasts.Last().Title == Title && Toasts.Last().Sub == Sub) { Toasts.Last().Born = Time; return; }
	FToast T;
	T.Title = Title;
	T.Sub = Sub;
	T.Born = Time;
	T.bBad = bBad;
	Toasts.Add(T);
	if (Toasts.Num() > 4) Toasts.RemoveAt(0);
	UE_LOG(LogSkyBuilder, Log, TEXT("toast: %s | %s"), *Title, *Sub);
}

void FSkyCourseBuilderImpl::ToastErrors(const TArray<FString>& Errors, const TCHAR* Title)
{
	if (Errors.Num() == 0) { Toast(Title, FString(), true); return; }
	for (int32 i = 0; i < Errors.Num() && i < 3; ++i)
	{
		FString E = Errors[i];
		if (E.Len() > 120) E = E.Left(117) + TEXT("...");
		Toast(i == 0 ? FString(Title) : FString(TEXT("and")), E, true);
	}
	if (Errors.Num() > 3) Toast(FString::Printf(TEXT("%d more problems"), Errors.Num() - 3), FString(), true);
}

void FSkyCourseBuilderImpl::Press(const FString& Button)
{
	TestQueue.Add(Button.ToLower());
}

void FSkyCourseBuilderImpl::TypeText(const FString& Text)
{
	if (Screen != EBuilderScreen::Name) return;
	for (const TCHAR C : Text)
	{
		if (NameText.Len() < 48 && (FChar::IsAlnum(C) || C == TEXT(' ') || C == TEXT('-') || C == TEXT('_'))) NameText.AppendChar(C);
	}
}

void FSkyCourseBuilderImpl::SetCamera(double InYaw, double InPitch, double InDist, bool bSnap)
{
	Yaw = InYaw;
	Pitch = FMath::Clamp(InPitch, 8.0, 89.0);
	Dist = FMath::Clamp(InDist, 6.0, 1000.0);
	if (bSnap) { YawS = Yaw; PitchS = Pitch; DistS = Dist; FocusS = FocusT; }
}

// ---------------------------------------------------------------------------------------------- input

bool FSkyCourseBuilderImpl::Edge(APlayerController* PC, const FKey& K, float Dt, bool bRepeat, double Delay, double Rate, bool bTyping)
{
	FRepeat& R = (bTyping ? TypeKeys : Keys).FindOrAdd(K);
	const bool bNow = PC && PC->IsInputKeyDown(K);
	bool bFire = false;
	if (bNow && !R.bDown) { bFire = true; R.T = 0; R.Acc = 0; }
	else if (bNow && bRepeat)
	{
		R.T += Dt;
		if (R.T > Delay && (R.Acc += Dt) >= Rate) { R.Acc -= Rate; bFire = true; }
	}
	R.bDown = bNow;
	return bFire;
}

FSkyCourseBuilderImpl::FIn FSkyCourseBuilderImpl::Gather(float Dt)
{
	FIn In;
	APlayerController* PC = P->bTestInput ? nullptr : Cast<APlayerController>(P->GetController());
	if (PC)
	{
		auto Ax = [PC](const FKey& K) { return (double)PC->GetInputAnalogKeyState(K); };
		auto Dn = [PC](const FKey& K) { return PC->IsInputKeyDown(K) ? 1.0 : 0.0; };
		// the sticks, with a round dead zone
		auto Dead = [](double& X, double& Y)
		{
			const double M = FMath::Sqrt(X * X + Y * Y);
			if (M < 0.16) { X = Y = 0; return; }
			const double K = FMath::Min(1.0, (M - 0.16) / 0.84) / M;
			X *= K; Y *= K;
		};
		double Lx = Ax(EKeys::Gamepad_LeftX), Ly = Ax(EKeys::Gamepad_LeftY), Rx = Ax(EKeys::Gamepad_RightX), Ry = Ax(EKeys::Gamepad_RightY);
		Dead(Lx, Ly);
		Dead(Rx, Ry);
		In.PanX = FMath::Clamp(Lx + Dn(EKeys::D) - Dn(EKeys::A), -1.0, 1.0);
		In.PanY = FMath::Clamp(Ly + Dn(EKeys::W) - Dn(EKeys::S), -1.0, 1.0);
		In.OrbX = FMath::Clamp(Rx + Dn(EKeys::C) - Dn(EKeys::Z), -1.0, 1.0);
		In.OrbY = FMath::Clamp(Ry + Dn(EKeys::Home) - Dn(EKeys::End), -1.0, 1.0);
		In.Zoom = FMath::Clamp(Ax(EKeys::Gamepad_RightTriggerAxis) - Ax(EKeys::Gamepad_LeftTriggerAxis) + Dn(EKeys::PageUp) - Dn(EKeys::PageDown), -1.0, 1.0);
		In.Wheel = Ax(EKeys::MouseWheelAxis);
		if (PC->IsInputKeyDown(EKeys::RightMouseButton))
		{
			float Mx = 0, My = 0;
			PC->GetInputMouseDelta(Mx, My);
			In.MouseYaw = Mx * 0.25;
			In.MousePitch = My * 0.25;
		}
		const bool bCtrl = PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl);
		In.bLeft = Edge(PC, EKeys::Gamepad_DPad_Left, Dt, true) | Edge(PC, EKeys::Left, Dt, true);
		In.bRight = Edge(PC, EKeys::Gamepad_DPad_Right, Dt, true) | Edge(PC, EKeys::Right, Dt, true);
		In.bUp = Edge(PC, EKeys::Gamepad_DPad_Up, Dt, true) | Edge(PC, EKeys::Up, Dt, true);
		In.bDown = Edge(PC, EKeys::Gamepad_DPad_Down, Dt, true) | Edge(PC, EKeys::Down, Dt, true);
		In.bLB = Edge(PC, EKeys::Gamepad_LeftShoulder, Dt, true) | Edge(PC, EKeys::Q, Dt, true);
		In.bRB = Edge(PC, EKeys::Gamepad_RightShoulder, Dt, true) | Edge(PC, EKeys::E, Dt, true);
		In.bA = Edge(PC, EKeys::Gamepad_FaceButton_Bottom, Dt, false) | Edge(PC, EKeys::Enter, Dt, false);
		In.bPadB = Edge(PC, EKeys::Gamepad_FaceButton_Right, Dt, false);
		In.bB = In.bPadB | Edge(PC, EKeys::BackSpace, Dt, false);
		In.bX = Edge(PC, EKeys::Gamepad_FaceButton_Left, Dt, false) | Edge(PC, EKeys::M, Dt, false);
		In.bY = Edge(PC, EKeys::Gamepad_FaceButton_Top, Dt, false) | Edge(PC, EKeys::T, Dt, false);
		In.bView = Edge(PC, EKeys::Gamepad_Special_Left, Dt, false) | Edge(PC, EKeys::Tab, Dt, false);
		In.bMenu = Edge(PC, EKeys::Gamepad_Special_Right, Dt, false) | Edge(PC, EKeys::Escape, Dt, false) | Edge(PC, EKeys::P, Dt, false);
		In.bR3 = Edge(PC, EKeys::Gamepad_RightThumbstick, Dt, false) | Edge(PC, EKeys::R, Dt, false);
		In.bUndo = Edge(PC, EKeys::U, Dt, false) | (bCtrl && Edge(PC, EKeys::Z, Dt, false));
		In.bEnter = In.bA;
		In.bBackspace = Edge(PC, EKeys::BackSpace, Dt, true, 0.4, 0.06);
		In.bEscape = In.bMenu;
		if (bCtrl) { In.OrbX = Rx; }   // Ctrl+Z is undo, not orbit
	}
	else if (P->bTestInput)
	{
		In.PanX = P->TestPanX; In.PanY = P->TestPanY; In.OrbX = P->TestOrbitX; In.OrbY = P->TestOrbitY; In.Zoom = P->TestZoom;
	}
	for (const FString& B : TestQueue)
	{
		if (B == TEXT("left")) In.bLeft = true;
		else if (B == TEXT("right")) In.bRight = true;
		else if (B == TEXT("up")) In.bUp = true;
		else if (B == TEXT("down")) In.bDown = true;
		else if (B == TEXT("lb")) In.bLB = true;
		else if (B == TEXT("rb")) In.bRB = true;
		else if (B == TEXT("a")) { In.bA = true; In.bEnter = true; }
		else if (B == TEXT("b")) { In.bB = true; In.bPadB = true; }
		else if (B == TEXT("x")) In.bX = true;
		else if (B == TEXT("y")) In.bY = true;
		else if (B == TEXT("view")) In.bView = true;
		else if (B == TEXT("menu")) { In.bMenu = true; In.bEscape = true; }
		else if (B == TEXT("r3")) In.bR3 = true;
		else if (B == TEXT("undo")) In.bUndo = true;
		else if (B == TEXT("backspace")) In.bBackspace = true;
	}
	TestQueue.Reset();
	return In;
}

// ---------------------------------------------------------------------------------------------- the frame

void FSkyCourseBuilderImpl::Tick(float Dt)
{
	Dt = FMath::Min(Dt, 0.1f);
	Time += Dt;
	ASkyCourseMode* Mode = P->Mode.Get();
	if (!Mode) return;
	ModeRef = Mode;
	ASkyCourseTrack* Track = Mode->GetTrack();
	while (Toasts.Num() > 0 && Time - Toasts[0].Born > 7.0) Toasts.RemoveAt(0);
	APlayerController* PC = Cast<APlayerController>(P->GetController());
	const bool bActive = (PC != nullptr || P->bTestInput) && !Mode->IsDriving();
	if (!bActive)
	{
		// the car has the wheel (or nobody does): hide the editor's bits
		if (UProceduralMeshComponent* M = CursorMesh.Get()) M->SetVisibility(false);
		if (bWasActive && Track) Track->ShowPreview(nullptr, FSkyFrame(), SkyCourse::DefaultLanes, true);
		bWasActive = false;
		return;
	}
	if (!bWasActive)
	{
		// control just came back (start of the mode, or off a test drive): the camera goes over the cursor
		CloseScreens();
		bHaveCursor = false;
		Sync();
		OnCursorMoved(!bCamInit);
		MarkFitDirty();
		FitDueAt = 0;
		if (UProceduralMeshComponent* M = CursorMesh.Get()) M->SetVisibility(true);
	}
	bWasActive = true;
	Sync();
	const FIn In = Gather(Dt);
	switch (Screen)
	{
	case EBuilderScreen::Build: HandleBuild(In, PC); break;
	case EBuilderScreen::Menu: HandleMenu(In); break;
	case EBuilderScreen::Load: HandleLoad(In); break;
	case EBuilderScreen::Name: HandleName(In, PC, Dt); break;
	case EBuilderScreen::Garage: HandleGarage(In); break;
	}
	Sync();    // an edit may have changed the course just now
	UpdateFit();
	UpdateCamera(Dt, Screen == EBuilderScreen::Build ? In : FIn());
	UpdateCursorVisual(Dt);
}

// the cursor follows the course: after every change, and when the line being edited switches
void FSkyCourseBuilderImpl::Sync()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const FSkyCourse& C = Mode->GetCourse();
	if (!C.Seqs.IsValidIndex(P->EditSeq)) P->EditSeq = 0;
	const int32 Rev = Mode->Revision();
	if (bHaveCursor && Rev == SeenRevision && P->EditSeq == SeenSeq) return;
	const bool bFirst = !bHaveCursor;
	SeenRevision = Rev;
	SeenSeq = P->EditSeq;
	bHaveCursor = true;
	const FSkyBaked& B = Mode->GetBaked();
	int32 L = SkyCourse::DefaultLanes;
	if (B.bValid)
	{
		Cursor = SkyCourse::EndOf(B, C, P->EditSeq, &L);
	}
	else
	{
		// nothing baked yet: stand at the course's start
		const FSkyCourse Starter = Mode->StarterCourse();
		FSkyFrame F;
		F.P = Starter.Start;
		const double Y = FMath::DegreesToRadians(Starter.Yaw);
		F.F = FVector(FMath::Cos(Y), FMath::Sin(Y), 0);
		F.L = FVector(-FMath::Sin(Y), FMath::Cos(Y), 0);
		F.U = FVector(0, 0, 1);
		Cursor = F;
		L = Starter.Lanes;
	}
	CursorLanes = FMath::Clamp(L, SkyCourse::MinLanes, SkyCourse::MaxLanes);
	bClosed = EndsClosed(C, P->EditSeq);
	RefreshDefaults();
	OnCursorMoved(bFirst && !bCamInit);
	MarkFitDirty();
	FitDueAt = 0;
	// new warnings from the bake show up once
	TArray<FString> Worth;
	for (const FString& W : B.Warnings) if (!IsRoutineWarning(W)) Worth.Add(W);
	const FString Key = FString::Join(Worth, TEXT("|"));
	if (Key != LastWarnKey)
	{
		LastWarnKey = Key;
		if (Worth.Num() > 0) Toast(TEXT("Heads up"), Worth[0].Left(120), false);
	}
}

// lane-dependent pieces (lanes, loop, split) are re-made when the lane count at the cursor changes
void FSkyCourseBuilderImpl::RefreshDefaults()
{
	if (DefaultsLanes == CursorLanes) return;
	DefaultsLanes = CursorLanes;
	for (const ESkyPiece T : { ESkyPiece::Lanes, ESkyPiece::Loop, ESkyPiece::Split })
	{
		FSkyPiece Fresh = MakeDefault(T, CursorLanes);
		FSkyPiece& Old = Stored[(int32)T];
		if (T == ESkyPiece::Lanes) { Fresh.Length = Old.Length; Fresh.Align = Old.Align; }
		if (T == ESkyPiece::Loop) { Fresh.Radius = Old.Radius; }
		if (T == ESkyPiece::Split) { Fresh.Length = Old.Length; Fresh.Gate = Old.Gate; Fresh.MergeLength = Old.MergeLength; Fresh.Branches.SetNum(FMath::Max(2, Old.Branches.Num())); }
		Old = Fresh;
	}
	if (Palette[P->PaletteIndex] == ESkyPiece::Lanes || Palette[P->PaletteIndex] == ESkyPiece::Loop || Palette[P->PaletteIndex] == ESkyPiece::Split)
		P->Pending = Stored[(int32)Palette[P->PaletteIndex]];
}

void FSkyCourseBuilderImpl::OnCursorMoved(bool bSnap)
{
	const double Heading = FMath::RadiansToDegrees(FMath::Atan2(Cursor.F.Y, Cursor.F.X));
	if (!bCamInit)
	{
		Yaw = YawS = Heading;
		Pitch = PitchS = 52;
		Dist = DistS = 70;
		FocusT = FocusS = Cursor.P;
		bCamInit = true;
	}
	else
	{
		// the view turns with the track: whatever you were looking at stays in front of you
		Yaw += FMath::FindDeltaAngleDegrees(LastHeading, Heading);
	}
	LastHeading = Heading;
	Pan = FVector::ZeroVector;
	FocusT = Cursor.P;
	if (bSnap) { YawS = Yaw; FocusS = FocusT; }
}

void FSkyCourseBuilderImpl::UpdateCamera(float Dt, const FIn& In)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode || !P->Camera) return;
	// orbit, zoom
	Yaw += (In.OrbX * 105.0) * Dt + In.MouseYaw;
	Pitch = FMath::Clamp(Pitch + (In.OrbY * 65.0) * Dt + In.MousePitch, 10.0, 89.0);
	Dist = FMath::Clamp(Dist * FMath::Exp(-(In.Zoom * 1.5) * Dt) * FMath::Pow(0.9, In.Wheel), 6.0, 1000.0);
	// pan: relative to where the camera looks
	const double Ry = FMath::DegreesToRadians(YawS);
	const FVector Fwd(FMath::Cos(Ry), FMath::Sin(Ry), 0), Left(-FMath::Sin(Ry), FMath::Cos(Ry), 0);
	const double Speed = 0.9 * FMath::Max(DistS, 12.0);
	Pan += (Fwd * In.PanY - Left * In.PanX) * Speed * Dt;
	const FBox A = Mode->BuildArea();
	if (A.IsValid)
	{
		FVector F = Cursor.P + Pan;
		F.X = FMath::Clamp(F.X, A.Min.X - 60.0, A.Max.X + 60.0);
		F.Y = FMath::Clamp(F.Y, A.Min.Y - 60.0, A.Max.Y + 60.0);
		Pan = FVector(F.X - Cursor.P.X, F.Y - Cursor.P.Y, 0);
	}
	FocusT = Cursor.P + Pan;
	// ease everything: the camera glides when the cursor jumps and settles when the sticks let go
	auto Ease = [Dt](double Cur, double Tgt, double K) { return Cur + (Tgt - Cur) * (1.0 - FMath::Exp(-K * Dt)); };
	FocusS = FVector(Ease(FocusS.X, FocusT.X, 6.5), Ease(FocusS.Y, FocusT.Y, 6.5), Ease(FocusS.Z, FocusT.Z, 6.5));
	YawS += FMath::FindDeltaAngleDegrees(YawS, Yaw) * (1.0 - FMath::Exp(-9.0 * Dt));   // the short way round
	PitchS = Ease(PitchS, Pitch, 9.0);
	DistS = Ease(DistS, Dist, 6.0);
	const double Py = FMath::DegreesToRadians(YawS), Pp = FMath::DegreesToRadians(PitchS);
	const FVector Back(-FMath::Cos(Py) * FMath::Cos(Pp), -FMath::Sin(Py) * FMath::Cos(Pp), FMath::Sin(Pp));
	FVector CamPos = FocusS + Back * DistS;
	CamPos.Z = FMath::Max(CamPos.Z, Mode->GroundZ() + 1.5);
	const FVector Dir = (FocusS - CamPos).GetSafeNormal();
	const FRotator Rot = FRotationMatrix::MakeFromXZ(SkyCourse::DirToUE(Dir), FVector(0, 0, 1)).Rotator();
	P->SetActorLocation(SkyCourse::ToUE(FocusS));   // (the root first: the camera hangs off it)
	P->Camera->SetWorldLocationAndRotation(SkyCourse::ToUE(CamPos), Rot);
}

// ---------------------------------------------------------------------------------------------- the cursor

UProceduralMeshComponent* FSkyCourseBuilderImpl::EnsureCursor()
{
	if (UProceduralMeshComponent* M = CursorMesh.Get()) return M;
	UProceduralMeshComponent* M = NewObject<UProceduralMeshComponent>(P, TEXT("BuilderCursor"));
	M->SetupAttachment(P->GetRootComponent());
	M->SetUsingAbsoluteLocation(true);
	M->SetUsingAbsoluteRotation(true);
	M->SetUsingAbsoluteScale(true);
	M->RegisterComponent();
	M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	M->SetCastShadow(false);
	M->bUseAsyncCooking = false;
	CursorMesh = M;
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SkyCity/Pickups/Materials/MI_CarLight.MI_CarLight"));
	if (!Base) Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/McGregor/Materials/MI_LEDRed.MI_LEDRed"));
	if (Base)
	{
		UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(Base, P);
		CursorMat = Mid;
		M->SetMaterial(0, Mid);
	}
	CursorWidthBuilt = -1;
	return M;
}

namespace
{
	struct FMeshBuf
	{
		TArray<FVector> V, N;
		TArray<int32> T;
		TArray<FVector2D> UV;
		// a triangle that faces Out (Unreal's front face is the one where (b - a) x (c - a) points away from the viewer)
		void Tri(const FVector& A, const FVector& B, const FVector& C, const FVector& Out)
		{
			const FVector Nrm = FVector::CrossProduct(B - A, C - A);
			const bool bFlip = FVector::DotProduct(Nrm, Out) > 0;
			const int32 I = V.Num();
			V.Add(A); V.Add(bFlip ? C : B); V.Add(bFlip ? B : C);
			for (int32 k = 0; k < 3; ++k) { N.Add(Out.GetSafeNormal()); UV.Add(FVector2D(k == 1, k == 2)); T.Add(I + k); }
		}
		void Quad(const FVector& A, const FVector& B, const FVector& C, const FVector& D, const FVector& Out) { Tri(A, B, C, Out); Tri(A, C, D, Out); }
		// an axis-aligned box in local space (x forward, y right, z up), centred at Mid
		void Box(const FVector& Mid, const FVector& Half)
		{
			const FVector P0 = Mid - Half, P1 = Mid + Half;
			const FVector C[8] = { FVector(P0.X, P0.Y, P0.Z), FVector(P1.X, P0.Y, P0.Z), FVector(P1.X, P1.Y, P0.Z), FVector(P0.X, P1.Y, P0.Z),
				FVector(P0.X, P0.Y, P1.Z), FVector(P1.X, P0.Y, P1.Z), FVector(P1.X, P1.Y, P1.Z), FVector(P0.X, P1.Y, P1.Z) };
			Quad(C[4], C[5], C[6], C[7], FVector(0, 0, 1));
			Quad(C[0], C[1], C[2], C[3], FVector(0, 0, -1));
			Quad(C[1], C[2], C[6], C[5], FVector(1, 0, 0));
			Quad(C[0], C[3], C[7], C[4], FVector(-1, 0, 0));
			Quad(C[2], C[3], C[7], C[6], FVector(0, 1, 0));
			Quad(C[0], C[1], C[5], C[4], FVector(0, -1, 0));
		}
		// a flat strip on the ground between two points (cm), Width wide, slightly above
		void Strip(const FVector2D& A, const FVector2D& B, double Width, double Z)
		{
			const FVector2D D = (B - A).GetSafeNormal(), Nn(-D.Y, D.X);
			const FVector2D O = Nn * Width * 0.5;
			Quad(FVector(A.X - O.X, A.Y - O.Y, Z), FVector(B.X - O.X, B.Y - O.Y, Z), FVector(B.X + O.X, B.Y + O.Y, Z), FVector(A.X + O.X, A.Y + O.Y, Z), FVector(0, 0, 1));
			Quad(FVector(A.X - O.X, A.Y - O.Y, Z), FVector(B.X - O.X, B.Y - O.Y, Z), FVector(B.X + O.X, B.Y + O.Y, Z), FVector(A.X + O.X, A.Y + O.Y, Z), FVector(0, 0, -1));
		}
	};
}

// A gate frame across the end of the track (so you see the width), a chevron ahead and a tall thin light beam so the
// cursor can be found from far above. Built in cm, x along the track, y across, z up; scaled up when the camera is far.
void FSkyCourseBuilderImpl::BuildCursorMesh(double Width)
{
	UProceduralMeshComponent* M = EnsureCursor();
	CursorWidthBuilt = Width;
	const double Hw = (Width * 0.5 + 1.0) * 100.0;
	FMeshBuf B;
	B.Strip(FVector2D(0, -Hw), FVector2D(0, Hw), 70.0, 6.0);                         // the bar across
	B.Box(FVector(0, -Hw, 120), FVector(25, 25, 120));                               // two posts
	B.Box(FVector(0, Hw, 120), FVector(25, 25, 120));
	B.Strip(FVector2D(120, -Hw * 0.55), FVector2D(450, 0), 60.0, 6.0);               // the chevron
	B.Strip(FVector2D(120, Hw * 0.55), FVector2D(450, 0), 60.0, 6.0);
	B.Strip(FVector2D(450, 0), FVector2D(880, 0), 40.0, 6.0);                        // and a tail
	B.Box(FVector(0, 0, 700), FVector(7, 7, 700));                                   // the beam
	M->ClearAllMeshSections();
	M->CreateMeshSection(0, B.V, B.T, B.N, B.UV, TArray<FColor>(), TArray<FProcMeshTangent>(), false);
	if (UMaterialInstanceDynamic* Mid = CursorMat.Get()) M->SetMaterial(0, Mid);
}

void FSkyCourseBuilderImpl::UpdateCursorVisual(float Dt)
{
	if (!bHaveCursor) return;
	UProceduralMeshComponent* M = EnsureCursor();
	const ASkyCourseMode* CursorMode = ModeRef.Get();
	const double W = FMath::Max(Cursor.Width, CursorMode ? CursorMode->GetCourse().LaneWidth : SkyCourse::DefaultLaneWidth);
	if (!FMath::IsNearlyEqual(W, CursorWidthBuilt, 0.01)) BuildCursorMesh(W);
	M->SetVisibility(true);
	CursorBlink += Dt;
	const double Pulse = 0.5 + 0.5 * FMath::Sin(CursorBlink * 5.5);
	const FRotator Rot = FRotationMatrix::MakeFromXZ(SkyCourse::DirToUE(Cursor.F), SkyCourse::DirToUE(Cursor.U)).Rotator();
	const double Scale = FMath::Clamp(DistS / 60.0, 1.0, 3.2);
	M->SetWorldLocationAndRotation(SkyCourse::ToUE(Cursor.P), Rot);
	M->SetWorldScale3D(FVector(Scale));
	if (UMaterialInstanceDynamic* Mid = CursorMat.Get())
	{
		const FLinearColor Base = bClosed ? FLinearColor(1.0f, 0.55f, 0.1f) : FLinearColor(0.1f, 0.95f, 1.0f);
		Mid->SetVectorParameterValue(TEXT("Color"), Base * (float)(1.3 + 1.7 * Pulse));
		Mid->SetVectorParameterValue(TEXT("EmissiveColor"), Base);
		Mid->SetScalarParameterValue(TEXT("EmissiveStrength"), (float)(4.0 + 8.0 * Pulse));
	}
}

// ---------------------------------------------------------------------------------------------- the fit test

void FSkyCourseBuilderImpl::UpdateFit()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	ASkyCourseTrack* Track = Mode ? Mode->GetTrack() : nullptr;
	if (!Mode || !Track || !bFitDirty || Time < FitDueAt) return;
	bFitDirty = false;
	FitDueAt = Time + 0.07;   // settings held on the pad repeat quickly: bake at most ~14 times a second
	const FSkyCourse& C = Mode->GetCourse();
	if (EndsClosed(C, P->EditSeq))
	{
		bFits = false;
		FitReason = TEXT("The course is closed: remove its last piece (B) to keep building");
		Track->ShowPreview(nullptr, Cursor, CursorLanes, false);
		return;
	}
	FSkyCourse Try = C;
	ApplyPlace(Try, P->EditSeq, P->Pending, CursorLanes);
	const double T0 = FPlatformTime::Seconds();
	SkyCourse::Bake(Try, Mode->BuildArea(), Trial);
	FitMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	FitMsMax = FMath::Max(FitMsMax, FitMs);
	++FitCount;
	bFits = Trial.bValid;
	FitReason = bFits ? FString() : (Trial.Errors.Num() > 0 ? Trial.Errors[0] : FString(TEXT("It doesn't fit here")));
	FSkyPiece Show = P->Pending;
	if (Show.Type == ESkyPiece::Split) FillBranches(Show, CursorLanes);
	else Show.Branches.Reset();
	Track->ShowPreview(&Show, Cursor, CursorLanes, bFits);
}

// ---------------------------------------------------------------------------------------------- building

void FSkyCourseBuilderImpl::StoreCurrent()
{
	Stored[(int32)P->Pending.Type] = P->Pending;
}

void FSkyCourseBuilderImpl::SelectPiece(int32 Index)
{
	StoreCurrent();
	P->PaletteIndex = ((Index % NumPalette) + NumPalette) % NumPalette;
	P->Pending = Stored[(int32)Palette[P->PaletteIndex]];
	SecondField = 1;
	MarkFitDirty();
	FitDueAt = 0;
}

void FSkyCourseBuilderImpl::AdjustMain(int32 Dir)
{
	EF F[3];
	FieldsFor(P->Pending.Type, F);
	if (F[0] == EF::None) return;
	AdjustField(P->Pending, F[0], Dir);
	StoreCurrent();
	MarkFitDirty();
}

void FSkyCourseBuilderImpl::AdjustSecond(int32 Dir)
{
	EF F[3];
	FieldsFor(P->Pending.Type, F);
	if (F[1] == EF::None) return;
	AdjustField(P->Pending, F[SecondField == 2 && F[2] != EF::None ? 2 : 1], Dir);
	StoreCurrent();
	MarkFitDirty();
}

void FSkyCourseBuilderImpl::Place()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	if (bClosed) { Toast(TEXT("The course is closed"), TEXT("B removes its last piece"), true); return; }
	FSkyCourse Try = Mode->GetCourse();
	const int32 NewSeq = ApplyPlace(Try, P->EditSeq, P->Pending, CursorLanes);
	TArray<FString> Errors;
	if (Mode->SetCourse(Try, Errors))
	{
		if (NewSeq != INDEX_NONE)
		{
			P->EditSeq = NewSeq;
			Toast(TEXT("Split placed"), TEXT("Now on its first branch. View switches branch"));
		}
	}
	else
	{
		ToastErrors(Errors, TEXT("That piece doesn't fit"));
	}
}

void FSkyCourseBuilderImpl::RemoveLast()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	FSkyCourse Try = Mode->GetCourse();
	int32 Seq = P->EditSeq;
	const FString Why = SkyBuilder::RemoveLast(Try, Seq);
	if (!Why.IsEmpty()) { Toast(Why, FString(), true); return; }
	TArray<FString> Errors;
	if (Mode->SetCourse(Try, Errors)) P->EditSeq = Seq;
	else ToastErrors(Errors, TEXT("Can't remove that"));
}

void FSkyCourseBuilderImpl::CycleSeq()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const FSkyCourse& C = Mode->GetCourse();
	if (C.Seqs.Num() <= 1) { Toast(TEXT("No splits yet"), TEXT("A split piece makes branches to switch between")); return; }
	TArray<int32> Order;
	for (int32 s = 1; s < C.Seqs.Num(); ++s) Order.Add(s);
	Order.Add(0);   // the main line, after the merge
	int32 At = Order.IndexOfByKey(P->EditSeq);
	P->EditSeq = Order[(At + 1) % Order.Num()];
	Toast(TEXT("Editing"), SeqLabel(C, Mode->GetBaked(), P->EditSeq));
}

void FSkyCourseBuilderImpl::OpenMenu()
{
	Screen = EBuilderScreen::Menu;
	MenuSel = 0;
	if (ASkyCourseMode* Mode = ModeRef.Get()) LapSel = FMath::Clamp(LapSel, 1, FMath::Max(1, Mode->GetCourse().Laps));
}

void FSkyCourseBuilderImpl::CloseScreens()
{
	Screen = EBuilderScreen::Build;
}

void FSkyCourseBuilderImpl::HandleBuild(const FIn& In, APlayerController* PC)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	if (In.bMenu) { Screen = EBuilderScreen::Garage; GarageSel = 0; return; }
	if (In.bX) { OpenMenu(); return; }
	if (In.bY) { Mode->StartTestDrive(-1); return; }
	if (In.bUndo)
	{
		if (Mode->Undo()) Toast(TEXT("Undone"));
		else Toast(TEXT("Nothing to undo"), FString(), true);
		return;
	}
	if (In.bLeft) SelectPiece(P->PaletteIndex - 1);
	if (In.bRight) SelectPiece(P->PaletteIndex + 1);
	if (In.bUp) AdjustMain(+1);
	if (In.bDown) AdjustMain(-1);
	if (In.bLB) AdjustSecond(-1);
	if (In.bRB) AdjustSecond(+1);
	if (In.bR3)
	{
		EF F[3];
		FieldsFor(P->Pending.Type, F);
		if (F[2] != EF::None) SecondField = SecondField == 1 ? 2 : 1;
	}
	if (In.bA) Place();
	if (In.bB) RemoveLast();
	if (In.bView) CycleSeq();
}

// ---------------------------------------------------------------------------------------------- the menu

static const TCHAR* SkinLabel(ESkySkin S) { return S == ESkySkin::Classic ? TEXT("CLASSIC (orange toy track)") : S == ESkySkin::Neon ? TEXT("NEON (dark glass, cyan edge)") : TEXT("UNVEIL (concrete, red trim)"); }

static FString WidthLabel(double W)
{
	return FMath::IsNearlyEqual(W, SkyCourse::StandardLaneWidth, 0.01) ? FString(TEXT("STANDARD (5.5 m lanes)"))
		: FMath::IsNearlyEqual(W, SkyCourse::WideLaneWidth, 0.01) ? FString(TEXT("WIDE (8 m lanes)"))
		: FMath::IsNearlyEqual(W, SkyCourse::ExtraLaneWidth, 0.01) ? FString(TEXT("EXTRA WIDE (11 m lanes)"))
		: FString::Printf(TEXT("%.1f m lanes"), W);
}
static const TCHAR* AssistLabel(ESkyAssist A) { return A == ESkyAssist::Full ? TEXT("FULL") : A == ESkyAssist::Light ? TEXT("LIGHT") : TEXT("OFF"); }

TArray<FSkyCourseBuilderImpl::FItem> FSkyCourseBuilderImpl::BuildItems() const
{
	TArray<FItem> Items;
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return Items;
	const FSkyCourse& C = Mode->GetCourse();
	auto Add = [&Items](EMenuItem Id, const TCHAR* Label, const FString& Value = FString(), bool bAdjust = false)
	{
		FItem I; I.Id = Id; I.Label = Label; I.Value = Value; I.bAdjust = bAdjust; Items.Add(I);
	};
	Add(EMenuItem::Resume, TEXT("Back to building"));
	Add(EMenuItem::NewCourse, TEXT("New course"));
	Add(EMenuItem::Save, TEXT("Save course..."), C.Name);
	Add(EMenuItem::Load, TEXT("Load course..."));
	Add(EMenuItem::Rename, TEXT("Rename..."), C.Name);
	Add(EMenuItem::Example, TEXT("Example course"));
	Add(EMenuItem::Undo, TEXT("Undo last change"));
	Add(EMenuItem::Skin, TEXT("Skin"), SkinLabel(C.Skin), true);
	Add(EMenuItem::Laps, TEXT("Laps"), FString::FromInt(C.Laps), true);
	Add(EMenuItem::Opponents, TEXT("Opponents"), FString::FromInt(C.Opponents), true);
	Add(EMenuItem::Skill, TEXT("AI skill"), FString::Printf(TEXT("%.1f"), C.Skill), true);
	Add(EMenuItem::CatchUp, TEXT("Catch-up (AI rubber band)"), C.bCatchUp ? TEXT("ON") : TEXT("OFF"), true);
	Add(EMenuItem::TrackWidth, TEXT("Track width"), WidthLabel(C.LaneWidth), true);
	Add(EMenuItem::Assist, TEXT("Assists (your car, races)"), AssistLabel(Mode->GetAssist()), true);
	const FString Client = Mode->McpClient();
	Add(EMenuItem::Llm, TEXT("LLM link"), !Mode->IsMcpEnabled() ? TEXT("OFF") : Client.IsEmpty() ? TEXT("ON") : FString::Printf(TEXT("ON: %s"), *Client));
	Add(EMenuItem::ConnectClaude, TEXT("   Install in Claude Desktop"));
	Add(EMenuItem::CopyClaudeCode, TEXT("   Copy Claude Code command"));
	Add(EMenuItem::CopyAddress, TEXT("   Copy address (other AI apps)"));
	// the line being edited, when it's a branch of a split
	FOwner O;
	if (P->EditSeq != 0 && FindOwner(C, P->EditSeq, O))
	{
		const FSkyPiece& Sp = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx];
		const FSkyBranch& Br = Sp.Branches[O.BranchIdx];
		Add(EMenuItem::BranchLanes, TEXT("This branch: lanes"), FString::FromInt(Br.Lanes), true);
		Add(EMenuItem::BranchAngle, TEXT("This branch: angle"), FString::Printf(TEXT("%s%s°"), Br.Angle > 0 ? TEXT("+") : TEXT(""), *Num(Br.Angle)), true);
		FString Laps;
		if (C.Laps <= 1) Laps = TEXT("needs 2 or more laps");
		else
		{
			for (int32 L = 1; L <= C.Laps; ++L)
			{
				const bool bOpen = Br.Laps.Num() == 0 || Br.Laps.Contains(L);
				Laps += FString::Printf(TEXT("%s%d%s "), L == LapSel ? TEXT("[") : TEXT(""), L, L == LapSel ? (bOpen ? TEXT(" open]") : TEXT(" shut]")) : (bOpen ? TEXT("+") : TEXT("-")));
			}
		}
		Add(EMenuItem::BranchLaps, TEXT("This branch: open laps"), Laps, true);
		Add(EMenuItem::Gate, TEXT("Split gate"), Sp.Gate == ESkyGate::Lights ? TEXT("LIGHTS") : Sp.Gate == ESkyGate::Wall ? TEXT("WALL") : TEXT("NONE"), true);
		Add(EMenuItem::MergeLength, TEXT("Split merge length"), FString::Printf(TEXT("%s m"), *Num(Sp.MergeLength)), true);
		Add(EMenuItem::MergeLanes, TEXT("Split merge lanes"), Sp.MergeLanes <= 0 ? FString(TEXT("same as before")) : FString::FromInt(Sp.MergeLanes), true);
	}
	Add(EMenuItem::Garage, TEXT("Garage: switch map..."));
	return Items;
}

void FSkyCourseBuilderImpl::HandleMenu(const FIn& In)
{
	const TArray<FItem> Items = BuildItems();
	if (Items.Num() == 0) return;
	MenuSel = FMath::Clamp(MenuSel, 0, Items.Num() - 1);
	if (In.bUp) MenuSel = (MenuSel + Items.Num() - 1) % Items.Num();
	if (In.bDown) MenuSel = (MenuSel + 1) % Items.Num();
	const FItem& It = Items[MenuSel];
	if (In.bLeft || In.bLB) { if (It.bAdjust) Adjust(It.Id, -1); }
	if (In.bRight || In.bRB) { if (It.bAdjust) Adjust(It.Id, +1); }
	if (In.bA) Activate(It.Id);
	if (In.bB || In.bX || In.bMenu) CloseScreens();
}

void FSkyCourseBuilderImpl::Activate(EMenuItem Id)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	TArray<FString> Errors;
	switch (Id)
	{
	case EMenuItem::Resume: CloseScreens(); break;
	case EMenuItem::NewCourse:
		if (Mode->SetCourse(Mode->StarterCourse(), Errors)) { P->EditSeq = 0; CloseScreens(); Toast(TEXT("New course")); }
		else ToastErrors(Errors, TEXT("Can't start a new course"));
		break;
	case EMenuItem::Save:
		Screen = EBuilderScreen::Name; bNameIsSave = true; NameText = Mode->GetCourse().Name; NameWheel = 0;
		break;
	case EMenuItem::Rename:
		Screen = EBuilderScreen::Name; bNameIsSave = false; NameText = Mode->GetCourse().Name; NameWheel = 0;
		break;
	case EMenuItem::Load:
		LoadList = Mode->ListCourses();
		LoadSel = 0;
		Screen = EBuilderScreen::Load;
		break;
	case EMenuItem::Example:
	{
		const FSkyCourse Starter = Mode->StarterCourse();
		if (Mode->SetCourse(SkyCourse::Example(Starter.Start, Starter.Yaw), Errors)) { P->EditSeq = 0; CloseScreens(); Toast(TEXT("Example course")); }
		else ToastErrors(Errors, TEXT("The example doesn't fit here"));
		break;
	}
	case EMenuItem::Undo:
		if (Mode->Undo()) { CloseScreens(); Toast(TEXT("Undone")); } else Toast(TEXT("Nothing to undo"), FString(), true);
		break;
	case EMenuItem::Llm:
	{
		const bool bOn = !Mode->IsMcpEnabled();
		const bool bNow = Mode->SetMcpEnabled(bOn);
		if (bOn && !bNow) Toast(TEXT("The LLM link couldn't start"), TEXT("Is port 47800 already in use?"), true);
		else if (bNow) Toast(TEXT("LLM link on"), TEXT("http://127.0.0.1:47800/mcp, this computer only"));
		else Toast(TEXT("LLM link off"));
		break;
	}
	case EMenuItem::Garage: Screen = EBuilderScreen::Garage; GarageSel = 0; break;
	case EMenuItem::ConnectClaude:
	{
		// the extension only talks to the LLM link, so switch the link on first
		if (!Mode->IsMcpEnabled() && !Mode->SetMcpEnabled(true)) { Toast(TEXT("The LLM link couldn't start"), TEXT("Is port 47800 already in use?"), true); break; }
		const FString File = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("SkyCity/Connect/SkyCity.mcpb"));
		if (!FPaths::FileExists(File)) { Toast(TEXT("The Claude extension is missing from this build"), TEXT("see docs/COURSE_MCP.md to connect by hand"), true); break; }
		// macOS hands the .mcpb to Claude Desktop, which shows its own Install window
		FPlatformProcess::LaunchFileInDefaultExternalApplication(*File, nullptr, ELaunchVerb::Open, false);
		Toast(TEXT("Opening Claude Desktop"), TEXT("click Install in Claude's window, then ask Claude to build you a course"));
		break;
	}
	case EMenuItem::CopyClaudeCode:
		if (!Mode->IsMcpEnabled()) Mode->SetMcpEnabled(true);
		FPlatformApplicationMisc::ClipboardCopy(*FString::Printf(TEXT("claude mcp add --transport http skycity http://127.0.0.1:%d/mcp"), SkyCourse::McpPort));
		Toast(TEXT("Copied the Claude Code command"), TEXT("paste it into Terminal once, then ask Claude Code for a course"));
		break;
	case EMenuItem::CopyAddress:
		if (!Mode->IsMcpEnabled()) Mode->SetMcpEnabled(true);
		FPlatformApplicationMisc::ClipboardCopy(*FString::Printf(TEXT("http://127.0.0.1:%d/mcp"), SkyCourse::McpPort));
		Toast(TEXT("Copied the address"), TEXT("for AI apps that connect to MCP servers over HTTP"));
		break;
	case EMenuItem::BranchLaps:
	{
		FOwner O;
		const FSkyCourse& C = Mode->GetCourse();
		if (C.Laps <= 1) { Toast(TEXT("Set 2 or more laps first"), FString(), true); break; }
		if (!FindOwner(C, P->EditSeq, O)) break;
		const int32 Lap = FMath::Clamp(LapSel, 1, C.Laps);
		bool bBad = false;
		const bool bOk = Mode->Edit([&](FSkyCourse& Cc)
		{
			FSkyBranch& Br = Cc.Seqs[O.ParentSeq].Pieces[O.PieceIdx].Branches[O.BranchIdx];
			TArray<int32> Open;
			for (int32 L = 1; L <= Cc.Laps; ++L) if (Br.Laps.Num() == 0 || Br.Laps.Contains(L)) Open.Add(L);
			if (Open.Contains(Lap)) { Open.Remove(Lap); if (Open.Num() == 0) { bBad = true; return; } }
			else Open.Add(Lap);
			Open.Sort();
			Br.Laps = Open.Num() == Cc.Laps ? TArray<int32>() : Open;
		}, Errors);
		if (bBad) Toast(TEXT("A branch needs at least one open lap"), FString(), true);
		else if (!bOk) ToastErrors(Errors, TEXT("Can't change the lap routing"));
		break;
	}
	default: Adjust(Id, +1); break;
	}
}

void FSkyCourseBuilderImpl::Adjust(EMenuItem Id, int32 Dir)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	TArray<FString> Errors;
	FOwner O;
	const bool bBranch = P->EditSeq != 0 && FindOwner(Mode->GetCourse(), P->EditSeq, O);
	bool bOk = true;
	const TCHAR* What = TEXT("Can't change that");
	switch (Id)
	{
	case EMenuItem::Skin:
		bOk = Mode->Edit([Dir](FSkyCourse& C) { C.Skin = (ESkySkin)((((int32)C.Skin + Dir) % (int32)ESkySkin::Count + (int32)ESkySkin::Count) % (int32)ESkySkin::Count); }, Errors);
		break;
	case EMenuItem::Laps:
		bOk = Mode->Edit([Dir](FSkyCourse& C) { C.Laps = FMath::Clamp(C.Laps + Dir, 1, SkyCourse::MaxLaps); }, Errors);
		What = TEXT("Laps need a lap course: end it with a Close piece");
		break;
	case EMenuItem::CatchUp:
		bOk = Mode->Edit([](FSkyCourse& C) { C.bCatchUp = !C.bCatchUp; }, Errors);
		break;
	case EMenuItem::TrackWidth:
	{
		// Standard -> Wide -> Extra wide and round; the edit is checked like any other (a wider track can stop fitting
		// the build area or a loop's clearance), so a width that doesn't fit is refused with the reasons and rolled back
		static const double Widths[3] = { SkyCourse::StandardLaneWidth, SkyCourse::WideLaneWidth, SkyCourse::ExtraLaneWidth };
		int32 Now = 0;
		for (int32 i = 1; i < 3; ++i) if (FMath::Abs(Mode->GetCourse().LaneWidth - Widths[i]) < FMath::Abs(Mode->GetCourse().LaneWidth - Widths[Now])) Now = i;
		const double To = Widths[((Now + Dir) % 3 + 3) % 3];
		bOk = Mode->Edit([To](FSkyCourse& C) { C.LaneWidth = To; }, Errors);
		What = TEXT("That track width doesn't fit this course");
		break;
	}
	case EMenuItem::Assist:
	{
		// shown Full, Light, Off; a player setting (saved with the game settings), not part of the course
		const int32 Now = 2 - (int32)Mode->GetAssist();
		Mode->SetAssist((ESkyAssist)(2 - (((Now + Dir) % 3 + 3) % 3)));
		break;
	}
	case EMenuItem::Opponents:
		bOk = Mode->Edit([Dir](FSkyCourse& C) { C.Opponents = FMath::Clamp(C.Opponents + Dir, 0, SkyCourse::MaxOpponents); }, Errors);
		break;
	case EMenuItem::Skill:
		bOk = Mode->Edit([Dir](FSkyCourse& C) { C.Skill = FMath::Clamp(FMath::RoundToDouble((C.Skill + Dir * 0.1) * 10.0) / 10.0, 0.3, 1.2); }, Errors);
		break;
	case EMenuItem::BranchLanes:
		if (bBranch) bOk = Mode->Edit([&](FSkyCourse& C) { FSkyBranch& B = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx].Branches[O.BranchIdx]; B.Lanes = FMath::Clamp(B.Lanes + Dir, 1, 4); }, Errors);
		break;
	case EMenuItem::BranchAngle:
		if (bBranch) bOk = Mode->Edit([&](FSkyCourse& C) { FSkyBranch& B = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx].Branches[O.BranchIdx]; B.Angle = FMath::Clamp(StepSnap(B.Angle, Dir, 5, -45, 45), -45.0, 45.0); }, Errors);
		break;
	case EMenuItem::BranchLaps:
	{
		const int32 Laps = FMath::Max(1, Mode->GetCourse().Laps);
		LapSel = FMath::Clamp(LapSel + Dir, 1, Laps);
		break;
	}
	case EMenuItem::Gate:
		if (bBranch) bOk = Mode->Edit([&](FSkyCourse& C) { FSkyPiece& S = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx]; S.Gate = (ESkyGate)((((int32)S.Gate + Dir) % 3 + 3) % 3); }, Errors);
		break;
	case EMenuItem::MergeLength:
		if (bBranch) bOk = Mode->Edit([&](FSkyCourse& C) { FSkyPiece& S = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx]; S.MergeLength = StepSnap(S.MergeLength, Dir, 5, 15, 80); }, Errors);
		break;
	case EMenuItem::MergeLanes:
		if (bBranch) bOk = Mode->Edit([&](FSkyCourse& C) { FSkyPiece& S = C.Seqs[O.ParentSeq].Pieces[O.PieceIdx]; S.MergeLanes = (S.MergeLanes + Dir + 5) % 5; }, Errors);
		break;
	default: break;
	}
	if (!bOk) ToastErrors(Errors.Num() > 0 ? Errors : TArray<FString>{ FString(What) }, What);
}

void FSkyCourseBuilderImpl::HandleLoad(const FIn& In)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const int32 N = LoadList.Num();
	if (N > 0)
	{
		if (In.bUp) LoadSel = (LoadSel + N - 1) % N;
		if (In.bDown) LoadSel = (LoadSel + 1) % N;
		LoadSel = FMath::Clamp(LoadSel, 0, N - 1);
		if (In.bA)
		{
			FString Err;
			const FString Name = LoadList[LoadSel];
			if (Mode->LoadCourse(Name, Err)) { P->EditSeq = 0; CloseScreens(); Toast(TEXT("Loaded"), Name); }
			else Toast(TEXT("Can't load that course"), Err.Left(140), true);
		}
	}
	if (In.bB || In.bX || In.bMenu) Screen = EBuilderScreen::Menu;
}

// ---------------------------------------------------------------------------------------------- the name box

static const TCHAR* GWheel = TEXT("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -_");

void FSkyCourseBuilderImpl::DoNameConfirm()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const FString Safe = SkyCourse::SafeName(NameText);
	if (Safe.IsEmpty()) { Toast(TEXT("Give it a name"), TEXT("letters, digits, spaces, dashes and underscores"), true); return; }
	if (bNameIsSave)
	{
		FString Err;
		if (Mode->SaveCourse(Safe, Err)) { CloseScreens(); Toast(TEXT("Saved"), Safe); }
		else Toast(TEXT("Can't save"), Err.Left(140), true);
	}
	else
	{
		TArray<FString> Errors;
		if (Mode->Edit([&Safe](FSkyCourse& C) { C.Name = Safe; }, Errors)) { CloseScreens(); Toast(TEXT("Renamed"), Safe); }
		else ToastErrors(Errors, TEXT("Can't rename"));
	}
}

void FSkyCourseBuilderImpl::HandleName(const FIn& In, APlayerController* PC, float Dt)
{
	const int32 WheelN = FCString::Strlen(GWheel);
	// the letter being turned is the last one in the box
	auto Wheel = [&](int32 Delta)
	{
		if (NameText.IsEmpty()) { NameText.AppendChar(GWheel[0]); NameWheel = 0; return; }
		const int32 At = FCString::Strchr(GWheel, NameText.Right(1)[0]) ? (int32)(FCString::Strchr(GWheel, NameText.Right(1)[0]) - GWheel) : 0;
		NameWheel = ((At + Delta) % WheelN + WheelN) % WheelN;
		NameText.RemoveAt(NameText.Len() - 1);
		NameText.AppendChar(GWheel[NameWheel]);
	};
	if (In.bUp) Wheel(+1);
	if (In.bDown) Wheel(-1);
	if (In.bRB) Wheel(+10);
	if (In.bLB) Wheel(-10);
	if (In.bRight && NameText.Len() < 48)
	{
		// the next letter starts where it's most likely: lower case after a letter, upper case after a space or at the start
		const TCHAR Last = NameText.IsEmpty() ? TEXT(' ') : NameText.Right(1)[0];
		NameText.AppendChar(FChar::IsAlpha(Last) ? TEXT('a') : TEXT('A'));
	}
	if (In.bLeft && NameText.Len() > 0) NameText.RemoveAt(NameText.Len() - 1);
	if (In.bBackspace && NameText.Len() > 0) NameText.RemoveAt(NameText.Len() - 1);
	if (In.bA) { DoNameConfirm(); return; }
	if (In.bMenu || In.bPadB) { Screen = EBuilderScreen::Menu; return; }
	// the keyboard types
	if (PC)
	{
		const bool bShift = PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift);
		const FKey Letters[26] = { EKeys::A, EKeys::B, EKeys::C, EKeys::D, EKeys::E, EKeys::F, EKeys::G, EKeys::H, EKeys::I, EKeys::J, EKeys::K, EKeys::L, EKeys::M,
			EKeys::N, EKeys::O, EKeys::P, EKeys::Q, EKeys::R, EKeys::S, EKeys::T, EKeys::U, EKeys::V, EKeys::W, EKeys::X, EKeys::Y, EKeys::Z };
		const FKey Digits[10] = { EKeys::Zero, EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine };
		auto Add = [this](TCHAR C) { if (NameText.Len() < 48) NameText.AppendChar(C); };
		for (int32 i = 0; i < 26; ++i)
			if (Edge(PC, Letters[i], Dt, true, 0.45, 0.07, true)) Add((TCHAR)((bShift ? TEXT('A') : TEXT('a')) + i));
		for (int32 i = 0; i < 10; ++i)
			if (Edge(PC, Digits[i], Dt, false, 0.4, 0.08, true)) Add((TCHAR)(TEXT('0') + i));
		if (Edge(PC, EKeys::SpaceBar, Dt, true, 0.45, 0.07, true)) Add(TEXT(' '));
		if (Edge(PC, EKeys::Hyphen, Dt, true, 0.45, 0.07, true)) Add(bShift ? TEXT('_') : TEXT('-'));
		if (Edge(PC, EKeys::Underscore, Dt, false, 0.4, 0.08, true)) Add(TEXT('_'));
	}
}

// ---------------------------------------------------------------------------------------------- the Garage stand-in

FString FSkyCourseBuilderImpl::MapName(const FString& Path) const
{
	const FString Base = FPaths::GetBaseFilename(Path);
	if (Base.Contains(TEXT("mode=build"))) return TEXT("Course Builder");
	if (Base == TEXT("SkyCityMashup") || Base == TEXT("SkyCity")) return TEXT("Sky City");
	if (Base == TEXT("McGregorNight")) return TEXT("McGregor Night");
	if (Base == TEXT("McGregor")) return TEXT("McGregor");
	return Base;
}

void FSkyCourseBuilderImpl::HandleGarage(const FIn& In)
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	// the car's own Garage (Menu) can't open while the car isn't possessed: this lists the same maps, so a player can leave
	const ASkysterCar* Car = Mode->GetCar();
	const TArray<FName> Maps = Car ? Car->Maps : TArray<FName>();
	const int32 N = Maps.Num() + 1;   // + "back to building"
	if (In.bUp) GarageSel = (GarageSel + N - 1) % N;
	if (In.bDown) GarageSel = (GarageSel + 1) % N;
	GarageSel = FMath::Clamp(GarageSel, 0, N - 1);
	if (In.bB || In.bMenu || In.bX) { CloseScreens(); return; }
	if (In.bA)
	{
		if (GarageSel >= Maps.Num()) { CloseScreens(); return; }
		const FString Entry = Maps[GarageSel].ToString();
		const FString Here = UGameplayStatics::GetCurrentLevelName(Mode, true) + (SkyCourse::IsBuildMode(Mode->GetWorld()) ? TEXT("?mode=build") : TEXT(""));
		if (FPaths::GetBaseFilename(Entry) == Here) { Toast(TEXT("You're already here"), FString(), false); return; }
		FString Level = Entry, Options;
		Entry.Split(TEXT("?"), &Level, &Options);
		Toast(TEXT("Opening"), MapName(Entry));
		UGameplayStatics::OpenLevel(Mode, FName(Level.IsEmpty() ? Entry : Level), true, Options);
	}
}

// ---------------------------------------------------------------------------------------------- state for tests

FString FSkyCourseBuilderImpl::StateJson() const
{
	TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
	ASkyCourseMode* Mode = ModeRef.Get();
	O->SetStringField(TEXT("piece"), PieceLabel(P->Pending.Type));
	O->SetNumberField(TEXT("paletteIndex"), P->PaletteIndex);
	O->SetNumberField(TEXT("editSeq"), P->EditSeq);
	O->SetBoolField(TEXT("fits"), bFits);
	O->SetStringField(TEXT("fitReason"), FitReason);
	O->SetNumberField(TEXT("fitMs"), FitMs);
	O->SetNumberField(TEXT("fitMsMax"), FitMsMax);
	O->SetNumberField(TEXT("fitCount"), FitCount);
	O->SetBoolField(TEXT("closed"), bClosed);
	O->SetNumberField(TEXT("cursorLanes"), CursorLanes);
	TArray<TSharedPtr<FJsonValue>> Cp;
	Cp.Add(MakeShared<FJsonValueNumber>(Cursor.P.X)); Cp.Add(MakeShared<FJsonValueNumber>(Cursor.P.Y)); Cp.Add(MakeShared<FJsonValueNumber>(Cursor.P.Z));
	O->SetArrayField(TEXT("cursor"), Cp);
	O->SetNumberField(TEXT("cursorHeading"), FMath::RadiansToDegrees(FMath::Atan2(Cursor.F.Y, Cursor.F.X)));
	TSharedRef<FJsonObject> Pend = MakeShared<FJsonObject>();
	EF F[3];
	FieldsFor(P->Pending.Type, F);
	for (int32 i = 0; i < 3; ++i)
		if (F[i] != EF::None) Pend->SetStringField(InfoFor(P->Pending.Type, F[i]).Label, FormatField(P->Pending, F[i]));
	O->SetObjectField(TEXT("pending"), Pend);
	O->SetNumberField(TEXT("secondField"), SecondField);
	const TCHAR* Names[] = { TEXT("build"), TEXT("menu"), TEXT("load"), TEXT("name"), TEXT("garage") };
	O->SetStringField(TEXT("screen"), Names[(int32)Screen]);
	O->SetNumberField(TEXT("menuSel"), MenuSel);
	O->SetStringField(TEXT("name"), NameText);
	if (Mode)
	{
		O->SetNumberField(TEXT("laneWidth"), Mode->GetCourse().LaneWidth);
		O->SetBoolField(TEXT("catchUp"), Mode->GetCourse().bCatchUp);
		O->SetNumberField(TEXT("assist"), (int32)Mode->GetAssist());
	}
	TSharedRef<FJsonObject> Cam = MakeShared<FJsonObject>();
	Cam->SetNumberField(TEXT("yaw"), YawS); Cam->SetNumberField(TEXT("pitch"), PitchS); Cam->SetNumberField(TEXT("dist"), DistS);
	O->SetObjectField(TEXT("camera"), Cam);
	TArray<TSharedPtr<FJsonValue>> Ts;
	for (const FToast& T : Toasts) Ts.Add(MakeShared<FJsonValueString>(T.Title + (T.Sub.IsEmpty() ? FString() : TEXT(" | ") + T.Sub)));
	O->SetArrayField(TEXT("toasts"), Ts);
	if (Mode)
	{
		O->SetNumberField(TEXT("revision"), Mode->Revision());
		O->SetNumberField(TEXT("seqs"), Mode->GetCourse().Seqs.Num());
		O->SetStringField(TEXT("seqLabel"), SeqLabel(Mode->GetCourse(), Mode->GetBaked(), P->EditSeq));
		O->SetBoolField(TEXT("driving"), Mode->IsDriving());
	}
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(O, W);
	return Out;
}
