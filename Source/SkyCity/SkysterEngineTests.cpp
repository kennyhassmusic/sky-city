#include "SkysterEngineTests.h"

#include "Camera/PlayerCameraManager.h"
#include "Components/AudioComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

DEFINE_LOG_CATEGORY_STATIC(LogSkyTests, Log, All);

// the quad is Unreal's /Engine/BasicShapes/Plane (100 cm, facing +Z); SC_JetCone is 1 m long toward local -X with a
// 9 cm base radius (Scripts/unreal/blender_fx_kit.py)
static constexpr float QUAD = 100.f;
static constexpr float CONE_R = 9.f;
static constexpr float SOUND_CMS = 34300.f;

float USkysterTestShakePattern::Amplitude = 0.f;

ASkysterEngineTests::ASkysterEngineTests()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	auto Cone = [this](const TCHAR* Name) {
		UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Root);
		C->SetMobility(EComponentMobility::Movable);
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->TranslucencySortPriority = 2;
		C->SetVisibility(false);
		return C;
	};
	PlumeOuter = Cone(TEXT("PlumeOuter"));
	PlumeCore = Cone(TEXT("PlumeCore"));

	auto Fx = [this](const TCHAR* Name, int32 Sort) {
		UInstancedStaticMeshComponent* C = CreateDefaultSubobject<UInstancedStaticMeshComponent>(Name);
		C->SetupAttachment(Root);
		C->SetMobility(EComponentMobility::Movable);
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->TranslucencySortPriority = Sort;
		C->SetVisibility(false);
		return C;
	};
	SmokeFx = Fx(TEXT("SmokeFx"), -1);   // smoke under the additive plume and flames
	FireFx = Fx(TEXT("FireFx"), 1);

	ExitLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("ExitLight"));
	ExitLight->SetupAttachment(Root);
	ExitLight->SetMobility(EComponentMobility::Movable);
	ExitLight->SetUsingAbsoluteLocation(true);
	ExitLight->SetIntensityUnits(ELightUnits::Candelas);
	ExitLight->SetIntensity(0.f);
	ExitLight->SetLightColor(FLinearColor(1.0f, 0.55f, 0.22f));
	ExitLight->SetAttenuationRadius(40000.f);
	ExitLight->SetCastShadows(false);
	ExitLight->SetVisibility(false);

	Roar = CreateDefaultSubobject<UAudioComponent>(TEXT("Roar"));
	Roar->SetupAttachment(Root);
	Roar->SetUsingAbsoluteLocation(true);
	Roar->bAutoActivate = false;
}

