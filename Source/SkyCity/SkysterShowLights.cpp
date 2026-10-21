#include "SkysterShowLights.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/LocalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "SkysterCar.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogShowLights, Log, All);

ASkysterShowLights::ASkysterShowLights()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;   // after the car has moved this frame
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Movable);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (Cube.Succeeded()) StripMesh = Cube.Object;
}

bool ASkysterShowLights::NameHasAny(const FString& Name, const TArray<FString>& Words)
{
	for (const FString& W : Words)
	{
		if (!W.IsEmpty() && Name.Contains(W)) return true;
	}
	return false;
}

void ASkysterShowLights::BeginPlay()
{
	Super::BeginPlay();
	if (bGlow)
	{
		GatherBars();
		BuildStrips();
	}
	if (bFloods) GatherFloods();
	FloodShown = -1.f;
	ApplyFloods(FVector::ZeroVector, false, 0.f);   // off until the car triggers them
	Summary = FString::Printf(TEXT("%d bars (%d pieces, %d strip bars), %d glow lights, %d flood lights, %d flood meshes"),
		Bars.Num(), NumPieces, NumStripBars, NumGlowLights, Floods.Num(), FloodMeshes.Num());
	UE_LOG(LogShowLights, Log, TEXT("SkysterShowLights %s: %s; fleet line %s -> %s"), *GetName(), *Summary, *LineStart.ToString(), *LineEnd.ToString());
}

// ---------------------------------------------------------------------------------------------- finding the bars

bool ASkysterShowLights::IsLEDSlot(const UPrimitiveComponent* C, int32 Slot) const
{
	for (UMaterialInterface* M = C->GetMaterial(Slot); M; )
	{
		if (LEDMaterials.Contains(M)) return true;
		const UMaterialInstance* MI = Cast<UMaterialInstance>(M);
		M = MI ? MI->Parent.Get() : nullptr;
	}
	const TArray<FName> Names = C->GetMaterialSlotNames();
	return Names.IsValidIndex(Slot) && NameHasAny(Names[Slot].ToString(), LEDSlotNames);
}

int32 ASkysterShowLights::AddBar(UPrimitiveComponent* C, const FString& Name, const FBox& Box, bool bAllSlots)
{
	FBar Bar;
	Bar.Name = Name;
	Bar.Comp = C;
	Bar.Box = Box;
	TMap<UMaterialInterface*, UMaterialInstanceDynamic*> ByMat;
	for (int32 s = 0; s < C->GetNumMaterials(); ++s)
	{
		if (!bAllSlots && !IsLEDSlot(C, s)) continue;
		UMaterialInterface* M = C->GetMaterial(s);
		float Base = 0.f;
		if (!M || !M->GetScalarParameterValue(FHashedMaterialParameterInfo(GlowParam), Base)) continue;
		UMaterialInstanceDynamic*& Mid = ByMat.FindOrAdd(M);
		if (!Mid)
		{
			Mid = UMaterialInstanceDynamic::Create(M, this);
			Made.Add(Mid);
			Bar.Mats.Add({ Mid, Base });
		}
		C->SetMaterial(s, Mid);
	}
	if (Bar.Mats.Num() == 0) return INDEX_NONE;
	if (bDebug) UE_LOG(LogShowLights, Log, TEXT("  bar %d: %s at %s"), Bars.Num(), *Name, *Box.GetCenter().ToString());
	return Bars.Add(MoveTemp(Bar));
}

UStaticMeshComponent* ASkysterShowLights::NewMeshPart(UStaticMesh* Mesh, const FTransform& X, bool bShadow)
{
	UStaticMeshComponent* S = NewObject<UStaticMeshComponent>(this, NAME_None, RF_Transient);
	S->SetMobility(EComponentMobility::Movable);
	S->SetStaticMesh(Mesh);
	S->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	S->SetGenerateOverlapEvents(false);
	S->SetCanEverAffectNavigation(false);
	S->SetCastShadow(bShadow);
	S->SetupAttachment(RootComponent);
	S->RegisterComponent();
	S->SetWorldTransform(X);
	Made.Add(S);
	return S;
}