void ASkysterEngineTests::BeginPlay()
{
	Super::BeginPlay();
	auto LoadM = [](TObjectPtr<UMaterialInterface>& M, const TCHAR* Path) { if (!M) M = LoadObject<UMaterialInterface>(nullptr, Path); };
	LoadM(JetMaterial, TEXT("/Game/SkyCity/Pickups/Materials/MI_Jet.MI_Jet"));
	LoadM(SmokeMaterial, TEXT("/Game/SkyCity/FX/M_SkyVapor.M_SkyVapor"));
	LoadM(FireMaterial, TEXT("/Game/SkyCity/FX/M_SkyFire.M_SkyFire"));
	if (!PlumeMesh) PlumeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Vehicles/RoadsterRig/SC_JetCone/StaticMeshes/SC_JetCone.SC_JetCone"));
	if (!QuadMesh) QuadMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (!RoarSound) RoarSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/McGregor/Audio/S_MG_EngineRoar.S_MG_EngineRoar"));

	if (PlumeMesh)
	{
		PlumeOuter->SetStaticMesh(PlumeMesh);
		PlumeCore->SetStaticMesh(PlumeMesh);
	}
	if (JetMaterial)
	{
		MatOuter = UMaterialInstanceDynamic::Create(JetMaterial, this);
		MatCore = UMaterialInstanceDynamic::Create(JetMaterial, this);
		PlumeOuter->SetMaterial(0, MatOuter);
		PlumeCore->SetMaterial(0, MatCore);
		MatOuter->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.8f, 1.0f, 0.35f));   // the car's "rocket" look
		MatOuter->SetScalarParameterValue(TEXT("Diamonds"), 0.7f);
		MatCore->SetVectorParameterValue(TEXT("Color"), FLinearColor(2.6f, 2.2f, 1.6f));
		MatCore->SetScalarParameterValue(TEXT("Diamonds"), 1.2f);
	}
	if (QuadMesh)
	{
		SmokeFx->SetStaticMesh(QuadMesh);
		FireFx->SetStaticMesh(QuadMesh);
	}
	if (SmokeMaterial) SmokeFx->SetMaterial(0, SmokeMaterial);
	if (FireMaterial) FireFx->SetMaterial(0, FireMaterial);
	Smoke.Init(SmokeFx, FMath::Clamp(MaxSmoke, 16, 4000), true, true);
	Fire.Init(FireFx, FMath::Clamp(MaxFire, 16, 2000), false, false);

	if (RoarSound) Roar->SetSound(RoarSound);
	FSoundAttenuationSettings Att;
	Att.bAttenuate = true;
	Att.bSpatialize = true;
	Att.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
	Att.AttenuationShapeExtents = FVector(6000.f, 0.f, 0.f);     // full volume within 60 m
	Att.FalloffDistance = FMath::Max(SoundRadius - 6000.f, 1000.f);
	Att.dBAttenuationAtMax = -48.f;
	Att.bAttenuateWithLPF = true;                                  // far away it's a low rumble
	Att.LPFRadiusMin = 20000.f;
	Att.LPFRadiusMax = SoundRadius;
	Att.LPFFrequencyAtMax = 700.f;
	Roar->bOverrideAttenuation = true;
	Roar->AttenuationOverrides = Att;

	ExitLight->SetAttenuationRadius(LightRadius);
	NextTest = GetWorld()->GetTimeSeconds() + FMath::Max(FirstDelay, 0.f);
	UE_LOG(LogSkyTests, Log, TEXT("SkysterEngineTests %s: %d stands, first test in %.0f s, then every %.0f s%s"), *GetName(), Sites.Num(), FirstDelay, Interval,
		bNightLights ? TEXT(" (night lights)") : TEXT(""));
	if (Sites.Num() == 0) SetActorTickEnabled(false);
}

void ASkysterEngineTests::EndPlay(const EEndPlayReason::Type Reason)
{
	USkysterTestShakePattern::Amplitude = 0.f;
	Super::EndPlay(Reason);
}

FVector ASkysterEngineTests::CameraLocation() const
{
	if (const APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0)) return PCM->GetCameraLocation();
	return PlayerLocation();
}

FVector ASkysterEngineTests::PlayerLocation() const
{
	if (const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0)) return P->GetActorLocation();
	return GetActorLocation();
}

int32 ASkysterEngineTests::PickSite() const
{
	const int32 N = Sites.Num();
	if (N == 0) return -1;
	if (!bFirstDone && bFirstNearest)
	{
		const FVector P = PlayerLocation();
		int32 Best = 0;
		double BestD = TNumericLimits<double>::Max();
		for (int32 i = 0; i < N; ++i)
		{
			const double D = FVector::DistSquared2D(P, Sites[i].Exit);
			if (D < BestD) { BestD = D; Best = i; }
		}
		return Best;
	}
	if (bRandomOrder && N > 1)
	{
		const int32 K = FMath::RandRange(0, N - 2);
		return Last < 0 ? K : (K >= Last ? K + 1 : K);
	}
	return (Last + 1) % N;
}

void ASkysterEngineTests::RunTestNow(int32 SiteIndex)
{
	if (Phase != EPhase::Idle && Phase != EPhase::Linger) return;
	if (!Sites.IsValidIndex(SiteIndex)) SiteIndex = PickSite();
	if (SiteIndex < 0) return;
	SetActorTickEnabled(true);
	StartTest(SiteIndex);
}

void ASkysterEngineTests::StartTest(int32 Index)
{
	const FSkysterTestSite& S = Sites[Index];
	Current = Last = Index;
	bFirstDone = true;
	Phase = EPhase::Vent;
	TestT = -FMath::Max(VentTime, 0.f);
	PhaseT = 0;
	Thrust = 0.f;
	bSoundOn = bSoundStopped = false;
	SoundDelay = FMath::Min(FVector::Dist(CameraLocation(), S.Exit) / SOUND_CMS, 6.0);
	Roar->SetWorldLocation(S.Exit);
	Roar->SetPitchMultiplier(S.Kind == 1 ? 0.82f : S.Kind == 2 ? 1.08f : 1.f);
	const FVector E = S.ExitDir.GetSafeNormal();
	ExitLight->SetWorldLocation(S.Exit + E * 600.f + FVector(0, 0, 900.f));
	SmokeFx->SetVisibility(true);
	FireFx->SetVisibility(true);
	UE_LOG(LogSkyTests, Log, TEXT("SkysterEngineTests: test at %s (%s), %.0f s burn, sound delay %.1f s"), *S.Name, *S.Id.ToString(), S.Duration, SoundDelay);
}

void ASkysterEngineTests::EndVisuals()
{
	PlumeOuter->SetVisibility(false);
	PlumeCore->SetVisibility(false);
	ExitLight->SetVisibility(false);
	USkysterTestShakePattern::Amplitude = 0.f;
	if (UCameraShakeBase* Sh = Shake.Get())
	{
		if (APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0)) PCM->StopCameraShake(Sh, true);
	}
	Shake.Reset();
	ShakeNow = 0.f;
	if (Roar->IsPlaying() && !bSoundStopped) Roar->FadeOut(1.5f, 0.f);
}

int32 ASkysterEngineTests::Count(float Rate, float Dt)
{
	const float E = FMath::Max(0.f, Rate * Dt);
	const int32 N = (int32)E;
	return N + (Rand.FRand() < E - N ? 1 : 0);
}

void ASkysterEngineTests::UpdateShake(const FSkysterTestSite& S, float Amp)
{
	const float D = (float)FVector::Dist(PlayerLocation(), S.Exit);
	const float F = FMath::Square(FMath::Clamp(1.f - D / FMath::Max(ShakeRadius, 1.f), 0.f, 1.f));
	ShakeNow = ShakeStrength * F * Amp * (S.Kind == 1 ? 1.6f : 1.f);
	USkysterTestShakePattern::Amplitude = ShakeNow;
	APlayerCameraManager* PCM = UGameplayStatics::GetPlayerCameraManager(this, 0);
	if (!PCM) return;
	if (ShakeNow > 0.002f && !Shake.IsValid()) Shake = PCM->StartCameraShake(USkysterTestShake::StaticClass(), 1.f);
	else if (ShakeNow <= 0.002f && Shake.IsValid())
	{
		PCM->StopCameraShake(Shake.Get(), true);
		Shake.Reset();
	}
}