ULocalLightComponent* ASkysterShowLights::MakeGlowLight(const FVector& At, float Radius)
{
	UPointLightComponent* L = NewObject<UPointLightComponent>(this, NAME_None, RF_Transient);
	L->SetMobility(EComponentMobility::Movable);
	L->SetIntensityUnits(ELightUnits::Lumens);
	L->SetAttenuationRadius(Radius);
	L->SetLightColor(GlowLightColor);
	L->SetCastShadows(false);
	L->SetIntensity(0.f);
	L->SetVisibility(false);
	L->SetupAttachment(RootComponent);
	L->RegisterComponent();
	L->SetWorldLocation(At);
	Made.Add(L);
	++NumGlowLights;
	return L;
}

void ASkysterShowLights::GatherBars()
{
	const FHashedMaterialParameterInfo Param(GlowParam);
	auto HasGlowSlot = [&](const UPrimitiveComponent* C)
	{
		for (int32 s = 0; s < C->GetNumMaterials(); ++s)
		{
			float V;
			if (IsLEDSlot(C, s) && C->GetMaterial(s) && C->GetMaterial(s)->GetScalarParameterValue(Param, V)) return true;
		}
		return false;
	};
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* A = *It;
		if (A == this || A->IsA<APawn>()) continue;
		const bool bTagged = A->ActorHasTag(ReactiveTag);
		TInlineComponentArray<UStaticMeshComponent*> Comps(A);
		TArray<int32> Mine;
		for (UStaticMeshComponent* C : Comps)
		{
			UStaticMesh* Mesh = C->GetStaticMesh();
			if (!Mesh || !C->IsRegistered()) continue;
			const FString MeshName = Mesh->GetName();
			if (!bTagged && !NameHasAny(MeshName, ReactiveMeshNames)) continue;
			if (!HasGlowSlot(C)) continue;
			const bool bPieceLight = PieceLightLumens > 0.f && NameHasAny(MeshName, PieceLightMeshes);
			if (UInstancedStaticMeshComponent* ISM = Cast<UInstancedStaticMeshComponent>(C))
			{
				// one HISM holds every piece: copy each instance into its own component so each bar glows on its own,
				// and hide the original in game (it keeps its collision)
				const int32 N = ISM->GetInstanceCount();
				TArray<FTransform> Xs;
				bool bOk = N > 0;
				for (int32 i = 0; i < N && bOk; ++i)
				{
					FTransform X;
					ISM->GetInstanceTransform(i, X, true);
					bOk = Mesh->GetBoundingBox().TransformBy(X).GetSize().GetMax() <= MaxPieceSize;
					Xs.Add(X);
				}
				if (!bOk)
				{
					UE_LOG(LogShowLights, Warning, TEXT("SkysterShowLights: %s on %s is bigger than MaxPieceSize, not reactive"), *MeshName, *A->GetName());
					continue;
				}
				for (int32 i = 0; i < N; ++i)
				{
					UStaticMeshComponent* S = NewMeshPart(Mesh, Xs[i], ISM->CastShadow);
					for (int32 s = 0; s < ISM->GetNumMaterials(); ++s) S->SetMaterial(s, ISM->GetMaterial(s));
					const int32 Id = AddBar(S, FString::Printf(TEXT("%s #%d"), *MeshName, i), Mesh->GetBoundingBox().TransformBy(Xs[i]), false);
					if (Id == INDEX_NONE) continue;
					++NumPieces;
					if (bPieceLight) Bars[Id].Lights.Add({ MakeGlowLight(Xs[i].TransformPosition(PieceLightOffset), PieceLightRadius), PieceLightLumens, true });
					Mine.Add(Id);
				}
				ISM->SetHiddenInGame(true);
			}
			else
			{
				const FBox Box = C->Bounds.GetBox();
				if (Box.GetSize().GetMax() > MaxPieceSize) continue;
				const int32 Id = AddBar(C, FString::Printf(TEXT("%s (%s)"), *MeshName, *A->GetName()), Box, false);
				if (Id == INDEX_NONE) continue;
				++NumPieces;
				if (bPieceLight) Bars[Id].Lights.Add({ MakeGlowLight(C->GetComponentTransform().TransformPosition(PieceLightOffset), PieceLightRadius), PieceLightLumens, true });
				Mine.Add(Id);
			}
		}
		// lights already on a reactive actor glow with the nearest of its bars
		if (Mine.Num())
		{
			TInlineComponentArray<ULocalLightComponent*> Lights(A);
			for (ULocalLightComponent* L : Lights)
			{
				int32 Best = Mine[0];
				double BestD = TNumericLimits<double>::Max();
				for (int32 Id : Mine)
				{
					const double D = Bars[Id].Box.ComputeSquaredDistanceToPoint(L->GetComponentLocation());
					if (D < BestD) { BestD = D; Best = Id; }
				}
				Bars[Best].Lights.Add({ L, L->Intensity, false });
			}
		}
	}
}