void ASkysterEngineTests::Tick(float Dt)
{
	Super::Tick(Dt);
	const double Now = GetWorld()->GetTimeSeconds();
	if (Phase == EPhase::Idle)
	{
		if (bEnabled && Sites.Num() > 0 && Now >= NextTest)
		{
			StartTest(PickSite());
			NextTest = Now + FMath::Max(Interval, 30.f);
		}
		else return;
	}
	if (!Sites.IsValidIndex(Current)) { Phase = EPhase::Idle; return; }
	const FSkysterTestSite& S = Sites[Current];
	TestT += Dt;
	PhaseT += Dt;
	LightT += Dt;

	// phases and the thrust envelope (a quick rise with a small overshoot, a softer cut-off)
	switch (Phase)
	{
	case EPhase::Vent:
		Thrust = 0.f;
		if (TestT >= 0.0)
		{
			Phase = EPhase::Burn;
			PhaseT = TestT;
			// ignition: a flash of fire at the nozzle
			const FVector D = S.NozzleDir.GetSafeNormal();
			for (int32 i = 0; i < 40; ++i)
			{
				FPuff& F = Fire.Add(Rand);
				F.P = S.Nozzle + D * Rand.FRandRange(0.f, S.PlumeLength * 0.5f) + Rand.GetUnitVector() * S.PlumeRadius * 0.8f;
				F.V = Rand.GetUnitVector() * Rand.FRandRange(800.f, 2500.f) + D * 2500.f;
				F.MaxLife = Rand.FRandRange(0.25f, 0.5f);
				F.Size = S.PlumeRadius * 2.f;
				F.Grow = S.PlumeRadius * 8.f;
				F.MaxSize = S.PlumeRadius * 7.f;
				F.C = FLinearColor(3.4f, 1.8f, 0.7f);
				F.A = 1.f;
				F.Drag = 2.5f;
			}
		}
		break;
	case EPhase::Burn:
	{
		const float K = FMath::Clamp((float)TestT / 0.35f, 0.f, 1.f);
		Thrust = K * K * (3.f - 2.f * K) * (1.f + 0.25f * FMath::Exp(-FMath::Square(((float)TestT - 0.3f) / 0.12f)));
		if (TestT >= S.Duration)
		{
			Phase = EPhase::Shutdown;
			PhaseT = 0;
			const FVector E = S.ExitDir.GetSafeNormal();
			for (int32 i = 0; i < 14; ++i)        // the last gulp out of the bay
			{
				FPuff& P = Smoke.Add(Rand);
				P.P = S.Exit + FVector::CrossProduct(E, FVector::UpVector).GetSafeNormal() * Rand.FRandRange(-0.4f, 0.4f) * S.ExitWidth;
				P.V = E * Rand.FRandRange(800.f, 1800.f) + FVector(0, 0, Rand.FRandRange(300.f, 700.f));
				P.MaxLife = Rand.FRandRange(14.f, 22.f);
				const float G = S.Kind == 1 ? 0.5f : 0.7f;
				P.C = FLinearColor(G, G * 0.98f, G * 0.95f);
				P.A = 0.55f;
				P.Size = 700.f;
				P.Grow = 500.f;
				P.MaxSize = 2400.f;
				P.Drag = 0.5f;
				P.RiseVel = Rand.FRandRange(200.f, 450.f);
				P.Floor = S.Exit.Z - 150.f;
			}
		}
		break;
	}
	case EPhase::Shutdown:
		Thrust = FMath::Clamp(1.f - (float)PhaseT / 0.6f, 0.f, 1.f);
		Thrust *= Thrust;
		if (PhaseT >= 0.6)
		{
			Phase = EPhase::Linger;
			PhaseT = 0;
			PlumeOuter->SetVisibility(false);
			PlumeCore->SetVisibility(false);
			ExitLight->SetVisibility(false);
		}
		break;
	case EPhase::Linger:
		Thrust = 0.f;
		break;
	default:
		break;
	}

	Emit(S, Dt);
	const FVector Cam = CameraLocation();
	Smoke.Update(Dt, Cam, WindVelocity);
	Fire.Update(Dt, Cam, FVector::ZeroVector);

	// plume: the cone and its hot core, flickering
	const bool bPlume = Thrust > 0.01f && PlumeMesh;
	if (PlumeOuter->IsVisible() != bPlume) { PlumeOuter->SetVisibility(bPlume); PlumeCore->SetVisibility(bPlume); }
	if (bPlume)
	{
		const FVector D = S.NozzleDir.GetSafeNormal();
		const FRotator R = FRotationMatrix::MakeFromX(-D).Rotator();
		const float Fl = 0.9f + 0.1f * FMath::Sin((float)LightT * 53.f) * FMath::Sin((float)LightT * 31.f);
		const float Rad = S.PlumeRadius / CONE_R * (S.Nozzles > 1 ? 1.15f : 1.f);
		PlumeOuter->SetWorldLocationAndRotation(S.Nozzle, R);
		PlumeCore->SetWorldLocationAndRotation(S.Nozzle + D * 5.f, R);
		PlumeOuter->SetWorldScale3D(FVector(S.PlumeLength / 100.f * Thrust * Fl, Rad, Rad));
		PlumeCore->SetWorldScale3D(FVector(S.PlumeLength / 100.f * 0.55f * Thrust * Fl, Rad * 0.5f, Rad * 0.5f));
		if (MatOuter) MatOuter->SetScalarParameterValue(TEXT("Strength"), 3.0f * FMath::Min(Thrust, 1.2f));
		if (MatCore) MatCore->SetScalarParameterValue(TEXT("Strength"), 1.6f * FMath::Min(Thrust, 1.2f));
	}

	// night light over the bay: flickers with the flame, a flash at ignition
	if (bNightLights)
	{
		const bool bL = Thrust > 0.01f;
		if (ExitLight->IsVisible() != bL) ExitLight->SetVisibility(bL);
		if (bL)
		{
			const float N = FMath::PerlinNoise1D((float)LightT * 9.f) * 0.5f + 0.5f;
			const float Flash = 1.f + 2.5f * FMath::Exp(-(float)FMath::Max(TestT, 0.0) / 0.12f);
			ExitLight->SetIntensity(LightCandelas * (S.Kind == 1 ? 1.8f : 1.f) * Thrust * (0.6f + 0.4f * N) * Flash);
		}
	}

	// sound and rumble arrive at the speed of sound
	const double Heard = TestT - SoundDelay;
	if (RoarSound && !bSoundOn && Heard >= 0.0 && Phase != EPhase::Vent && Phase != EPhase::Linger)
	{
		Roar->Play();
		Roar->FadeIn(0.3f, SoundVolume * (S.Kind == 1 ? 1.f : 0.8f));
		bSoundOn = true;
	}
	if (bSoundOn && !bSoundStopped && Heard >= S.Duration)
	{
		Roar->FadeOut(2.5f, 0.f);
		bSoundStopped = true;
	}
	float Amp = 0.f;
	if (Heard >= 0.0 && Heard < S.Duration + 0.6)
	{
		const float Up = FMath::Clamp((float)Heard / 0.35f, 0.f, 1.f);
		const float Down = FMath::Clamp((float)(S.Duration + 0.6 - Heard) / 0.6f, 0.f, 1.f);
		Amp = FMath::Min(Up, Down) * (1.f + 0.6f * FMath::Exp(-FMath::Square(((float)Heard - 0.3f) / 0.15f)));
	}
	UpdateShake(S, Amp);

	// done when the cloud has gone (or after a minute)
	if (Phase == EPhase::Linger && ((Smoke.Parts.Num() == 0 && Fire.Parts.Num() == 0 && Heard > S.Duration + 3.0) || PhaseT > 60.0))
	{
		EndVisuals();
		Smoke.Parts.Reset();
		Fire.Parts.Reset();
		Smoke.Update(0.f, Cam, WindVelocity);
		Fire.Update(0.f, Cam, FVector::ZeroVector);
		SmokeFx->SetVisibility(false);
		FireFx->SetVisibility(false);
		Phase = EPhase::Idle;
		Current = -1;
	}
}

void ASkysterEngineTests::Emit(const FSkysterTestSite& S, float Dt)
{
	const FVector Up(0, 0, 1);
	const FVector D = S.NozzleDir.GetSafeNormal(UE_SMALL_NUMBER, FVector(0, 0, -1));
	const FVector E = S.ExitDir.GetSafeNormal(UE_SMALL_NUMBER, FVector(-1, 0, 0));
	FVector Side = FVector::CrossProduct(E, Up);
	if (!Side.Normalize()) Side = FVector(0, 1, 0);
	const bool bBooster = S.Kind == 1;
	if (Phase == EPhase::Vent)
	{
		// tank chill-down: white vapour wisps around the stand
		for (int32 i = Count(9.f, Dt); i > 0; --i)
		{
			FPuff& P = Smoke.Add(Rand);
			P.P = S.Nozzle + Up * Rand.FRandRange(300.f, 1300.f) + FVector(Rand.FRandRange(-400.f, 400.f), Rand.FRandRange(-400.f, 400.f), 0);
			P.V = FVector(Rand.FRandRange(-120.f, 120.f), Rand.FRandRange(-120.f, 120.f), Rand.FRandRange(30.f, 150.f));
			P.MaxLife = Rand.FRandRange(4.f, 6.f);
			P.C = FLinearColor(0.93f, 0.95f, 0.98f);
			P.A = 0.32f;
			P.Size = 160.f;
			P.Grow = 200.f;
			P.MaxSize = 800.f;
			P.Drag = 0.8f;
			P.RiseVel = 80.f;
		}
		return;
	}
	if (Phase == EPhase::Burn || Phase == EPhase::Shutdown)
	{
		const float T = (float)TestT;
		const float Th = FMath::Min(Thrust, 1.f);
		// fire streaming along the plume
		for (int32 i = Count(55.f * S.FireScale * Th, Dt); i > 0; --i)
		{
			FPuff& F = Fire.Add(Rand);
			FVector Off = Rand.GetUnitVector() * S.PlumeRadius * 0.6f;
			if (S.Nozzles > 1 && S.NozzleSpread > 0.f) Off += Rand.GetUnitVector() * S.NozzleSpread;
			F.P = S.Nozzle + D * Rand.FRandRange(0.f, S.PlumeLength * 0.8f) + Off - D * (Off | D);
			F.V = D * Rand.FRandRange(3000.f, 6000.f);
			F.MaxLife = Rand.FRandRange(0.12f, 0.26f);
			F.Size = S.PlumeRadius * 1.6f;
			F.Grow = S.PlumeRadius * 4.f;
			F.MaxSize = S.PlumeRadius * 4.5f;
			F.C = FLinearColor(3.0f, 1.35f, 0.4f);
			F.A = 0.8f;
			F.Drag = 2.f;
		}
		// the exhaust bay: flame tongues (strong at first, fewer once the deluge water turns them to steam), smoke
		if (T > 0.25f)
		{
			const float Tongue = T < S.Duration * 0.5f ? 1.f : FMath::Lerp(1.f, 0.35f, FMath::Clamp((T - S.Duration * 0.5f) / (S.Duration * 0.5f), 0.f, 1.f));
			const float Big = bBooster ? 1.6f : 1.f;
			for (int32 i = Count(40.f * S.FireScale * Th * Tongue, Dt); i > 0; --i)
			{
				FPuff& F = Fire.Add(Rand);
				F.P = S.Exit + Side * Rand.FRandRange(-0.38f, 0.38f) * S.ExitWidth + Up * Rand.FRandRange(0.f, 150.f) - E * 200.f;
				F.V = E * Rand.FRandRange(2500.f, 4500.f) + Side * Rand.FRandRange(-500.f, 500.f) + Up * Rand.FRandRange(100.f, 500.f);
				F.MaxLife = Rand.FRandRange(0.35f, 0.75f);
				F.Size = 350.f * Big;
				F.Grow = 900.f * Big;
				F.MaxSize = 1800.f * Big;
				F.C = FLinearColor(2.8f, 1.15f, 0.32f);
				F.A = 0.85f;
				F.Drag = 1.6f;
				F.RiseVel = 300.f;
			}
			for (int32 i = Count(26.f * S.SmokeScale * Th, Dt); i > 0; --i)
			{
				FPuff& P = Smoke.Add(Rand);
				P.P = S.Exit + Side * Rand.FRandRange(-0.45f, 0.45f) * S.ExitWidth + Up * Rand.FRandRange(0.f, 250.f);
				P.V = E * Rand.FRandRange(1800.f, 3800.f) + Side * Rand.FRandRange(-600.f, 600.f) + Up * Rand.FRandRange(200.f, 800.f);
				P.MaxLife = Rand.FRandRange(14.f, 24.f);
				const float G = bBooster ? Rand.FRandRange(0.48f, 0.66f) : Rand.FRandRange(0.72f, 0.86f);
				P.C = FLinearColor(G, G * 0.98f, G * 0.95f);
				P.A = Rand.FRandRange(0.5f, 0.65f);
				P.Size = 500.f;
				P.Grow = 650.f;
				P.MaxSize = 2600.f * (bBooster ? 1.3f : 1.f);
				P.Drag = 0.45f;
				P.RiseVel = Rand.FRandRange(250.f, 600.f);
				P.Floor = S.Exit.Z - 150.f;
			}
		}
		// steam rising off the stand itself
		for (int32 i = Count(5.f * S.SmokeScale * Th, Dt); i > 0; --i)
		{
			FPuff& P = Smoke.Add(Rand);
			P.P = S.Nozzle + Up * Rand.FRandRange(200.f, 900.f) + FVector(Rand.FRandRange(-300.f, 300.f), Rand.FRandRange(-300.f, 300.f), 0);
			P.V = Up * Rand.FRandRange(300.f, 700.f) + FVector(Rand.FRandRange(-150.f, 150.f), Rand.FRandRange(-150.f, 150.f), 0);
			P.MaxLife = Rand.FRandRange(8.f, 12.f);
			P.C = FLinearColor(0.86f, 0.86f, 0.86f);
			P.A = 0.35f;
			P.Size = 300.f;
			P.Grow = 300.f;
			P.MaxSize = 1200.f;
			P.Drag = 0.6f;
			P.RiseVel = 350.f;
		}
		return;
	}
	if (Phase == EPhase::Linger && PhaseT < 4.0)
	{
		for (int32 i = Count(3.f * S.SmokeScale, Dt); i > 0; --i)
		{
			FPuff& P = Smoke.Add(Rand);
			P.P = S.Exit + Side * Rand.FRandRange(-0.3f, 0.3f) * S.ExitWidth + Up * Rand.FRandRange(0.f, 150.f);
			P.V = E * Rand.FRandRange(100.f, 400.f) + Up * Rand.FRandRange(100.f, 300.f);
			P.MaxLife = Rand.FRandRange(8.f, 12.f);
			P.C = FLinearColor(0.8f, 0.8f, 0.8f);
			P.A = 0.35f;
			P.Size = 400.f;
			P.Grow = 250.f;
			P.MaxSize = 1400.f;
			P.Drag = 0.5f;
			P.RiseVel = 150.f;
			P.Floor = S.Exit.Z - 150.f;
		}
	}
}