void ASkysterShowLights::BuildStrips()
{
	if (!Strips.Num()) return;
	float Base = 0.f;
	if (!StripMesh || !StripMaterial || !StripMaterial->GetScalarParameterValue(FHashedMaterialParameterInfo(GlowParam), Base))
	{
		UE_LOG(LogShowLights, Warning, TEXT("SkysterShowLights: no StripMesh / StripMaterial with \"%s\": the LED strips won't react"), *GlowParam.ToString());
		return;
	}
	for (int32 si = 0; si < Strips.Num(); ++si)
	{
		const TArray<FVector>& P = Strips[si].Points;
		if (P.Num() < 2) continue;
		TArray<double> Cum;
		Cum.Add(0.0);
		for (int32 i = 1; i < P.Num(); ++i) Cum.Add(Cum.Last() + FVector::Dist(P[i - 1], P[i]));
		const double Len = Cum.Last();
		if (Len < 10.0) continue;
		auto At = [&](double D)
		{
			int32 k = 0;
			while (k < P.Num() - 2 && Cum[k + 1] < D) ++k;
			const double T = FMath::Clamp((D - Cum[k]) / FMath::Max(Cum[k + 1] - Cum[k], 1e-6), 0.0, 1.0);
			return FMath::Lerp(P[k], P[k + 1], T);
		};
		const int32 N = FMath::Max(1, FMath::RoundToInt(Len / FMath::Max(StripSegment, 10.f)));
		const int32 First = Bars.Num();
		for (int32 k = 0; k < N; ++k)
		{
			const FVector A0 = At(Len * k / N), B0 = At(Len * (k + 1) / N);
			const FVector D = B0 - A0;
			const double L = FMath::Max(D.Size(), 1.0);
			const FRotator R = FRotationMatrix::MakeFromXZ(D, FVector::UpVector).Rotator();
			const FVector Up = FRotationMatrix(R).GetUnitAxis(EAxis::Z);
			const FVector Mid = (A0 + B0) * 0.5 + Up * (StripLift + StripThickness * 0.5);
			// bars butt up end to end (1 cm overlap); each a little wider and taller than the painted ribbon under it
			UStaticMeshComponent* S = NewMeshPart(StripMesh, FTransform(R, Mid, FVector((L + 1.0) / 100.0, Strips[si].Width / 100.0, StripThickness / 100.0)), false);
			S->SetMaterial(0, StripMaterial);
			FBox Box(ForceInit);
			Box += A0;
			Box += B0;
			const int32 Id = AddBar(S, FString::Printf(TEXT("strip %d/%d"), si, k), Box.ExpandBy(Strips[si].Width * 0.5), true);
			if (Id == INDEX_NONE) continue;
			Bars[Id].bSegment = true;
			Bars[Id].A = A0;
			Bars[Id].B = B0;
			++NumStripBars;
		}
		// red lights along the strip that come on near the car, each glowing with the bar under it
		if (StripLightSpacing > 0.f && StripLightLumens > 0.f && Bars.Num() > First)
		{
			const int32 NL = FMath::Max(1, FMath::FloorToInt(Len / StripLightSpacing));
			for (int32 j = 0; j < NL; ++j)
			{
				const double D = (j + 0.5) * Len / NL;
				const int32 Id = FMath::Clamp(First + FMath::FloorToInt(D / Len * N), First, Bars.Num() - 1);
				Bars[Id].Lights.Add({ MakeGlowLight(At(D) + FVector(0, 0, StripLightHeight), StripLightRadius), StripLightLumens, true });
			}
		}
	}
}