FString ASkysterEngineTests::GetTestState() const
{
	static const TCHAR* Names[] = { TEXT("idle"), TEXT("vent"), TEXT("burn"), TEXT("shutdown"), TEXT("linger") };
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	return FString::Printf(TEXT("phase=%s site=%s t=%.2f next_in=%.1f smoke=%d fire=%d thrust=%.2f shake=%.3f sound=%d sound_delay=%.2f plume=%d light=%d"),
		Names[(int32)Phase], Sites.IsValidIndex(Current) ? *Sites[Current].Id.ToString() : TEXT("-"), TestT, NextTest - Now, Smoke.Parts.Num(), Fire.Parts.Num(), Thrust,
		ShakeNow, (Roar && Roar->IsPlaying()) ? 1 : 0, SoundDelay, PlumeOuter && PlumeOuter->IsVisible() ? 1 : 0, ExitLight && ExitLight->IsVisible() ? 1 : 0);
}

// ------------------------------------------------------------------ the puff pools (SkysterFX's layout: R G B alpha age)

void ASkysterEngineTests::FPool::Init(UInstancedStaticMeshComponent* InIsm, int32 InMax, bool bInSort, bool bInWind)
{
	Ism = InIsm;
	Max = InMax;
	bSort = bInSort;
	bWind = bInWind;
	Parts.Reset();
	Parts.Reserve(Max);
	if (!Ism) return;
	Ism->ClearInstances();
	Ism->SetNumCustomDataFloats(5);
	TArray<FTransform> Parked;
	Parked.Init(FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), Max);
	Ism->AddInstances(Parked, false, true);
}

ASkysterEngineTests::FPuff& ASkysterEngineTests::FPool::Add(FRandomStream& R)
{
	FPuff& N = Parts.Num() < Max ? Parts.AddDefaulted_GetRef() : Parts[R.RandHelper(Max)];
	N.P = N.V = FVector::ZeroVector;
	N.C = FLinearColor::White;
	N.Life = 0.f;
	N.MaxLife = 1.f;
	N.Size = 100.f;
	N.Grow = 0.f;
	N.MaxSize = 900.f;
	N.A = 0.5f;
	N.Drag = 1.f;
	N.RiseVel = 0.f;
	N.Floor = -1e9f;
	N.Roll = bWind ? R.FRandRange(-0.45f, 0.45f) : R.FRandRange(0.f, 2 * PI);
	N.Spin = bWind ? R.FRandRange(-0.2f, 0.2f) : R.FRandRange(-0.8f, 0.8f);
	N.Phase = R.FRandRange(0.f, 0.15f);
	N.bLanded = false;
	return N;
}

void ASkysterEngineTests::FPool::Update(float Dt, const FVector& Cam, const FVector& Wind)
{
	if (!Ism) return;
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		FPuff& Pt = Parts[i];
		Pt.Life += Dt;
		if (Pt.Life >= Pt.MaxLife)
		{
			Parts.RemoveAtSwap(i--, EAllowShrinking::No);
			continue;
		}
		// relax toward the wind (smoke) or toward rest (fire), plus a buoyant rise speed
		const float K = 1.f - FMath::Exp(-Pt.Drag * Dt);
		const FVector Target = (bWind ? Wind : FVector::ZeroVector) + FVector(0, 0, Pt.RiseVel);
		Pt.V += (Target - Pt.V) * K;
		Pt.P += Pt.V * Dt;
		if (Pt.P.Z < Pt.Floor)
		{
			// lands: rolls outward along the ground, as in SkysterFX
			Pt.P.Z = Pt.Floor;
			if (!Pt.bLanded)
			{
				Pt.bLanded = true;
				const float Fall = FMath::Abs((float)Pt.V.Z);
				const FVector2D H(Pt.V.X, Pt.V.Y);
				const FVector2D Dir = H.SizeSquared() > 400.f ? H.GetSafeNormal() : FVector2D(FMath::Cos(Pt.Roll * 7.f), FMath::Sin(Pt.Roll * 7.f));
				Pt.V.X += Dir.X * Fall * 0.7f;
				Pt.V.Y += Dir.Y * Fall * 0.7f;
				Pt.Grow *= 1.4f;
			}
			Pt.V.Z = FMath::Max((float)Pt.V.Z, 20.f);
		}
		Pt.Size = FMath::Min(Pt.Size + Pt.Grow * Dt, Pt.MaxSize);
		Pt.Grow *= FMath::Exp(-0.12f * Dt);
		Pt.Roll += Pt.Spin * Dt;
	}
	const int32 N = Parts.Num();
	if (N == 0 && LastN == 0) return;
	LastN = N;
	Order.SetNum(N);
	for (int32 i = 0; i < N; ++i) Order[i] = i;
	if (bSort)
	{
		Order.Sort([this, &Cam](int32 A, int32 B) { return FVector::DistSquared(Parts[A].P, Cam) > FVector::DistSquared(Parts[B].P, Cam); });
	}
	const int32 Count = Max;
	if (Count == 0) return;
	Xfs.SetNum(Count);
	Data.SetNumUninitialized(Count * 5);
	for (int32 j = 0; j < Count; ++j)
	{
		if (j >= N)
		{
			Xfs[j] = FTransform(FQuat::Identity, Cam, FVector::ZeroVector);
			Data[j * 5] = Data[j * 5 + 1] = Data[j * 5 + 2] = Data[j * 5 + 3] = Data[j * 5 + 4] = 0.f;
			continue;
		}
		const FPuff& Pt = Parts[Order[j]];
		const FVector Z = (Cam - Pt.P).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
		FVector R = FVector::CrossProduct(FVector::UpVector, Z);
		if (!R.Normalize()) R = FVector::ForwardVector;
		const FVector U = FVector::CrossProduct(Z, R);
		const FVector X = R * FMath::Cos(Pt.Roll) + U * FMath::Sin(Pt.Roll);
		const float S = Pt.Size / QUAD;
		const float T = Pt.Life / Pt.MaxLife;
		Xfs[j] = FTransform(FRotationMatrix::MakeFromZX(Z, X).ToQuat(), Pt.P, FVector(S, S, 1.f));
		Data[j * 5] = Pt.C.R;
		Data[j * 5 + 1] = Pt.C.G;
		Data[j * 5 + 2] = Pt.C.B;
		// smoke: fades in over 0.4 s, holds, thins out at the end (the flipbook thins too); fire: (1 - t)^2
		Data[j * 5 + 3] = bWind ? Pt.A * FMath::Min(1.f, Pt.Life / 0.4f) * (1.f - T * T * T) : Pt.A * (1.f - T) * (1.f - T);
		Data[j * 5 + 4] = FMath::Min(1.f, T * 0.85f + Pt.Phase);
	}
	Ism->BatchUpdateInstancesTransforms(0, Xfs, true, false, true);
	Ism->SetCustomData(0, Count - 1, Data, false);
}