void ASkysterShowLights::GatherFloods()
{
	const FHashedMaterialParameterInfo Param(GlowParam);
	TArray<int32> WantFollow;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* A = *It;
		const bool bFlood = A->ActorHasTag(FloodTag), bBeam = A->ActorHasTag(FloodBeamTag);
		if (A == this || (!bFlood && !bBeam)) continue;
		const bool bTrack = A->ActorHasTag(TrackTag);
		TInlineComponentArray<ULocalLightComponent*> Lights(A);
		for (ULocalLightComponent* L : Lights)
		{
			FFloodLight F;
			F.Light = L;
			F.On = L->Intensity;                       // the placed intensity is the lit one
			F.Base = F.Cur = L->GetComponentQuat();
			F.bTrack = bTrack && L->Mobility == EComponentMobility::Movable;
			Floods.Add(F);
		}
		TInlineComponentArray<UStaticMeshComponent*> Meshes(A);
		for (UStaticMeshComponent* C : Meshes)
		{
			FFloodMesh FM;
			FM.Comp = C;
			FM.bBeam = bBeam;
			const TArray<FName> Names = C->GetMaterialSlotNames();
			TMap<UMaterialInterface*, UMaterialInstanceDynamic*> ByMat;
			for (int32 s = 0; s < C->GetNumMaterials(); ++s)
			{
				if (!bBeam && !(Names.IsValidIndex(s) && NameHasAny(Names[s].ToString(), FloodLensSlots))) continue;
				UMaterialInterface* M = C->GetMaterial(s);
				float Base = 0.f;
				if (!M || !M->GetScalarParameterValue(Param, Base)) continue;
				UMaterialInstanceDynamic*& Mid = ByMat.FindOrAdd(M);
				if (!Mid)
				{
					Mid = UMaterialInstanceDynamic::Create(M, this);
					Made.Add(Mid);
					FM.Mats.Add({ Mid, Base });
				}
				C->SetMaterial(s, Mid);
			}
			if (!FM.Mats.Num() && !bBeam) continue;
			const int32 Id = FloodMeshes.Add(FM);
			if (bBeam && bTrack && C->Mobility == EComponentMobility::Movable) WantFollow.Add(Id);
		}
	}
	// shafts on tracking actors turn with the nearest tracking light (within 10 m)
	for (int32 Id : WantFollow)
	{
		FFloodMesh& FM = FloodMeshes[Id];
		const UPrimitiveComponent* C = FM.Comp.Get();
		double BestD = 1000.0 * 1000.0;
		for (int32 i = 0; i < Floods.Num(); ++i)
		{
			const ULocalLightComponent* L = Floods[i].Light.Get();
			if (!L || !Floods[i].bTrack) continue;
			const double D = FVector::DistSquared(L->GetComponentLocation(), C->GetComponentLocation());
			if (D < BestD) { BestD = D; FM.Follow = i; }
		}
		if (FM.Follow != INDEX_NONE) FM.Offset = Floods[FM.Follow].Base.Inverse() * C->GetComponentQuat();
	}
}

// ---------------------------------------------------------------------------------------------- every frame

void ASkysterShowLights::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Clamp(DeltaSeconds, 0.f, 0.1f);
	APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
	const bool bHaveCar = Pawn != nullptr;
	FVector Car = FVector::ZeroVector, Vel = FVector::ZeroVector;
	if (Pawn)
	{
		Car = Pawn->GetActorLocation();
		if (const ASkysterCar* S = Cast<ASkysterCar>(Pawn))
		{
			Vel = FVector(S->Vel.X * 100.0, -S->Vel.Y * 100.0, S->Vel.Z * 100.0);   // sim m/s -> Unreal cm/s
		}
		else
		{
			Vel = Pawn->GetVelocity();
			if (Vel.IsNearlyZero() && bHavePrev && Dt > 0.f) Vel = (Car - PrevCar) / Dt;
		}
		PrevCar = Car;
		bHavePrev = true;
	}
	if (bGlow && Bars.Num()) UpdateGlow(Dt, Car, bHaveCar);
	if (bFloods)
	{
		if (bHaveCar) UpdateTrigger(Car, Vel);
		UpdateFloods(Dt);
		ApplyFloods(Car, bHaveCar, Dt);
	}
	if (bDebug) DebugDraw(Car);
}

void ASkysterShowLights::UpdateGlow(float Dt, const FVector& Car, bool bHaveCar)
{
	const float KRise = 1.f - FMath::Exp(-Dt / FMath::Max(RiseTime, 0.001f));
	const float KFall = 1.f - FMath::Exp(-Dt / FMath::Max(FallTime, 0.001f));
	const float Far = FMath::Max(FarDist, 1.f), Near = FMath::Min(NearDist, Far - 1.f);
	for (FBar& B : Bars)
	{
		float Target = 0.f;
		if (bHaveCar)
		{
			double D;
			if (B.bSegment)
			{
				FVector P = Car, A = B.A, E = B.B;
				if (bPlanDistance) P.Z = A.Z = E.Z = 0.0;
				D = FMath::PointDistToSegment(P, A, E);
			}
			else
			{
				FVector P = Car;
				if (bPlanDistance) P.Z = FMath::Clamp(P.Z, B.Box.Min.Z, B.Box.Max.Z);
				D = FMath::Sqrt(B.Box.ComputeSquaredDistanceToPoint(P));
			}
			Target = 1.f - FMath::SmoothStep(Near, Far, (float)D);
		}
		B.Glow += (Target - B.Glow) * (Target > B.Glow ? KRise : KFall);
		if (Target == 0.f && B.Glow < 0.001f) B.Glow = 0.f;
		if (FMath::Abs(B.Glow - B.Shown) > 0.003f || (B.Glow == 0.f && B.Shown != 0.f)) ApplyBar(B);
	}
}

void ASkysterShowLights::ApplyBar(FBar& B)
{
	const float K = 1.f + Boost * B.Glow;
	for (const FGlowMat& M : B.Mats)
	{
		if (M.Mid) M.Mid->SetScalarParameterValue(GlowParam, M.Base * K);
	}
	const float LB = AttachedLightBoost < 0.f ? Boost : AttachedLightBoost;
	for (const FGlowLight& G : B.Lights)
	{
		ULocalLightComponent* L = G.Light.Get();
		if (!L) continue;
		if (G.bAuto)
		{
			// the added lights only come on near the car (squared: a pool of red right by it, little further out)
			const bool bOn = B.Glow > 0.05f;
			if (L->IsVisible() != bOn) L->SetVisibility(bOn);
			if (bOn) L->SetIntensity(G.Base * B.Glow * B.Glow);
		}
		else
		{
			L->SetIntensity(G.Base * (1.f + LB * B.Glow));
		}
	}
	B.Shown = B.Glow;
}

void ASkysterShowLights::UpdateTrigger(const FVector& Car, const FVector& Vel)
{
	FVector Dir = LineEnd - LineStart;
	Dir.Z = 0.0;
	const double Len = Dir.Size();
	if (Len < 100.0) return;
	Dir /= Len;
	const FVector Rel = Car - LineStart;
	const double Along = Rel.X * Dir.X + Rel.Y * Dir.Y;
	const double Side = Rel.X * Dir.Y - Rel.Y * Dir.X;
	const double Height = Car.Z - FMath::Lerp(LineStart.Z, LineEnd.Z, FMath::Clamp(Along / Len, 0.0, 1.0));
	const double VAlong = Vel.X * Dir.X + Vel.Y * Dir.Y;
	const double V2 = Vel.Size2D();
	CarFrame = FVector(Along, Side, Height);
	CarAlongSpeed = VAlong;
	const bool bInCorridor = Along > -RearmBefore && Along < Len + RearmPast && FMath::Abs(Side) < RearmHalfWidth;
	if (!bArmed && !bInCorridor)
	{
		bArmed = true;
		UE_LOG(LogShowLights, Log, TEXT("SkysterShowLights: car left the fleet line corridor, floods re-armed"));
	}
	const bool bInZone = Along >= TriggerFrom && Along <= TriggerTo && FMath::Abs(Side) <= TriggerHalfWidth
		&& Height <= TriggerMaxHeight && Height > -500.0;
	if (bArmed && bInZone && VAlong >= MinSpeed && V2 > 1.0 && VAlong / V2 >= MinAlign)
	{
		bArmed = false;
		TriggerFloods();
		UE_LOG(LogShowLights, Log, TEXT("SkysterShowLights: floods triggered (car %.1f m along the fleet line, %.1f m to the side, %.1f m/s along it)"),
			Along / 100.0, Side / 100.0, VAlong / 100.0);
	}
}