// ------------------------------------------------------------------ rumble

void USkysterTestShakePattern::GetShakePatternInfoImpl(FCameraShakeInfo& OutInfo) const
{
	OutInfo.Duration = FCameraShakeDuration::Infinite();
}

void USkysterTestShakePattern::StartShakePatternImpl(const FCameraShakePatternStartParams& Params)
{
	T = 0.f;
}

void USkysterTestShakePattern::UpdateShakePatternImpl(const FCameraShakePatternUpdateParams& Params, FCameraShakePatternUpdateResult& OutResult)
{
	T += Params.DeltaTime;
	const float A = Amplitude * Params.GetTotalScale();
	if (A <= 0.f) return;
	OutResult.Rotation.Pitch = A * 0.55f * FMath::PerlinNoise1D(T * 11.f);
	OutResult.Rotation.Yaw = A * 0.35f * FMath::PerlinNoise1D(T * 9.f + 17.f);
	OutResult.Rotation.Roll = A * 0.25f * FMath::PerlinNoise1D(T * 13.f + 41.f);
	OutResult.Location = FVector(0.f, 0.f, A * 4.f * FMath::PerlinNoise1D(T * 23.f + 5.f));
}

USkysterTestShake::USkysterTestShake(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<USkysterTestShakePattern>(TEXT("RootShakePattern")))
{
	bSingleInstance = true;
}