void ASkysterShowLights::TriggerFloods()
{
	++TriggerCount;
	FloodState = EFlood::FadeIn;    // from wherever the level is now (a re-trigger while lit just starts the hold again)
	HoldT = 0.f;
}

void ASkysterShowLights::StopFloods()
{
	if (FloodState != EFlood::Off) FloodState = EFlood::FadeOut;
}

FString ASkysterShowLights::GetFloodState() const
{
	switch (FloodState)
	{
	case EFlood::FadeIn: return TEXT("fade_in");
	case EFlood::Hold: return TEXT("hold");
	case EFlood::FadeOut: return TEXT("fade_out");
	default: return TEXT("off");
	}
}

void ASkysterShowLights::UpdateFloods(float Dt)
{
	switch (FloodState)
	{
	case EFlood::FadeIn:
		FloodLevel = FadeInTime > 0.f ? FMath::Min(1.f, FloodLevel + Dt / FadeInTime) : 1.f;
		if (FloodLevel >= 1.f) { FloodState = EFlood::Hold; HoldT = 0.f; }
		break;
	case EFlood::Hold:
		FloodLevel = 1.f;
		HoldT += Dt;
		if (HoldT >= HoldTime) FloodState = EFlood::FadeOut;
		break;
	case EFlood::FadeOut:
		FloodLevel = FadeOutTime > 0.f ? FMath::Max(0.f, FloodLevel - Dt / FadeOutTime) : 0.f;
		if (FloodLevel <= 0.f) FloodState = EFlood::Off;
		break;
	default:
		FloodLevel = 0.f;
		break;
	}
	FloodOut = FloodLevel * FloodLevel * (3.f - 2.f * FloodLevel);   // eased both ways
}

void ASkysterShowLights::ApplyFloods(const FVector& Car, bool bHaveCar, float Dt)
{
	const bool bChanged = FMath::Abs(FloodOut - FloodShown) > 0.0005f || (FloodOut == 0.f && FloodShown != 0.f);
	const bool bVisible = FloodOut > 0.0005f;
	const bool bTracking = bTrackCar && bHaveCar && bVisible;
	if (!bChanged && !bTracking) return;
	const float KTrack = 1.f - FMath::Exp(-Dt * FMath::Max(TrackRate, 0.f));
	const double MaxA = FMath::DegreesToRadians(FMath::Max(TrackMaxAngle, 0.f));
	for (FFloodLight& F : Floods)
	{
		ULocalLightComponent* L = F.Light.Get();
		if (!L) continue;
		if (bChanged)
		{
			L->SetIntensity(F.On * FloodScale * FloodOut);
			if (L->IsVisible() != bVisible) L->SetVisibility(bVisible);
		}
		if (!F.bTrack) continue;
		FQuat Want = F.Base;
		if (bTracking)
		{
			const FVector To = (Car + FVector(0, 0, TrackAimHeight) - L->GetComponentLocation()).GetSafeNormal();
			const FVector From = F.Base.GetForwardVector();
			if (!To.IsNearlyZero())
			{
				const double Ang = FMath::Acos(FMath::Clamp(FVector::DotProduct(From, To), -1.0, 1.0));
				const FQuat Delta = FQuat::FindBetweenNormals(From, To);
				const FQuat Lim = (Ang > MaxA && Ang > 1e-4) ? FQuat::Slerp(FQuat::Identity, Delta, MaxA / Ang) : Delta;
				Want = Lim * F.Base;
			}
		}
		F.Cur = bVisible ? FQuat::Slerp(F.Cur, Want, KTrack) : F.Base;
		L->SetWorldRotation(F.Cur);
	}
	for (FFloodMesh& FM : FloodMeshes)
	{
		UPrimitiveComponent* C = FM.Comp.Get();
		if (!C) continue;
		if (bChanged)
		{
			const float K = FM.bBeam ? FloodOut : LensOffShare + (1.f - LensOffShare) * FloodOut;
			for (const FGlowMat& M : FM.Mats)
			{
				if (M.Mid) M.Mid->SetScalarParameterValue(GlowParam, M.Base * K);
			}
			if (FM.bBeam && C->IsVisible() != bVisible) C->SetVisibility(bVisible);
		}
		if (Floods.IsValidIndex(FM.Follow)) C->SetWorldRotation(Floods[FM.Follow].Cur * FM.Offset);
	}
	FloodShown = FloodOut;
}

void ASkysterShowLights::DebugDraw(const FVector& Car) const
{
#if ENABLE_DRAW_DEBUG
	UWorld* W = GetWorld();
	FVector Dir = LineEnd - LineStart;
	Dir.Z = 0.0;
	const double Len = Dir.Size();
	if (W && Len > 100.0)
	{
		Dir /= Len;
		const FVector Side(Dir.Y, -Dir.X, 0.0);
		auto Rect = [&](double A0, double A1, double H, const FColor& Col)
		{
			const FVector Z(0, 0, 30);
			const FVector P[4] = { LineStart + Dir * A0 + Side * H + Z, LineStart + Dir * A1 + Side * H + Z,
								   LineStart + Dir * A1 - Side * H + Z, LineStart + Dir * A0 - Side * H + Z };
			for (int32 i = 0; i < 4; ++i) DrawDebugLine(W, P[i], P[(i + 1) % 4], Col, false, -1.f, 0, 8.f);
		};
		Rect(TriggerFrom, TriggerTo, TriggerHalfWidth, bArmed ? FColor::Green : FColor::Red);
		Rect(-RearmBefore, Len + RearmPast, RearmHalfWidth, FColor::Yellow);
	}
	if (GEngine)
	{
		float MaxGlow = 0.f;
		for (const FBar& B : Bars) MaxGlow = FMath::Max(MaxGlow, B.Glow);
		GEngine->AddOnScreenDebugMessage((uint64)GetUniqueID(), 0.f, FColor::Red,
			FString::Printf(TEXT("ShowLights: floods %s %.2f (%s, %d triggers) | car along %.1f m side %.1f m up %.1f m, %.1f m/s | max bar glow %.2f | %s"),
				*GetFloodState(), FloodOut, bArmed ? TEXT("armed") : TEXT("not armed"), TriggerCount, CarFrame.X / 100.0, CarFrame.Y / 100.0,
				CarFrame.Z / 100.0, CarAlongSpeed / 100.0, MaxGlow, *Summary));
	}
#endif
}

// ---------------------------------------------------------------------------------------------- test hooks

FString ASkysterShowLights::GetBarName(int32 I) const
{
	return Bars.IsValidIndex(I) ? Bars[I].Name : FString();
}

FVector ASkysterShowLights::GetBarLocation(int32 I) const
{
	if (!Bars.IsValidIndex(I)) return FVector::ZeroVector;
	const FBar& B = Bars[I];
	return B.bSegment ? (B.A + B.B) * 0.5 : B.Box.GetCenter();
}

float ASkysterShowLights::GetBarGlow(int32 I) const
{
	return Bars.IsValidIndex(I) ? Bars[I].Glow : 0.f;
}

float ASkysterShowLights::GetBarBrightness(int32 I) const
{
	if (!Bars.IsValidIndex(I) || !Bars[I].Mats.Num()) return 0.f;
	return Bars[I].Mats[0].Base * (1.f + Boost * Bars[I].Shown);
}

float ASkysterShowLights::GetFloodLightIntensity(int32 I) const
{
	const ULocalLightComponent* L = Floods.IsValidIndex(I) ? Floods[I].Light.Get() : nullptr;
	return L ? L->Intensity : 0.f;
}
