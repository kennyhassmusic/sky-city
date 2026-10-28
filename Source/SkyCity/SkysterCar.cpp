#include "SkysterCar.h"

#include "Camera/CameraComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SphereComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/Paths.h"
#include "SkyCourse.h"
#include "SkysterFleet.h"
#include "SkysterHUD.h"
#include "SkysterTraffic.h"
#include "UObject/ConstructorHelpers.h"

// Rocket League's values (Unreal units for a 118 uu Octane) scaled by K = 3.9 to the 4.6 m Roadster;
// where Tesla published a real figure (top speed, thruster tank, suction) the real figure wins.
// Same table as js/vehicle.js `P` (Skyster 4.0).
namespace SkyP
{
	constexpr double RL_K = 3.9;
	constexpr double G = 650 * RL_K / 100;                 // 25.4 m/s^2
	constexpr double MAX_SPEED = 103;                      // 230 mph
	constexpr double SUPERSONIC = 97;                      // 217 mph
	constexpr double MAX_DRIVE = 103.0 * 1410 / 2300;      // 63 m/s on the motors alone (full car)
	constexpr double BRAKE = 3500 * RL_K / 100;            // 136.5 m/s^2
	// Kenny (20 Oct): X is the brake (it stops the car and holds it, never reverses) and LT is plain reverse. Both
	// slow the car at a firm ~3 g instead of Rocket League's 14 g brake, which felt like a glitch at speed.
	constexpr double STOP_DECEL = 30.0;                    // m/s^2
	constexpr double REVERSE_TOP = 18.0;                   // m/s (40 mph): a reverse gear, not Rocket League's full-speed reverse
	constexpr double COAST = 525 * RL_K / 100;             // 20.5 m/s^2 (arcade handling)
	constexpr double BOOST_GROUND = 991.667 * RL_K / 100;  // 38.7 m/s^2
	constexpr double BOOST_AIR = 991.667 * RL_K / 100;
	constexpr double AIR_THROTTLE = 66.667 * RL_K / 100;   // 2.6 m/s^2
	// water (provisional: floats and slows; Kenny hasn't picked float vs respawn)
	constexpr double WATER_WET = 0.35;         // m of the body under the surface before the water takes hold
	constexpr double WATER_DRAFT = 0.75;       // m: the float line, the car's underside this far under the surface
	constexpr double WATER_MAX_DEPTH = 8.0;    // m: deeper than this under a surface isn't that water
	constexpr double WATER_CRAWL = 3.0;        // m/s: above this the drag is strong...
	constexpr double WATER_DRAG_FAST = 3.0;    // 1/s
	constexpr double WATER_DRAG = 1.5;         // 1/s ...and below it, enough that paddling (throttle) tops out near 2 m/s
	constexpr double WATER_K = 6.0;            // 1/s^2 buoyancy spring to the float line
	constexpr double WATER_C = 4.0;            // 1/s its damping
	constexpr double WATER_LEVEL = 2.5;        // 1/s levelling to wheels-down on the water
	constexpr double WATER_SPIN = 3.0;         // 1/s spin damping
	constexpr double AIR_BRAKE = 40;                       // m/s^2 off the horizontal travel, LT in the air
	constexpr double BOOST_RATE = 33.3;                    // %/s: a full tank is 3 s
	constexpr double SPAWN_BOOST = 33;                     // RL: a third of a tank after every spawn
	constexpr double HOVER_RATE = 22;
	constexpr double JUMP_V = 291.667 * RL_K / 100;        // 11.4 m/s
	constexpr double JUMP_HOLD_A = 1458 * RL_K / 100;      // 56.9 m/s^2 for up to 0.2 s
	constexpr double JUMP_HOLD_T = 0.2;
	constexpr double DOUBLE_T = 1.25;
	constexpr double DODGE_V = 500 * RL_K / 100;           // 19.5 m/s
	constexpr double DODGE_T = 0.65;
	constexpr double DODGE_SPIN = (UE_DOUBLE_PI * 2) / 0.65;
	constexpr double DODGE_LOCK = 0.15;
	constexpr double T_PITCH = 12.146, T_YAW = 8.92, T_ROLL = 36.08;
	constexpr double D_PITCH = 2.798, D_YAW = 1.886, D_ROLL = 4.47;
	constexpr double MAX_ANG = 5.5;
	constexpr double SUCTION = 2.0;
	constexpr double TRACK_BOOSTER = 45.0;                 // m/s^2 along a Course Builder booster strip
	constexpr double RAIL_BOUNCE = 0.2;                    // Course Builder bumpers (SkyRail): the push back off the rail
	constexpr double RAIL_SCRUB = 0.08;                    // speed lost along the rail, at a 20 m/s hit or harder
	// Course Builder race assists (Design/RaceHandling.md), only on SkyTrack in a race (ASkyCourseRace sets the level)
	constexpr double RACE_GRIP = 0.5;                      // g of extra tyre load on the deck (Light and Full)
	constexpr double RACE_CREST = 6.0;                     // m/s off the deck before a crest launches you (2.5 without)
	constexpr double RACE_ESC = 3.0;                       // stability control times this (Full, not while powersliding)
	constexpr double WHEELBASE = 2.825;
	constexpr double SIXTY = 26.8224;
	constexpr double CHARGE_FAST = 80.0 / 15;              // %/s on a fast charger up to 80%
	constexpr double CHARGE_SLOW = 20.0 / 30;              // %/s above it
	constexpr double CHARGE_TAPER = 80;
	constexpr double VMIN = 5;                             // m/s: slip-angle floor
	constexpr double DEAD = 0.2;                           // RL's default stick deadzone
}

using namespace SkyP;

// Kenny's rigged Roadster, from Scripts/unreal/blender_roadster_rig.py (pivots.json), Unreal cm in the car frame.
// The model's axles sit 9 cm behind the physics wheelbase, so everything moves forward by RIG_FWD.
namespace SkyRig
{
	constexpr double RIG_FWD = 9.06;
	const FVector WING(169.0, 0, 73.7), SPOILER(-195.2, 0, 92.8), PANEL_L(227.349, -69.726, 46.992), PANEL_R(227.349, 69.726, 46.992);
	const FVector PUSH_DIR(-0.9701425, 0, 0.2425356);                    // spoiler actuators, 0..24 cm
	const FVector AXIS_X(0, -1, 0);                                      // the GLB's +X hinge axis, in Unreal
	const FVector PANEL_AXIS_L(0.1947375, 0.9787970, -0.0635112), PANEL_AXIS_R(-0.1947375, 0.9787970, 0.0635112);
	const FVector BAFFLE_L(-0.0002354, -0.9991587, -0.0410104), BAFFLE_R(-0.0002354, 0.9991587, -0.0410104);
	const FVector WHEELS[4] = { FVector(137.64, -104.967, 33.1), FVector(137.64, 104.967, 33.1), FVector(-148.26, -112.522, 33.762), FVector(-148.26, 112.522, 33.762) };
	const double WHEEL_R[4] = { 0.328, 0.328, 0.337, 0.337 };
	// four rear nozzles in the JetMetal panel under the tail bar; six floor jets FL FR ML MR RL RR
	const FVector REAR[4] = { FVector(-224.9, -40.5, 41), FVector(-224.9, -14.3, 41), FVector(-224.9, 14.3, 41), FVector(-224.9, 40.5, 41) };
	const FVector DOWN[6] = { FVector(175, -62, 22), FVector(175, 62, 22), FVector(20, -90, 21), FVector(20, 90, 21), FVector(-162, -88, 23), FVector(-162, 88, 23) };
	// two side thrusters in the fender camera slots just behind the front wheels (left, right), firing outward
	const FVector SIDE[2] = { FVector(62, -101, 66), FVector(62, 101, 66) };
	// js/addons.js LOOKS: plume colours, core, length and flame by the best fuel on board
	struct FLook { FLinearColor Rear, Down, Core, Fire; double Len; bool bFire; FLinearColor Vapor; double FireSize, FireSpeed, FireRate; };
	static FLook Look(const FString& Best)
	{
		if (Best == TEXT("nitrogen")) return { FLinearColor(0.55f, 1.5f, 2.7f), FLinearColor(0.5f, 1.35f, 2.4f), FLinearColor(1.8f, 2.8f, 3.8f), FLinearColor::Black, 1.1, false, FLinearColor(0.78f, 0.92f, 1.08f, 0.26f), 0, 0, 0 };
		if (Best == TEXT("combustion")) return { FLinearColor(1.6f, 0.6f, 0.16f), FLinearColor(1.4f, 0.55f, 0.18f), FLinearColor(2.2f, 1.5f, 0.7f), FLinearColor(1.5f, 0.55f, 0.12f), 1.3, true, FLinearColor(0.42f, 0.4f, 0.4f, 0.28f), 0.32, 16, 0.7 };
		if (Best == TEXT("rocket")) return { FLinearColor(1.8f, 1.0f, 0.35f), FLinearColor(1.5f, 0.85f, 0.3f), FLinearColor(2.6f, 2.2f, 1.6f), FLinearColor(1.7f, 1.05f, 0.45f), 1.7, true, FLinearColor(0.55f, 0.52f, 0.5f, 0.28f), 0.4, 26, 0.85 };
		return { FLinearColor(0.9f, 1.3f, 1.9f), FLinearColor(0.8f, 1.2f, 1.7f), FLinearColor(2.2f, 2.4f, 2.8f), FLinearColor::Black, 1.0, false, FLinearColor(0.9f, 0.94f, 1.0f, 0.22f), 0, 0, 0 };
	}
}

static const FVector UPV(0, 0, 1);
static const FVector DOWNV(0, 0, -1);

// The McGregor line-up is placed with whatever car models the project had (Scripts/vehicles/lineup_ue.py tags each part
// "LineupCar:<car>" and "LineupPart:<part>"). At play every part takes the model SkyFleet picks now: the licensed one if
// it's in this build and not listed as a stand-in, otherwise the blocky stand-in. So one map works in the open-source
// repo (no licensed models), the public build and Kenny's own build. Material overrides (the night map's lit lamps) carry
// over by slot name.
static FString SlotBase(const FName& Slot)
{
	FString S = Slot.ToString();
	int32 U;
	if (S.FindLastChar(TEXT('_'), U) && U + 1 < S.Len() && S.RightChop(U + 1).IsNumeric()) S.LeftInline(U);   // glTF's _001
	return S;
}

static void PickLineupModels(UWorld* World)
{
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		AStaticMeshActor* A = *It;
		if (!A->ActorHasTag(TEXT("MG_Lineup"))) continue;
		FString Car, Part;
		for (const FName& T : A->Tags)
		{
			const FString S = T.ToString();
			if (S.StartsWith(TEXT("LineupCar:"))) Car = S.RightChop(10);
			else if (S.StartsWith(TEXT("LineupPart:"))) Part = S.RightChop(11);
		}
		UStaticMeshComponent* C = A->GetStaticMeshComponent();
		if (Car.IsEmpty() || Part.IsEmpty() || !C) continue;
		const FString Want = SkyFleet::MeshPath(*Car, *Part);
		const UStaticMesh* Have = C->GetStaticMesh();
		if (Have && Have->GetPathName() == Want) continue;
		UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *Want);
		if (!M) continue;
		TMap<FString, UMaterialInterface*> Keep;
		if (Have)
		{
			const TArray<FStaticMaterial>& Old = Have->GetStaticMaterials();
			for (int32 i = 0; i < Old.Num(); ++i)
			{
				if (C->OverrideMaterials.IsValidIndex(i) && C->OverrideMaterials[i]) Keep.Add(SlotBase(Old[i].MaterialSlotName), C->OverrideMaterials[i]);
			}
		}
		C->SetMobility(EComponentMobility::Movable);
		C->EmptyOverrideMaterials();
		C->SetStaticMesh(M);
		const TArray<FStaticMaterial>& New = M->GetStaticMaterials();
		for (int32 i = 0; i < New.Num(); ++i)
		{
			if (UMaterialInterface** O = Keep.Find(SlotBase(New[i].MaterialSlotName))) C->SetMaterial(i, *O);
		}
	}
}

static double Damp(double A, double B, double Lambda, double Dt) { return FMath::Lerp(A, B, 1.0 - FMath::Exp(-Lambda * Dt)); }
static double Smooth(double E0, double E1, double X) { const double T = FMath::Clamp((X - E0) / (E1 - E0), 0.0, 1.0); return T * T * (3 - 2 * T); }
static double Sgn(double X) { return X > 0 ? 1.0 : X < 0 ? -1.0 : 0.0; }

ASkysterCar::ASkysterCar()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	Sensor = CreateDefaultSubobject<USphereComponent>(TEXT("Sensor"));
	Sensor->InitSphereRadius(150.f);
	Sensor->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Sensor->SetGenerateOverlapEvents(false);
	RootComponent = Sensor;

	Chassis = CreateDefaultSubobject<USceneComponent>(TEXT("Chassis"));
	Chassis->SetupAttachment(Sensor);

	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	Body->SetupAttachment(Chassis);
	Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Body->SetGenerateOverlapEvents(false);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CarMesh(TEXT("/Game/Vehicles/Roadster/SM_SM_Roadster_Merged.SM_SM_Roadster_Merged"));
	if (CarMesh.Succeeded())
	{
		Body->SetStaticMesh(CarMesh.Object);
	}

	// the rigged Roadster, if its parts are imported (else the old merged body stays)
	auto Part = [this](const TCHAR* Name, USceneComponent* Parent, const TCHAR* Path) {
		UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Parent);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		ConstructorHelpers::FObjectFinder<UStaticMesh> M(Path);
		if (M.Succeeded()) C->SetStaticMesh(M.Object);
		return C;
	};
	RigBody = Part(TEXT("RigBody"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_Body/StaticMeshes/RR_Body.RR_Body"));
	RigWing = Part(TEXT("RigWing"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_FrontWing/StaticMeshes/RR_FrontWing.RR_FrontWing"));
	RigPush = Part(TEXT("RigPush"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_SpoilerPush/StaticMeshes/RR_SpoilerPush.RR_SpoilerPush"));
	RigSpoiler = Part(TEXT("RigSpoiler"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_Spoiler/StaticMeshes/RR_Spoiler.RR_Spoiler"));
	RigPanelL = Part(TEXT("RigPanelL"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_HeadlightPanel_L/StaticMeshes/RR_HeadlightPanel_L.RR_HeadlightPanel_L"));
	RigPanelR = Part(TEXT("RigPanelR"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_HeadlightPanel_R/StaticMeshes/RR_HeadlightPanel_R.RR_HeadlightPanel_R"));
	RigBaffleL = Part(TEXT("RigBaffleL"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_Baffle_L/StaticMeshes/RR_Baffle_L.RR_Baffle_L"));
	RigBaffleR = Part(TEXT("RigBaffleR"), Chassis, TEXT("/Game/Vehicles/RoadsterRig/RR_Baffle_R/StaticMeshes/RR_Baffle_R.RR_Baffle_R"));
	RigWheels.Add(Part(TEXT("RigWheelFL"), Sensor, TEXT("/Game/Vehicles/RoadsterRig/RR_Wheel_FL/StaticMeshes/RR_Wheel_FL.RR_Wheel_FL")));
	RigWheels.Add(Part(TEXT("RigWheelFR"), Sensor, TEXT("/Game/Vehicles/RoadsterRig/RR_Wheel_FR/StaticMeshes/RR_Wheel_FR.RR_Wheel_FR")));
	RigWheels.Add(Part(TEXT("RigWheelRL"), Sensor, TEXT("/Game/Vehicles/RoadsterRig/RR_Wheel_RL/StaticMeshes/RR_Wheel_RL.RR_Wheel_RL")));
	RigWheels.Add(Part(TEXT("RigWheelRR"), Sensor, TEXT("/Game/Vehicles/RoadsterRig/RR_Wheel_RR/StaticMeshes/RR_Wheel_RR.RR_Wheel_RR")));
	static const TCHAR* Cone = TEXT("/Game/Vehicles/RoadsterRig/SC_JetCone/StaticMeshes/SC_JetCone.SC_JetCone");
	auto Jet = [&Part](const FString& Name, USceneComponent* Parent) {
		UStaticMeshComponent* C = Part(*Name, Parent, Cone);
		C->SetCastShadow(false);
		C->SetVisibility(false);
		return C;
	};
	for (int32 i = 0; i < 4; ++i)
	{
		RearJets.Add(Jet(FString::Printf(TEXT("RearJet%d"), i), Chassis));
		RearCores.Add(Jet(FString::Printf(TEXT("RearCore%d"), i), Chassis));
		Flames.Add(Jet(FString::Printf(TEXT("Flame%d"), i), Chassis));
	}
	for (int32 i = 0; i < 6; ++i)
	{
		DownJets.Add(Jet(FString::Printf(TEXT("DownJet%d"), i), Chassis));
		DownCores.Add(Jet(FString::Printf(TEXT("DownCore%d"), i), Chassis));
	}
	for (int32 i = 0; i < 2; ++i)
	{
		SideJets.Add(Jet(FString::Printf(TEXT("SideJet%d"), i), Chassis));
		SideCores.Add(Jet(FString::Printf(TEXT("SideCore%d"), i), Chassis));
	}

	// particle pools: world-space instanced quads (their materials load at BeginPlay, from Scripts/unreal/fx_ue.py)
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Quad(TEXT("/Engine/BasicShapes/Plane.Plane"));
	auto Fx = [this](const TCHAR* Name, int32 Sort) {
		UInstancedStaticMeshComponent* C = CreateDefaultSubobject<UInstancedStaticMeshComponent>(Name);
		C->SetupAttachment(Sensor);
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->TranslucencySortPriority = Sort;
		if (Quad.Succeeded()) C->SetStaticMesh(Quad.Object);
		return C;
	};
	VaporFx = Fx(TEXT("VaporFx"), -1); // smoke under the additive plumes, fire and sparks
	FireFx = Fx(TEXT("FireFx"), 1);
	SparkFx = Fx(TEXT("SparkFx"), 1);

	for (int32 i = 0; i < 2; ++i)
	{
		USpotLightComponent* L = CreateDefaultSubobject<USpotLightComponent>(i == 0 ? TEXT("HeadBeamL") : TEXT("HeadBeamR"));
		L->SetupAttachment(Chassis);
		L->SetRelativeLocation(FVector(232.0, i == 0 ? -62.0 : 62.0, 52.0));
		L->SetRelativeRotation(FRotator(-5.0, i == 0 ? -3.0 : 3.0, 0));
		L->SetIntensityUnits(ELightUnits::Lumens);
		L->SetIntensity(28000.f);
		L->SetLightColor(FLinearColor(1.0f, 0.95f, 0.88f));
		L->SetAttenuationRadius(9000.f);
		L->SetInnerConeAngle(16.f);
		L->SetOuterConeAngle(34.f);
		L->SetCastShadows(false);
		L->SetVisibility(false);
		HeadBeams.Add(L);
	}

	AltBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("AltBody"));
	AltBody->SetupAttachment(Chassis);
	AltBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	AltBody->SetGenerateOverlapEvents(false);
	AltBody->SetVisibility(false);
	for (int32 i = 0; i < 6; ++i)
	{
		UStaticMeshComponent* Wh = CreateDefaultSubobject<UStaticMeshComponent>(*FString::Printf(TEXT("AltWheel%d"), i));
		Wh->SetupAttachment(Sensor);
		Wh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Wh->SetGenerateOverlapEvents(false);
		Wh->SetVisibility(false);
		AltWheels.Add(Wh);
	}

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("ChaseCamera"));
	Camera->SetupAttachment(Sensor);
	Camera->SetUsingAbsoluteLocation(true);
	Camera->SetUsingAbsoluteRotation(true);
	Camera->SetFieldOfView(90.f);

	bUseControllerRotationPitch = bUseControllerRotationYaw = bUseControllerRotationRoll = false;
}

void ASkysterCar::BeginPlay()
{
	Super::BeginPlay();
	// seat the body: the sim's reference point is where the tyres touch, under the middle of the car
	if (const UStaticMesh* Mesh = Body->GetStaticMesh())
	{
		const FBox B = Mesh->GetBoundingBox();
		Body->SetRelativeLocation(FVector(-(B.Min.X + B.Max.X) * 0.5, -(B.Min.Y + B.Max.Y) * 0.5, -B.Min.Z));
	}
	SpawnPosUE = GetActorLocation();
	SpawnYawDeg = GetActorRotation().Yaw;
	ScanWater();
	// the car's materials load at play, not with the class: anything loaded during editor start-up becomes permanent and
	// can't be rebuilt by Scripts/unreal/fx_ue.py (DefaultGame.ini cooks these folders for the packaged game)
	auto Load = [](TObjectPtr<UMaterialInterface>& M, const TCHAR* Path) { if (!M) M = LoadObject<UMaterialInterface>(nullptr, Path); };
	Load(JetMaterial, TEXT("/Game/SkyCity/Pickups/Materials/MI_Jet.MI_Jet"));
	Load(CarLightMaterial, TEXT("/Game/SkyCity/Pickups/Materials/MI_CarLight.MI_CarLight"));
	Load(VaporMaterial, TEXT("/Game/SkyCity/FX/M_SkyVapor.M_SkyVapor"));
	Load(FireMaterial, TEXT("/Game/SkyCity/FX/M_SkyFire.M_SkyFire"));
	Load(SparkMaterial, TEXT("/Game/SkyCity/FX/M_SkySpark.M_SkySpark"));
	if (VaporMaterial) VaporFx->SetMaterial(0, VaporMaterial);
	if (FireMaterial) FireFx->SetMaterial(0, FireMaterial);
	if (SparkMaterial) SparkFx->SetMaterial(0, SparkMaterial);
	// an AI opponent gets smaller particle pools: every pool rewrites all its instances each frame it has particles
	const int32 PoolDiv = bAIDriver ? 4 : 1;
	VaporPool.Init(VaporFx, 2400 / PoolDiv, true, false, true);
	FirePool.Init(FireFx, 700 / PoolDiv, false, false);
	SparkPool.Init(SparkFx, 600 / PoolDiv, false, true);
	// the rigged Roadster replaces the old merged body when its parts are imported
	bRig = RigBody && RigBody->GetStaticMesh() != nullptr && RigWheels.Num() == 4 && RigWheels[0]->GetStaticMesh() != nullptr;
	if (bRig)
	{
		using namespace SkyRig;
		Body->SetVisibility(false, true);
		const FVector F(RIG_FWD, 0, 0);
		RigBody->SetRelativeLocation(F);
		RigWing->SetRelativeLocation(WING + F);
		RigPush->SetRelativeLocation(F);
		RigSpoiler->SetRelativeLocation(SPOILER + F);
		RigPanelL->SetRelativeLocation(PANEL_L + F);
		RigPanelR->SetRelativeLocation(PANEL_R + F);
		RigBaffleL->SetRelativeLocation(F);
		RigBaffleR->SetRelativeLocation(F);
		for (int32 i = 0; i < 4; ++i) RigWheels[i]->SetRelativeLocation(WHEELS[i] + F);
		for (int32 i = 0; i < 4; ++i)
		{
			for (UStaticMeshComponent* C : { RearJets[i].Get(), RearCores[i].Get(), Flames[i].Get() }) C->SetRelativeLocation(REAR[i] + F);
		}
		for (int32 i = 0; i < 6; ++i)
		{
			for (UStaticMeshComponent* C : { DownJets[i].Get(), DownCores[i].Get() })
			{
				C->SetRelativeLocation(DOWN[i] + F);
				C->SetRelativeRotation(FRotator(90, 0, 0)); // the cone points -X; turned to point down
			}
		}
		for (int32 i = 0; i < 2; ++i)
		{
			for (UStaticMeshComponent* C : { SideJets[i].Get(), SideCores[i].Get() })
			{
				C->SetRelativeLocation(SIDE[i] + F);
				C->SetRelativeRotation(FRotator(0, i == 0 ? 90 : -90, 0)); // the cone points -X; turned out of each side
			}
		}
		// lamp lenses glow under the car's control; plumes share four dynamic materials
		UMaterialInterface* Emissive = CarLightMaterial;
		UMaterialInterface* JetM = JetMaterial;
		if (Emissive)
		{
			const TArray<FName> Slots = RigBody->GetMaterialSlotNames();
			for (int32 i = 0; i < Slots.Num(); ++i)
			{
				const FString N = Slots[i].ToString();
				if (N.Contains(TEXT("LightWhite"))) { if (!MatHead) MatHead = UMaterialInstanceDynamic::Create(Emissive, this); RigBody->SetMaterial(i, MatHead); }
				if (N.Contains(TEXT("LightRed"))) { if (!MatTail) MatTail = UMaterialInstanceDynamic::Create(Emissive, this); RigBody->SetMaterial(i, MatTail); }
			}
			if (MatHead) MatHead->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.0f, 0.97f, 0.92f));
			if (MatTail) MatTail->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.0f, 0.04f, 0.03f));
		}
		if (JetM)
		{
			MatRear = UMaterialInstanceDynamic::Create(JetM, this);
			MatDown = UMaterialInstanceDynamic::Create(JetM, this);
			MatCore = UMaterialInstanceDynamic::Create(JetM, this);
			MatFlame = UMaterialInstanceDynamic::Create(JetM, this);
			for (auto& C : RearJets) C->SetMaterial(0, MatRear);
			for (auto& C : RearCores) C->SetMaterial(0, MatCore);
			for (auto& C : Flames) C->SetMaterial(0, MatFlame);
			for (auto& C : DownJets) C->SetMaterial(0, MatDown);
			for (auto& C : DownCores) C->SetMaterial(0, MatCore);
			for (auto& C : SideJets) C->SetMaterial(0, MatDown);
			for (auto& C : SideCores) C->SetMaterial(0, MatCore);
		}
	}
	else
	{
		for (UStaticMeshComponent* C : { RigBody.Get(), RigWing.Get(), RigPush.Get(), RigSpoiler.Get(), RigPanelL.Get(), RigPanelR.Get(), RigBaffleL.Get(), RigBaffleR.Get() }) if (C) C->SetVisibility(false);
		for (auto& C : RigWheels) C->SetVisibility(false);
	}
	if (bAIDriver)
	{
		// an AI opponent drives the body its race gave it (TestVehicle), not the player's choice
		const int32 V = FMath::Max(0, TestVehicle);
		TestVehicle = -1;
		SetVehicle(V, false);
	}
	else
	{
		SetVehicle(SkyFleet::GChoice, false);
		PickLineupModels(GetWorld());
	}
	// Sky City's streets carry traffic (and, switched on, flying Cybercabs): see SkysterTraffic
	if (!bAIDriver && UGameplayStatics::GetCurrentLevelName(this, true).Contains(TEXT("SkyCity")))
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Traffic = GetWorld()->SpawnActor<ASkysterTraffic>(ASkysterTraffic::StaticClass(), FTransform::Identity, P);
	}
	// night maps start with the headlights up
	if (UGameplayStatics::GetCurrentLevelName(this, true).Contains(TEXT("Night"))) bLights = true;
	// the Course Builder (Garage X cycles to it: McGregor opened with ?mode=build) runs from its own director actor
	if (!bAIDriver && SkyCourse::IsBuildMode(GetWorld()) && !ASkyCourseMode::Get(GetWorld()))
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		GetWorld()->SpawnActor<ASkyCourseMode>(ASkyCourseMode::StaticClass(), FTransform::Identity, P);
	}
	if (bAIDriver)
	{
		// a Course Builder opponent: the full car minus flight, nothing loaded or saved, no pickups (they're the
		// player's), no camera of its own
		Caps = Skyster::CapsFor(Skyster::NumLevels - 1);
		Caps.bFlight = false;
		FuelMult = 1;
		Camera->SetActive(false);
		SpawnAt(SpawnPosUE, SpawnYawDeg);
		return;
	}
	Progress.Load();
	Caps = Skyster::CapsFor(Progress.Level);
	FuelMult = Progress.FuelMult();
	World.Gather(GetWorld());
	World.HideOwned(Progress.Owned);
	SpawnAt(SpawnPosUE, SpawnYawDeg);
	const FSkyLevel& L = Progress.Current();
	Toast(FString::Printf(TEXT("Level %d · %s"), Progress.Level + 1, L.Name), L.Blurb);
}

void ASkysterCar::ResetToStart()
{
	SpawnAt(SpawnPosUE, SpawnYawDeg);
}

void ASkysterCar::ApplyCaps(const FSkyCaps& C)
{
	Caps = C;
	if (!Caps.bBoost) bBoosting = false;
}

void ASkysterCar::Toast(const FString& Title, const FString& Sub)
{
	if (bAIDriver) return;   // nobody reads an opponent's toasts
	Toasts.Add({ Title, Sub, SimTime });
	if (Toasts.Num() > 4) Toasts.RemoveAt(0);
}

void ASkysterCar::Event(ESkyEv Type, const FString& Name, double A, double B, int32 I)
{
	FSkyEvent E;
	E.Type = Type;
	E.Name = Name;
	E.A = A;
	E.B = B;
	E.I = I;
	Events.Add(E);
}

// A press of something the car hasn't unlocked yet: one event per press.
void ASkysterCar::Locked(const TCHAR* What, bool bOn)
{
	bool& Edge = LockEdge.FindOrAdd(What);
	if (bOn && !Edge) Event(ESkyEv::Locked, What);
	Edge = bOn;
}

void ASkysterCar::SpawnAt(const FVector& PosUE, double YawDeg)
{
	Pos = FromUE(PosUE);
	const double G0 = GroundAt(Pos.X, Pos.Y, Pos.Z + 2.0);
	if (G0 > -900) Pos.Z = G0;
	Vel = W = FVector::ZeroVector;
	Q = FQuat(UPV, FMath::DegreesToRadians(-YawDeg)); // Unreal yaw turns toward +Y (right); the sim's heading turns toward +y (left)
	UpdateAxes();
	bGrounded = true;
	Sup = FSupport();
	Sup.bOn = true;
	Jump = FJump();
	Dodge = FDodge();
	bTumbling = bFlying = bLanding = bLandArmed = bHovering = bAirBraking = false;
	StuckT = 0;
	Health = 100;
	bAlive = true;
	DeadT = 0;
	BoostTank = SPAWN_BOOST;
	SteerAngle = 0;
	YawRate = 0;
	Macro = FMacro();
	St.bSixtyOn = false;
	BankCombo(TEXT("dropped"));
	bCamInit = false;
	SpawnT = SimTime;
	ShowBody(true);
	ApplyToActor(0);
}

// Back on the nearest road to where the car is (js main.js respawn), or the map's start.
void ASkysterCar::Respawn()
{
	FVector P;
	double Yaw = 0;
	if (World.NearestRoad(ToUE(Pos), P, Yaw)) SpawnAt(P + FVector(0, 0, 50), Yaw);
	else SpawnAt(SpawnPosUE, SpawnYawDeg);
}

void ASkysterCar::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	// the car brings its own HUD, whatever the game mode says
	if (APlayerController* PC = Cast<APlayerController>(NewController))
	{
		PC->ClientSetHUD(ASkysterHUD::StaticClass());
	}
}

void ASkysterCar::UpdateAxes()
{
	Fwd = Q.RotateVector(FVector(1, 0, 0));
	Left = Q.RotateVector(FVector(0, 1, 0));
	Up = Q.RotateVector(FVector(0, 0, 1));
}

FQuat ASkysterCar::RotTo(const FVector& A, const FVector& B, double K)
{
	const double D = FMath::Clamp(FVector::DotProduct(A, B), -1.0, 1.0);
	FVector Axis = FVector::CrossProduct(A, B);
	const double Len = Axis.Size();
	if (Len < 1e-6)
	{
		if (D > 0) return FQuat::Identity;
		Axis = FVector::CrossProduct(FVector(1, 0, 0), A);
		if (Axis.SizeSquared() < 1e-6) Axis = FVector::CrossProduct(FVector(0, 0, 1), A);
		return FQuat(Axis.GetSafeNormal(), UE_DOUBLE_PI * K);
	}
	return FQuat(Axis / Len, FMath::Acos(D) * K);
}

// --- world queries -------------------------------------------------------------------------

double ASkysterCar::GroundAt(double X, double Y, double Z) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SkysterGround), false, this);
	const FVector A = ToUE(FVector(X, Y, Z + 1.5));
	const FVector B = ToUE(FVector(X, Y, Z - 500.0));
	if (GetWorld()->LineTraceSingleByChannel(Hit, A, B, ECC_Visibility, Params))
	{
		return Hit.ImpactPoint.Z / 100.0;
	}
	return -1000.0;
}

bool ASkysterCar::FindSupport(FSupport& Out, bool bGroundedNow) const
{
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SkysterSupport), false, this);
	FHitResult Hit;
	// along the car's down axis: whatever is under the wheels, floor, ramp, wall or ceiling
	const FVector A = ToUE(Pos + Up * 1.0);
	const FVector B = ToUE(Pos - Up * 1.3);
	bool bHit = GetWorld()->LineTraceSingleByChannel(Hit, A, B, ECC_Visibility, Params);
	FVector N = bHit ? DirFromUE(FVector(Hit.ImpactNormal)) : FVector::ZeroVector;
	if (!bHit || FVector::DotProduct(Up, N) < 0.35)
	{
		// tilted over flat ground: look straight down too (js: up.y > 0.35 and close to the ground)
		if (Up.Z <= 0.35) return false;
		const FVector A2 = ToUE(Pos + UPV * 1.5);
		const FVector B2 = ToUE(Pos - UPV * 1.5);
		if (!GetWorld()->LineTraceSingleByChannel(Hit, A2, B2, ECC_Visibility, Params)) return false;
		N = DirFromUE(FVector(Hit.ImpactNormal));
		if (N.Z < 0.6) return false;
	}
	Out.N = N.GetSafeNormal();
	Out.P = FromUE(FVector(Hit.ImpactPoint));
	Out.Dist = FVector::DotProduct(Pos - Out.P, Out.N);
	Out.Kind = Out.N.Z > 0.6 ? ESurface::Ground : ESurface::Wall;
	Out.Comp = Hit.GetComponent();
	return true;
}

// --- input ---------------------------------------------------------------------------------

ASkysterCar::FDriverInput ASkysterCar::ReadInput(float Dt)
{
	FDriverInput S;
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC && !bTestInput) return S;
	auto Ax = [PC](const FKey& K) { return PC ? (double)PC->GetInputAnalogKeyState(K) : 0.0; };
	auto On = [PC](const FKey& K) { return PC && PC->IsInputKeyDown(K); };
	auto K01 = [&On](const FKey& K) { return On(K) ? 1.0 : 0.0; };
	auto Hit = [this, &On](const FKey& K) { const bool bNow = On(K); bool& Prev = PrevKeys.FindOrAdd(K); const bool bHit = bNow && !Prev; Prev = bNow; return bHit; };

	// left stick with RL's radial deadzone
	double Lx = Ax(EKeys::Gamepad_LeftX), Ly = Ax(EKeys::Gamepad_LeftY);
	const double M = FMath::Sqrt(Lx * Lx + Ly * Ly);
	if (M < DEAD) { Lx = Ly = 0; }
	else { const double Kk = FMath::Min(1.0, (M - DEAD) / (1.0 - DEAD)) / M; Lx *= Kk; Ly *= Kk; }
	double Rx = Ax(EKeys::Gamepad_RightX), Ry = Ax(EKeys::Gamepad_RightY);
	if (FMath::Sqrt(Rx * Rx + Ry * Ry) < DEAD) Rx = Ry = 0;

	// raw controls: pad, then keyboard (W/S also pitch in the air, like RL's keyboard layout)
	double Throttle = FMath::Max3(Ax(EKeys::Gamepad_RightTriggerAxis), K01(EKeys::W), K01(EKeys::Up));
	double Brake = FMath::Max3(Ax(EKeys::Gamepad_LeftTriggerAxis), K01(EKeys::S), K01(EKeys::Down));
	double Steer = FMath::Clamp(Lx + K01(EKeys::D) - K01(EKeys::A) + K01(EKeys::Right) - K01(EKeys::Left), -1.0, 1.0);
	double Pitch = FMath::Clamp(Ly + K01(EKeys::W) - K01(EKeys::S) + K01(EKeys::Up) - K01(EKeys::Down), -1.0, 1.0); // stick forward = nose down
	const bool bAirNow = !bGrounded;
	// X: the brake on the road, air roll in the air; the powerslide moved to RB on the road (Ctrl on keys)
	bool bAirRollBtn = (bAirNow && On(EKeys::Gamepad_FaceButton_Left)) || (!bAirNow && On(EKeys::Gamepad_RightShoulder)) || On(EKeys::LeftControl) || On(EKeys::RightControl);
	double Stop = FMath::Max((!bAirNow && On(EKeys::Gamepad_FaceButton_Left)) ? 1.0 : 0.0, K01(EKeys::X));
	double RollBtn = K01(EKeys::Gamepad_RightShoulder) + K01(EKeys::E) - K01(EKeys::Q);
	bool bJumpBtn = On(EKeys::Gamepad_FaceButton_Bottom) || On(EKeys::SpaceBar);
	bool bBoostBtn = On(EKeys::Gamepad_FaceButton_Right) || On(EKeys::LeftShift) || On(EKeys::RightShift);
	bool bFlyBtn = On(EKeys::Gamepad_LeftShoulder) || On(EKeys::F);
	const bool bAir = !bGrounded;
	bool bLandBtn = (bAir && Ax(EKeys::Gamepad_LeftTriggerAxis) > 0.5) || On(EKeys::L); // LT in the air: air brake
	S.bMenuHit = Hit(EKeys::Gamepad_Special_Right) | Hit(EKeys::Escape) | Hit(EKeys::P);
	S.bResetHit = Hit(EKeys::Gamepad_Special_Left) | Hit(EKeys::R);
	const bool bUp = Hit(EKeys::Gamepad_DPad_Up), bDown = Hit(EKeys::Gamepad_DPad_Down), bL = Hit(EKeys::Gamepad_DPad_Left), bR = Hit(EKeys::Gamepad_DPad_Right);
	S.bKickHit = bUp | Hit(EKeys::One);
	S.bParkHit = bDown | Hit(EKeys::Two);
	S.bLaunchHit = (bAir && bL) | Hit(EKeys::Three);
	S.bLightsHit = (!bAir && bL) | Hit(EKeys::H);
	S.bModeHit = Hit(EKeys::G);                                      // handling: G, or A in the Garage
	S.bFsdHit = bR | Hit(EKeys::Z);                                  // self-driving: D-pad right / Z
	S.bNavA = Hit(EKeys::Gamepad_FaceButton_Bottom);
	S.bNavL = bL;
	S.bNavR = bR;
	S.bNavU = bUp;
	S.bNavD = bDown;
	S.bVehicleHit = Hit(EKeys::V);
	S.bTrafficHit = Hit(EKeys::T);
	S.bCabsHit = Hit(EKeys::C);
	S.bNavLB = Hit(EKeys::Gamepad_LeftShoulder);
	S.bNavRB = Hit(EKeys::Gamepad_RightShoulder);
	S.bNavY = Hit(EKeys::Gamepad_FaceButton_Top);
	S.bNavX = Hit(EKeys::Gamepad_FaceButton_Left);
	S.bNavB = Hit(EKeys::Gamepad_FaceButton_Right);
	S.bLevelDown = Hit(EKeys::LeftBracket);
	S.bLevelUp = Hit(EKeys::RightBracket);
	if (bTestInput)
	{
		Throttle = TestThrottle; Brake = TestBrake; Steer = TestSteer; Pitch = TestPitch; Stop = TestStop;
		RollBtn = TestRoll; bAirRollBtn = bTestSlide; bJumpBtn = bTestJump; bBoostBtn = bTestBoost; bFlyBtn = bTestFly;
		bLandBtn = bAir && TestBrake > 0.5f;
	}

	S.Throttle = Throttle;
	S.Brake = Brake;
	S.Stop = (float)Stop;
	S.Steer = Steer;
	S.Pitch = Pitch;
	S.bAirRoll = bAirRollBtn;
	if (bAir && bAirRollBtn && FMath::Abs(Steer) > 0.05)
	{
		S.Roll = FMath::Clamp(Steer + RollBtn, -1.0, 1.0); // holding air roll turns the steer axis into roll
		S.Yaw = 0;
	}
	else
	{
		S.Roll = FMath::Clamp(RollBtn, -1.0, 1.0);
		S.Yaw = Steer;
	}
	S.bJump = bJumpBtn;
	S.bJumpHit = S.bJump && !bPrevJumpT;
	bPrevJumpT = S.bJump;
	S.bBoost = bBoostBtn;
	S.bFlyHold = bAir && bFlyBtn;
	S.bLandHold = bLandBtn;
	S.LookX = Rx;
	S.LookY = Ry;
	return S;
}

// --- per frame -----------------------------------------------------------------------------

void ASkysterCar::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.05f);
	Events.Reset();
	FDriverInput S = ReadInput(Dt);
	if (TestSetLevel > 0) { Progress.SetLevel(TestSetLevel - 1, *this); TestSetLevel = 0; }
	if (S.bMenuHit) { bGarage = !bGarage; }
	if (bGarage)
	{
		Garage(S);
		UpdateCamera(Dt, FDriverInput());
		return;
	}
	if (S.bLevelDown || S.bLevelUp)
	{
		Progress.SetLevel(Progress.Level + (S.bLevelUp ? 1 : -1), *this);
		Toast(FString::Printf(TEXT("Car: Level %d · %s"), Progress.Level + 1, Progress.Current().Name), Progress.Current().Blurb);
	}
	if (S.bVehicleHit) SetVehicle(Vehicle + 1, true);
	if (TestVehicle >= 0) { SetVehicle(TestVehicle, true); TestVehicle = -1; }
	if (S.bTrafficHit) ToggleTraffic(false);
	if (S.bCabsHit) ToggleTraffic(true);
	// in a Course Builder race the race puts you back on the track (at the last good spot), not at the map's start
	if (bInCourseRace) { if (S.bResetHit) bRaceResetHit = true; }
	else if (S.bResetHit || Pos.Z < -60.0) Respawn();
	if (S.bModeHit)
	{
		Handling.bArcade = !Handling.bArcade;
		Toast(FString::Printf(TEXT("Handling: %s"), Handling.bArcade ? TEXT("Rocket League") : TEXT("grip (tyres)")), TEXT("Garage A / G switches"));
	}
	if (S.bFsdHit || bTestFsd) { bTestFsd = false; ToggleFsd(); }
	if (bFsd) FsdControl(Dt, S);
	// smart steering (race assist Full): the race's nudge away from the deck's edge, on top of the stick
	if (bInCourseRace && bGrounded && RaceSteerNudge != 0.f) S.Steer = FMath::Clamp(S.Steer + RaceSteerNudge, -1.f, 1.f);
	if (S.bLightsHit)
	{
		bLights = !bLights;
		Toast(FString::Printf(TEXT("Headlights %s"), bLights ? TEXT("up") : TEXT("down")));
	}
	if (bAlive)
	{
		const double Side = S.Steer < -0.2 ? -1.0 : 1.0;
		if (S.bKickHit && !StartMacro(TEXT("kickflip"), Side)) Toast(TEXT("No flip left"), TEXT("land or touch a wall first"));
		if (S.bParkHit && !StartMacro(TEXT("parallel"), Side)) Toast(TEXT("No flip left"), TEXT("land or touch a wall first"));
		if (S.bLaunchHit)
		{
			if (!bGrounded) bLandArmed = true; // landing protocol until touchdown (or a jump press)
			else if (Sup.Kind == ESurface::Ground) Toast(TEXT("Wall launch: do it from a wall"), TEXT("in the air this engages the landing protocol"));
			else if (!StartMacro(TEXT("launch"), Side)) Toast(TEXT("Recovering..."));
		}
	}
	if (bTestFullTank) BoostTank = 100;
	Simulate(Dt, S);
	HandleEvents();
	if (!bAIDriver) Progress.Update(Dt, *this);   // an opponent's stunts aren't the player's challenges
	if (bAlive && !bAIDriver)
	{
		const FString Id = World.CollectAddon(ToUE(Pos), Progress.Owned);
		if (!Id.IsEmpty() && Progress.Grant(Id))
		{
			FuelMult = Progress.FuelMult();
			BoostTank = 100;
			World.HideOwned(Progress.Owned);
			for (const Skyster::FAddon& A : Skyster::Addons)
			{
				if (Id != A.Id) continue;
				BurstSparks(ToUE(Pos) + FVector(0, 0, 180), 140, A.Col, 16);
				Toast(FString::Printf(TEXT("%s installed"), A.Name),
					FuelMult > A.Mult ? FString::Printf(TEXT("flight time x%d · x%d with everything on board · tank full"), A.Mult, (int32)FuelMult)
					                  : FString::Printf(TEXT("flight time x%d · tank full"), A.Mult));
			}
			Event(ESkyEv::Addon, Id);
		}
	}
	World.Update(Dt, SimTime, ToUE(Pos));
	if (!bAlive && (DeadT += Dt) > 3.4) Respawn();
	HurtFlash = FMath::Max(0.0, HurtFlash - Dt * 1.5);
	ComboShowT = FMath::Max(0.0, ComboShowT - Dt);
	ApplyToActor(Dt);
	if (!bAIDriver) UpdateCamera(Dt, S);
	UpdateFX(Dt);
}

// The Garage (Menu): the sim waits; D-pad left/right sets the car level for testing, X switches
// map, Y resets the challenges, B or Menu closes it.
void ASkysterCar::Garage(const FDriverInput& S)
{
	if (S.bNavL || S.bNavR || S.bLevelDown || S.bLevelUp)
	{
		Progress.SetLevel(Progress.Level + ((S.bNavR || S.bLevelUp) ? 1 : -1), *this);
	}
	if (S.bNavU || S.bNavD) SetVehicle(Vehicle + (S.bNavU ? 1 : -1), true);
	if (S.bNavLB) ToggleTraffic(true);
	if (S.bNavA)
	{
		Handling.bArcade = !Handling.bArcade;
		Toast(FString::Printf(TEXT("Handling: %s"), Handling.bArcade ? TEXT("Rocket League") : TEXT("grip (tyres)")), TEXT("Garage A / G switches"));
	}
	if (S.bNavRB) ToggleTraffic(false);
	if (S.bNavY) { Progress.Reset(*this); Toast(TEXT("Challenges reset"), TEXT("back to level 1 · Stock")); }
	if (S.bNavB) bGarage = false;
	// View / R: straight into the Course Builder (McGregor opened with ?mode=build), one press from any map
	if (S.bResetHit && !SkyCourse::IsBuildMode(GetWorld()))
	{
		UGameplayStatics::OpenLevel(this, FName(TEXT("/Game/Maps/McGregor")), true, TEXT("mode=build"));
		return;
	}
	if (S.bNavX && Maps.Num() > 0)
	{
		// entries are map paths, optionally with URL options ("/Game/Maps/McGregor?mode=build" is the Course Builder)
		const FString Here = UGameplayStatics::GetCurrentLevelName(this, true) + (SkyCourse::IsBuildMode(GetWorld()) ? TEXT("?mode=build") : TEXT(""));
		int32 Next = 0;
		for (int32 i = 0; i < Maps.Num(); ++i)
		{
			if (FPaths::GetBaseFilename(Maps[i].ToString()) == Here) { Next = (i + 1) % Maps.Num(); break; }
		}
		FString Level = Maps[Next].ToString(), Options;
		Maps[Next].ToString().Split(TEXT("?"), &Level, &Options);
		UGameplayStatics::OpenLevel(this, FName(Level.IsEmpty() ? Maps[Next].ToString() : Level), true, Options);
	}
}

void ASkysterCar::ToggleTraffic(bool bSkyLayer)
{
	ASkysterTraffic* T = Traffic.Get();
	if (!T || !T->IsReady())
	{
		Toast(TEXT("No traffic on this map"), TEXT("Sky City has it"));
		return;
	}
	if (bSkyLayer)
	{
		T->SetSky(!T->IsSky());
		Toast(FString::Printf(TEXT("Flying robotaxis %s"), T->IsSky() ? TEXT("on") : TEXT("off")), TEXT("the streets' lanes and rules, mirrored in the sky · floating signals"));
	}
	else
	{
		T->SetGround(!T->IsGround());
		Toast(FString::Printf(TEXT("Street traffic %s"), T->IsGround() ? TEXT("on") : TEXT("off")), TEXT("lanes, signals and stop signs"));
	}
}

void ASkysterCar::ToggleFsd()
{
	ASkysterTraffic* T = Traffic.Get();
	if (bFsd)
	{
		bFsd = bFsdHold = false;
		if (T) T->FsdStop();
		Toast(TEXT("Self-driving off"), TEXT("D-pad right / Z"));
		return;
	}
	if (!T || !T->IsReady())
	{
		Toast(TEXT("Self-driving unavailable"), TEXT("it drives Sky City's mapped streets"));
		return;
	}
	if (!bAlive || !bGrounded || Sup.Kind != ESurface::Ground)
	{
		Toast(TEXT("Self-driving unavailable"), TEXT("wheels on the road first"));
		return;
	}
	// destinations: the charger sites
	TArray<FVector> Goals;
	for (const FVector& C : World.Crosses) Goals.Add(C);
	FString Why;
	if (!T->FsdStart(GetActorLocation(), GetActorRotation().Yaw, Goals, Why))
	{
		Toast(TEXT("Self-driving unavailable"), Why);
		return;
	}
	bFsd = true;
	bFsdHold = false;
	Toast(TEXT("Self-driving on"), FString::Printf(TEXT("to %s · steer, brake, jump or boost to take over"), *T->FsdDestination()));
}

void ASkysterCar::FsdControl(double Dt, FDriverInput& S)
{
	ASkysterTraffic* T = Traffic.Get();
	const auto Off = [&](const TCHAR* Why)
	{
		bFsd = bFsdHold = false;
		if (T) T->FsdStop();
		Toast(TEXT("Self-driving off"), Why);
	};
	if (!T || !T->FsdOn()) { Off(TEXT("")); return; }
	// the driver takes over: steering, braking, a jump, boost, flight; the accelerator only hurries it along
	if (FMath::Abs(S.Steer) > 0.35 || S.Brake > 0.35 || S.Stop > 0.35 || S.bJumpHit || S.bBoost || S.bFlyHold || S.bKickHit || S.bParkHit) { Off(TEXT("you took over")); return; }
	if (!bAlive) { Off(TEXT("")); return; }
	if (Sup.Kind == ESurface::Wall) { Off(TEXT("off the road")); return; }
	const FVector CarUE = GetActorLocation();
	const double Yaw = GetActorRotation().Yaw;
	ASkysterTraffic::FFsdStep Step;
	if (!T->FsdStep(CarUE, Yaw, Vf, Dt, Step)) { Off(TEXT("off the mapped route")); return; }
	FsdHint = Step.Hint;
	FsdDistLeft = Step.DistLeft;
	// steering: pure pursuit to the look-ahead point, as a front-wheel angle over this speed's steering lock
	const FVector D = FVector(Step.Look.Y * 100.0 - CarUE.X, Step.Look.X * 100.0 - CarUE.Y, 0) / 100.0;
	const double CY = FMath::Cos(FMath::DegreesToRadians(Yaw)), SY = FMath::Sin(FMath::DegreesToRadians(Yaw));
	const double Lf = D.X * CY + D.Y * SY, Lr = -D.X * SY + D.Y * CY;
	const double Ld = FMath::Max(3.0, FMath::Sqrt(Lf * Lf + Lr * Lr));
	const double Delta = FMath::Atan(2.0 * WHEELBASE * FMath::Sin(FMath::Atan2(Lr, Lf)) / Ld);
	const bool bGripH = !Handling.bArcade;
	const double MaxSteer = (bGripH ? Handling.SteerLock : 0.62) / (1 + FMath::Abs(Vf) / (bGripH ? Handling.SteerFade : 16.0));
	const float PlayerThrottle = S.Throttle;
	S.Steer = FMath::Clamp(Delta / FMath::Max(MaxSteer, 0.05), -1.0, 1.0);
	S.Pitch = S.Roll = 0;
	S.bBoost = S.bJump = S.bFlyHold = S.bAirRoll = false;
	// speed: throttle up to the target, the X brake down to it, and held at a stop
	const double Err = Step.VTarget - Vf;
	S.Throttle = 0;
	S.Brake = 0;
	S.Stop = 0;
	if (Step.VTarget < 0.3 && Vf < 0.6) S.Stop = 1.f;
	else if (Err > 0.3) S.Throttle = (float)FMath::Clamp(0.12 + Err * 0.1, 0.0, 0.7);
	else if (Err < -0.8) S.Stop = (float)FMath::Clamp(-Err * 0.08, 0.05, 1.0);
	if (PlayerThrottle > 0.1f && S.Stop <= 0) S.Throttle = FMath::Max(S.Throttle, PlayerThrottle);
}

FString ASkysterCar::GetVehicleName() const
{
	return Vehicle > 0 ? FString(SkyFleet::Cars[Vehicle - 1].Label) : FString(TEXT("Roadster"));
}

void ASkysterCar::ShowBody(bool bOn)
{
	const bool bAlt = Vehicle > 0;
	Body->SetVisibility(bOn && !bRig && !bAlt, true);
	for (UStaticMeshComponent* C : { RigBody.Get(), RigWing.Get(), RigPush.Get(), RigSpoiler.Get(), RigPanelL.Get(), RigPanelR.Get(), RigBaffleL.Get(), RigBaffleR.Get() })
	{
		if (C) C->SetVisibility(bOn && bRig && !bAlt);
	}
	for (auto& C : RigWheels) C->SetVisibility(bRig && !bAlt);
	AltBody->SetVisibility(bOn && bAlt);
	for (int32 i = 0; i < AltWheels.Num(); ++i) AltWheels[i]->SetVisibility(bAlt && i < AltNum);
}

// Swap the body and wheels (Garage D-pad up/down, or V): the Roadster, or one of Kenny's McGregor line-up. Thrusters,
// headlight beams and the chase camera follow the vehicle's size; the handling stays the Skyster Roadster's.
void ASkysterCar::SetVehicle(int32 Index, bool bToast)
{
	using namespace SkyRig;
	using namespace SkyFleet;
	Index = ((Index % Num) + Num) % Num;
	UStaticMesh* BodyMesh = nullptr;
	if (Index > 0)
	{
		BodyMesh = LoadObject<UStaticMesh>(nullptr, *MeshPath(Cars[Index - 1].Name, TEXT("Body")));
		if (!BodyMesh)
		{
			if (bToast) Toast(TEXT("Vehicle not imported"), Cars[Index - 1].Label);
			Index = 0;
		}
	}
	Vehicle = Index;
	if (!bAIDriver) GChoice = Index;   // the player's choice rides through map changes; an opponent's doesn't
	const FVector F(RIG_FWD, 0, 0);
	FVector Size = ROADSTER;
	AltNum = 0;
	if (Vehicle > 0)
	{
		const FCar& C = Cars[Vehicle - 1];
		Size = C.Size;
		// overrides are kept by slot index across SetStaticMesh: drop the last vehicle's lamp overrides, or they land on
		// whatever this body has at those indices (Robotaxi glass and interior, Semi dashboard and glass lit up white/red)
		AltBody->EmptyOverrideMaterials();
		AltBody->SetStaticMesh(BodyMesh);
		AltBody->SetRelativeLocation(FVector(C.OffX, 0, 0));
		AltNum = C.NumWheels;
		for (int32 i = 0; i < 6; ++i)
		{
			UStaticMeshComponent* Wh = AltWheels[i];
			if (i >= C.NumWheels) { Wh->SetStaticMesh(nullptr); continue; }
			const FWheel& D = C.W[i];
			Wh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, *MeshPath(C.Name, D.Part)));
			Wh->SetRelativeLocation(D.P);
			AltR[i] = FMath::Max(0.1, D.R);
			AltSteer[i] = D.bSteer;
			AltAxle[i] = (D.bSteer ? 0 : 2) + (D.P.Y > 0 ? 1 : 0);
			AltSpin[i] = 0;
		}
		// lamp lenses under the car's control, like the Roadster's: the lens slots by exact name (Contains() also took
		// the Model 3's Taillight_Detail housing and reflectors and the Cybertruck's textured *_Inner emitters, which
		// keep their own atlas material from Scripts/vehicles/lineup_ue.py)
		const TArray<FName> Slots = AltBody->GetMaterialSlotNames();
		for (int32 i = 0; i < Slots.Num(); ++i)
		{
			const FString N = Slots[i].ToString();
			if (CarLightMaterial && (N == TEXT("Headlight") || N == TEXT("AuxLight")))
			{
				if (!MatHead) { MatHead = UMaterialInstanceDynamic::Create(CarLightMaterial, this); MatHead->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.0f, 0.97f, 0.92f)); }
				AltBody->SetMaterial(i, MatHead);
			}
			if (CarLightMaterial && N == TEXT("Taillight"))
			{
				if (!MatTail) { MatTail = UMaterialInstanceDynamic::Create(CarLightMaterial, this); MatTail->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.0f, 0.04f, 0.03f)); }
				AltBody->SetMaterial(i, MatTail);
			}
		}
	}
	// thrusters, beams and camera scaled from the Roadster to this vehicle's size (bigger rigs stand taller)
	const FVector K(Size.X / ROADSTER.X, Size.Y / ROADSTER.Y, FMath::Clamp(Size.Z / ROADSTER.Z, 1.0, 2.4));
	for (int32 i = 0; i < 4; ++i)
	{
		for (UStaticMeshComponent* C : { RearJets[i].Get(), RearCores[i].Get(), Flames[i].Get() }) if (C) C->SetRelativeLocation((REAR[i] + F) * K);
	}
	for (int32 i = 0; i < 6; ++i)
	{
		for (UStaticMeshComponent* C : { DownJets[i].Get(), DownCores[i].Get() }) if (C) C->SetRelativeLocation((DOWN[i] + F) * K);
	}
	for (int32 i = 0; i < 2; ++i)
	{
		for (UStaticMeshComponent* C : { SideJets[i].Get(), SideCores[i].Get() }) if (C) C->SetRelativeLocation((SIDE[i] + F) * K);
	}
	for (int32 i = 0; i < HeadBeams.Num(); ++i)
	{
		if (HeadBeams[i]) HeadBeams[i]->SetRelativeLocation(FVector(232.0, i == 0 ? -62.0 : 62.0, 52.0) * K);
	}
	CamScale = FMath::Max(1.0, FMath::Sqrt(Size.X / ROADSTER.X) * FMath::Sqrt(Size.Z / ROADSTER.Z));
	CamLift = FMath::Max(0.0, (Size.Z - ROADSTER.Z) * 0.006);
	ShowBody(bAlive);
	if (bToast) Toast(FString::Printf(TEXT("Driving: %s"), *GetVehicleName()), TEXT("Garage D-pad up/down or V to switch · same Skyster physics"));
}

FString ASkysterCar::GetMode() const
{
	if (!bAlive) return TEXT("WRECKED");
	if (bCharging) return TEXT("CHARGING");
	if (bFlying) return TEXT("FLIGHT");
	if (bInWater) return TEXT("WATER");
	if (bHovering) return TEXT("HOVER");
	if (bAirBraking) return TEXT("AIR BRAKE");
	if (bLanding) return TEXT("LANDING");
	if (bTumbling) return TEXT("TUMBLE");
	if (Dodge.bActive) return TEXT("FLIP");
	if (!bGrounded) return TEXT("AIR");
	if (Sup.Kind == ESurface::Wall) return TEXT("WALL");
	if (bDrifting) return TEXT("SLIDE");
	return TEXT("DRIVE");
}

void ASkysterCar::Simulate(float Dt, FDriverInput& Live)
{
	SimTime += Dt;
	if (!bAlive)
	{
		Vel.Z -= G * Dt;
		Pos += Vel * Dt;
		const double Gy = GroundAt(Pos.X, Pos.Y, Pos.Z);
		if (Pos.Z < Gy) { Pos.Z = Gy; Vel = FVector::ZeroVector; }
		Speed = 0;
		return;
	}
	// a jump press takes over from a scripted move so you can chain into your own
	if (Macro.bOn && Live.bJumpHit && Macro.T > 0.12) Macro.bOn = false;
	if (Macro.bOn) RunMacro(Dt, Live);
	FDriverInput S = Macro.bOn ? Macro.S : Live;

	// landing protocol: engaged by the level-out tap (D-pad left in the air) until touchdown, and by
	// the wall launch: wheels down, nose along the travel, the floor thrusters brake the descent
	const bool bWasLanding = bLanding;
	if (bGrounded) bLandArmed = false;
	const bool bThrusters = Caps.bBoost && !bGrounded && !bTumbling && !Dodge.bActive && !S.bFlyHold;
	bLanding = bThrusters && (bLandArmed || (Macro.bOn && Macro.Name == TEXT("launch") && Macro.Phase == 2));
	if (bLanding && !Macro.bOn)
	{
		FVector D(Vel.X, Vel.Y, 0);
		if (D.SizeSquared() < 16) D = FVector(Fwd.X, Fwd.Y, 0);
		if (D.SizeSquared() < 0.01) D = FVector(1, 0, 0);
		Aim(S, D.GetSafeNormal(), UPV, 1);
	}
	if (bLanding && !bWasLanding) Event(ESkyEv::Landing);
	// landing help (race assist Light/Full): over Course Builder track, turn wheels-down along the deck below, eased
	// out while the player gives air input of their own (or holds air roll)
	if (bInCourseRace && RaceAssist > 0 && bRaceAirAim && !bGrounded && !bLanding && !Macro.bOn && !Dodge.bActive && !bTumbling && !S.bFlyHold)
	{
		FDriverInput Am = S;
		Aim(Am, RaceAimFwd, RaceAimUp, 1);
		const double Mine = FMath::Max3(FMath::Abs((double)S.Pitch), FMath::Abs((double)S.Roll), FMath::Abs((double)S.Yaw));
		const float K = S.bAirRoll ? 0.f : (float)(1.0 - Smooth(0.15, 0.6, Mine));
		S.Pitch = FMath::Lerp(S.Pitch, Am.Pitch, K);
		S.Roll = FMath::Lerp(S.Roll, Am.Roll, K);
		S.Yaw = FMath::Lerp(S.Yaw, Am.Yaw, K);
	}

	// air brake: hold LT in the air and the thrusters slow the travel (see Fly) while roll and pitch
	// settle the car wheels-down; the nose keeps its heading, gravity still brings it down
	const bool bWasAirBraking = bAirBraking;
	bAirBraking = bThrusters && !bLanding && S.bLandHold && BoostTank > 0.01;
	if (bAirBraking && !Macro.bOn)
	{
		FVector D(Fwd.X, Fwd.Y, 0);
		// nose straight up or down: the heading it would level out to is along the belly or the roof
		if (D.SizeSquared() < 0.09) { const double Sg = Sgn(Fwd.Z) != 0 ? Sgn(Fwd.Z) : 1.0; D = FVector(Up.X, Up.Y, 0) * -Sg; }
		if (D.SizeSquared() < 1e-4) D = FVector(1, 0, 0);
		Aim(S, D.GetSafeNormal(), UPV, 1);
	}
	if (bAirBraking && !bWasAirBraking) Event(ESkyEv::AirBrake);

	// flight mode: hold LB (or F) in the air and the car flies like a jump jet while the tank has
	// pressure. The stick turns (banking) and climbs, RT drives, LT is the air brake, boost boosts.
	const bool bWasFlying = bFlying;
	Locked(TEXT("flight"), !Caps.bFlight && !bGrounded && S.bFlyHold);
	Locked(TEXT("boost"), !Caps.bBoost && S.bBoost);
	Locked(TEXT("airbrake"), !Caps.bBoost && !bGrounded && S.bLandHold);
	bFlying = Caps.bFlight && !bGrounded && bAlive && !bTumbling && !Dodge.bActive && !Macro.bOn && S.bFlyHold && BoostTank > 0.01;
	if (bFlying)
	{
		const double Hz = FMath::Sqrt(Vel.X * Vel.X + Vel.Y * Vel.Y);
		if (!bWasFlying)
		{
			FlyHeading = Hz > 4 ? FMath::Atan2(Vel.Y, Vel.X) : FMath::Atan2(Fwd.Y, Fwd.X);
			Event(ESkyEv::Flight);
		}
		FlyTurn = FMath::Clamp((double)S.Steer, -1.0, 1.0);
		FlyClimb = FMath::Clamp(-(double)S.Pitch, -1.0, 1.0); // stick back climbs
		const double Rate = FMath::Min(1.6, (G * 2.2) / FMath::Max(Hz, 1.0)); // about a 2.2 G turn at speed
		FlyHeading -= FlyTurn * Rate * Dt;
		// the nose points along the climb or dive at speed (see Fly); hovering it just tips a little
		const double Fast = Smooth(8, 25, Vel.Size());
		const double Path = FMath::Clamp(FMath::Atan2(Vel.Z, FMath::Max(Hz, 1.0)), -(double)Handling.FlyAngle - 0.1, (double)Handling.FlyAngle + 0.1);
		const double Hd = FlyHeading, Bank = FlyTurn * 0.5, Nose = FlyClimb * 0.22 * (1 - Fast) + Path * Fast;
		const FVector FT(FMath::Cos(Hd) * FMath::Cos(Nose), FMath::Sin(Hd) * FMath::Cos(Nose), FMath::Sin(Nose));
		const FVector UT(FMath::Sin(Hd) * FMath::Sin(Bank), -FMath::Cos(Hd) * FMath::Sin(Bank), FMath::Cos(Bank));
		Aim(S, FT, UT, 1);
	}

	// jump button edge handling (before substeps so one press = one action)
	if (S.bJumpHit) OnJump(S);
	if (!S.bJump) Jump.bHolding = false;

	// 0-60 timer: was the car standing still before this frame's push?
	St.bSixtyRest = bGrounded && Vel.SizeSquared() < 0.09;
	const int32 Steps = FMath::Max(1, FMath::CeilToInt(Dt * 120.0));
	const double H = Dt / Steps;
	for (int32 i = 0; i < Steps; ++i) Step(H, S);

	Speed = Vel.Size();
	UpdateAxes();
	TrackStunts(Dt, S);
	UpdateJets(Dt, S);
	Pickups(Dt);
	if (GroundRefill > 0 && bGrounded && !bBoosting) BoostTank = FMath::Min(100.0, BoostTank + GroundRefill * Dt);
}

void ASkysterCar::OnJump(FDriverInput& S)
{
	bLandArmed = false; // a jump press takes control back from the landing protocol
	if (bGrounded && !bTumbling)
	{
		// first jump: push off the surface along the car's up
		Vel += Up * JUMP_V;
		Jump.T = 0;
		Jump.AirT = 0;
		Jump.bCanDouble = true;
		Jump.bHolding = true;
		Jump.HoldT = 0;
		Jump.bHoverArmed = false;
		Jump.bFree = false;
		Jump.bFromWall = Sup.Kind != ESurface::Ground;
		Jump.Takeoff = Pos;
		LeaveSurface();
		BurstAll(1);
		Event(ESkyEv::Jump);
		St.Roll = St.Pitch = St.Yaw = 0;
	}
	else if (bTumbling || (Up.Z < 0.45 && Pos.Z - GroundY < 2.6))
	{
		RightSelf(); // on the roof or side: a thruster shove rights the car
	}
	else if (Jump.bCanDouble && (Jump.bFree || Jump.T < DOUBLE_T) && !Dodge.bActive)
	{
		if (!Caps.bDoubleJump) { Event(ESkyEv::Locked, TEXT("doubleJump")); return; }
		const double Dx = S.Steer, Dy = S.Pitch; // stick forward = front flip
		if (FMath::Sqrt(Dx * Dx + Dy * Dy) > 0.5) StartDodge(Dy, Dx);
		else
		{
			Vel += Up * JUMP_V;
			BurstAll(0.8);
			Event(ESkyEv::DoubleJump);
		}
		Jump.bCanDouble = false;
		Jump.bFree = false;
		Jump.bHolding = false;
	}
}

void ASkysterCar::StartDodge(double F, double R, double Impulse)
{
	const double M = FMath::Sqrt(F * F + R * R);
	if (M > 0) { F /= M; R /= M; }
	Dodge.bActive = true;
	Dodge.T = 0;
	Dodge.bCancelled = false;
	Dodge.Extra = FVector::ZeroVector;
	Dodge.Spin = FVector(R * DODGE_SPIN, F * DODGE_SPIN, 0); // car frame: roll, pitch (+ = nose down), yaw
	Dodge.PitchSign = Sgn(F);
	// impulse in the car's yaw frame (RL ignores pitch/roll for the dodge impulse)
	FVector Fh, Lh;
	if (Up.Z > 0.5) { Fh = FVector(Fwd.X, Fwd.Y, 0).GetSafeNormal(); Lh = FVector::CrossProduct(UPV, Fh); }
	else { Fh = Fwd; Lh = Left; }
	// RL: a back flip while rolling forward gets 2.5x (that's why it brakes); a side flip scales up with speed
	double Fk = F, Rk = R;
	const double Vf0 = FVector::DotProduct(Vel, Fh);
	if (F < 0 && Vf0 > 2) Fk *= 2.5;
	if (FMath::Abs(R) > 0.01) Rk *= 1 + 0.9 * FMath::Clamp(Vf0 / Caps.Drive, 0.0, 1.0);
	Vel += (Fh * Fk - Lh * Rk) * (DODGE_V * Impulse);
	if (Vel.Size() > MAX_SPEED) Vel = Vel.GetSafeNormal() * MAX_SPEED;
	Cb.LastDodge = SimTime;
	Cb.DodgeF = F;
	Event(ESkyEv::Dodge, FString(), F, R);
	// which nozzles: a front flip lifts the tail (rear pair), a roll fires the opposite side
	if (F > 0.4) { JetBurst[4] = JetBurst[5] = 1; }
	if (F < -0.4) { JetBurst[0] = JetBurst[1] = 1; }
	if (R > 0.4) { JetBurst[0] = JetBurst[2] = JetBurst[4] = 1; }
	if (R < -0.4) { JetBurst[1] = JetBurst[3] = JetBurst[5] = 1; }
}

void ASkysterCar::LeaveSurface()
{
	bGrounded = false;
	Sup.bOn = false;
	LastSupN = FVector::ZeroVector;
	// grip handling: a car that leaves the road mid-slide keeps turning
	W = Handling.bArcade ? FVector::ZeroVector : Sup.N * -YawRate;
}

void ASkysterCar::RightSelf()
{
	FVector F(Fwd.X, Fwd.Y, 0);
	if (F.SizeSquared() < 0.01) F = FVector(1, 0, 0);
	F.Normalize();
	const FVector L = FVector::CrossProduct(UPV, F);
	Q = FQuat(FMatrix(F, L, UPV, FVector::ZeroVector));
	UpdateAxes();
	const double G0 = GroundAt(Pos.X, Pos.Y, Pos.Z + 1);
	Pos.Z = FMath::Max(Pos.Z, G0) + 0.3;
	Vel = FVector(Vel.X * 0.3, Vel.Y * 0.3, 4.5);
	W = FVector::ZeroVector;
	YawRate = 0;
	bTumbling = false;
	StuckT = 0;
	bGrounded = false;
	Jump.bCanDouble = false;
	BurstAll(1);
	Event(ESkyEv::Righted);
}

// --- fixed step ----------------------------------------------------------------------------

void ASkysterCar::Step(double H, FDriverInput& S)
{
	UpdateAxes();
	bBoosting = Caps.bBoost && S.bBoost && BoostTank > 0.01 && !bTumbling;
	if (Dodge.bActive)
	{
		Dodge.T += H;
		if (Dodge.T >= DODGE_T)
		{
			Dodge.bActive = false;
			W = Q.RotateVector(Dodge.Extra); // any yaw or roll added through the flip carries on
		}
	}
	if (bGrounded) DriveOnSurface(H, S);
	else
	{
		if (bInCourseRace && RaceAssist > 0) Vel += RaceAirPull * H;   // landing help: drift toward the pad's middle
		Fly(H, S);
	}
	const FVector Prev = Pos;
	Pos += Vel * H;
	Collide(H, Prev);
	ResolveSupport(H);
	if (WaterBoxes.Num()) WaterForces(H);
	if (bBoosting) BoostTank = FMath::Max(0.0, BoostTank - BOOST_RATE * (Health < 30 ? 1.5 : 1.0) * H / FuelMult);
}

void ASkysterCar::DriveOnSurface(double H, FDriverInput& S)
{
	const FVector N = Sup.N;
	const bool bGrip = !Handling.bArcade;
	FVector F = Fwd - N * FVector::DotProduct(Fwd, N);
	if (F.SizeSquared() < 1e-4) F = FVector::CrossProduct(Left, N);
	F.Normalize();
	FVector L = FVector::CrossProduct(N, F).GetSafeNormal();
	double VF = FVector::DotProduct(Vel, F), VR = FVector::DotProduct(Vel, L);
	// rolling back down a steep ramp or wall before the fans are unlocked: say why
	if (!Caps.bWalls && Sup.Kind != ESurface::Ground && VF < -1.0) Event(ESkyEv::Locked, TEXT("walls"));
	const double Dmg = Health < 30 ? 0.75 : Health < 60 ? 0.9 : 1.0;
	// RL throttle curve: full acceleration at rest, a tenth near the drive cap, nothing past it
	const double DriveCap = Caps.Drive * Dmg * RaceSpeedScale;
	auto Curve = [this, DriveCap](double V) { return V >= DriveCap ? 0.0 : Caps.Accel * (1.0 - 0.9 * FMath::Clamp(V / DriveCap, 0.0, 1.0)); };
	double A = 0; // through the tyres
	// RT drives forward (and against a backward roll slows it first); LT is reverse (and against a forward roll slows
	// it first): no latches, it just goes the way you ask. X brakes to a stop in either direction and holds the car
	// there for as long as it's held, on any slope.
	const bool bStop = S.Stop > 0.05;
	if (!bStop)
	{
		if (S.Throttle > 0.02) A += VF >= 0 ? S.Throttle * Curve(VF) : S.Throttle * STOP_DECEL;
		if (S.Brake > 0.05) A -= VF > 0.5 ? S.Brake * STOP_DECEL : S.Brake * (-VF >= REVERSE_TOP ? 0.0 : Caps.Accel * (1.0 - 0.9 * FMath::Clamp(-VF / REVERSE_TOP, 0.0, 1.0)));
	}
	else A -= Sgn(VF) * FMath::Min(FMath::Abs(VF) / FMath::Max(H, 1e-3), STOP_DECEL * S.Stop);
	// the rear thrusters push the body, not the tyres, so grip never limits boost
	const double Thrust = bBoosting && VF < Caps.Top * Dmg * RaceSpeedScale ? BOOST_GROUND : 0.0;
	// Course Builder track pieces (component tags, Source/SkyCity/SkyCourse.h): a booster strip shoves the car along
	const UPrimitiveComponent* SupComp = Sup.Comp.Get();
	const bool bTrack = SupComp && SupComp->ComponentHasTag(TEXT("SkyTrack"));
	const double RaceGrip = (bTrack && bInCourseRace && RaceAssist > 0) ? G * RACE_GRIP : 0.0;
	bRaceStable = bTrack && bInCourseRace && RaceAssist >= 2 && !S.bAirRoll;
	const double Pad = (bTrack && SupComp->ComponentHasTag(TEXT("SkyBoost")) && VF > -1.0 && VF < MAX_SPEED) ? TRACK_BOOSTER : 0.0;
	bBraking = (bStop && FMath::Abs(VF) > 0.5) || (S.Brake > 0.05 && VF > 0.5);
	bReversing = VF < -0.5;
	bBrakeHold = bThrottleHold = false;
	const bool bIdle = S.Throttle < 0.02 && S.Brake < 0.05 && !bStop && !bBoosting;
	if (bIdle) A -= Sgn(VF) * FMath::Min(FMath::Abs(VF) / H, bGrip ? (double)Handling.Coast : COAST);
	// gravity along the surface (slides you down walls unless you drive)
	FVector Ag(0, 0, -G);
	const double Gn = FVector::DotProduct(Ag, N); // negative when gravity pushes into the surface
	Ag -= N * Gn;
	const double Gf = FVector::DotProduct(Ag, F), Gl = FVector::DotProduct(Ag, L);
	// tyre load (grip): gravity into the surface, the fans' suction and the wing's downforce, shifted
	// toward the rear under throttle and onto the front under braking
	double Nf = 0, Nr = 0;
	if (bGrip)
	{
		// on Course Builder track, the press of a loop or corkscrew (TrackPress, from the last step) loads the tyres too
		const double Load = FMath::Max(G * 0.25, -Gn + G * SUCTION * Fans * Handling.FanGrip + G * Handling.Aero * FMath::Square(VF / MAX_SPEED)
			+ (bTrack ? TrackPress + RaceGrip : 0.0));
		const double Shift = FMath::Clamp(AccelLong * Handling.CgH / WHEELBASE, -0.4 * Load, 0.4 * Load);
		Nf = Load * Handling.CgF - Shift;
		Nr = Load * (1 - Handling.CgF) + Shift;
		// wheelspin on a hard launch, ABS under hard braking: the tyres only push as hard as they grip
		const double Cap = Handling.Mu * Load * Handling.LongGrip;
		A = FMath::Clamp(A, -Cap * (VF > 0.5 ? 1.25 : 1.0), Cap);
	}
	// parked: static friction holds the car if the tyres' grip (fans plus whatever gravity presses into
	// the surface) beats the pull of gravity along it, at any angle on a wall
	const bool bHoldable = (bIdle && FMath::Abs(VF) < 0.8 && FMath::Abs(VR) < 0.8 &&
		FMath::Sqrt(Gf * Gf + Gl * Gl) < Handling.Mu * FMath::Max(0.0, -Gn + G * SUCTION * Fans))
		|| (bStop && S.Stop > 0.5 && FMath::Abs(VF) < 0.8 && FMath::Abs(VR) < 0.8 && Sup.Kind == ESurface::Ground);   // X holds the car
	if (!bHoldable)
	{
		VF += (A + Thrust + Pad + Gf) * H;
		VR += Gl * H;
	}
	else
	{
		VF = Damp(VF, 0, 30, H);
		VR = Damp(VR, 0, 30, H);
		YawRate = 0;
	}
	// steering: speed-sensitive lock
	const double MaxSteer = (bGrip ? Handling.SteerLock : 0.62) / (1 + FMath::Abs(VF) / (bGrip ? Handling.SteerFade : 16.0));
	SteerAngle = Damp(SteerAngle, S.Steer * MaxSteer, 12, H);
	double Turn; // yaw this step, + = right
	if (bGrip)
	{
		Turn = bHoldable ? 0.0 : Tyres(H, S, VF, VR, Nf, Nr, A);
		if (bHoldable) AccelLat = 0;
		bDrifting = FMath::Abs(VF) > 6 && (S.bAirRoll || FMath::Abs(SlipR) > 0.12);
	}
	else
	{
		// Rocket League: a bicycle model with no slip; powerslide turns harder and lets the car drift
		double Yaw = (VF / WHEELBASE) * FMath::Tan(SteerAngle);
		bDrifting = S.bAirRoll && FMath::Abs(VF) > 6;
		if (bDrifting) { Yaw *= 1.55; VF *= FMath::Exp(-0.28 * H); }
		VR *= FMath::Exp(-(bDrifting ? 1.5 : FMath::Abs(VR) > 6 ? 5.0 : 12.0) * H);
		AccelLat = VF * Yaw;
		YawRate = Yaw;
		Turn = Yaw * H;
	}
	AccelLong = A + Thrust;
	Vf = VF;
	Vr = VR;
	// yaw about the surface normal (a right turn is negative about up)
	const FQuat TurnQ(N, -Turn);
	if (bGrip)
	{
		// the tyre model works in the car's turning frame: its velocity turns with the car
		F = TurnQ.RotateVector(F);
		L = TurnQ.RotateVector(L);
	}
	Vel = F * VF + L * VR;
	Q = TurnQ * Q;
	// suspension pulls the car's up onto the surface normal; faster with speed so the body keeps up with a
	// curved ramp (js's flat city never needed it: a 7 m transition at 80 m/s turns the normal 6 degrees a step)
	UpdateAxes();
	Q = (RotTo(Up, N, 1.0 - FMath::Exp(-(22.0 + 3.0 * FMath::Abs(VF)) * H)) * Q).GetNormalized();
	W = FVector::ZeroVector;
	// fans: suction keeps the car on walls and ceilings and spins up with speed on the road; detach
	// when gravity wins (before the fans are unlocked a ramp past vertical drops you)
	Fans = (Sup.Kind != ESurface::Ground ? 1.0 : 0.15 + 0.45 * Smooth(15, 40, FMath::Abs(VF))) * Caps.Fans;
	// on Course Builder track a concave curve presses the car into it (v^2 / r, from how fast the surface normal turns
	// under the car), so a loop holds you if you're fast enough, as on real toy track, even before the fans are unlocked;
	// off the track nothing changes
	// The track is flat triangles, so the support normal only turns when the car crosses an edge: most steps it doesn't
	// move at all. So the bend is measured against the normal where it last changed, over the distance since, and the
	// press is held (decaying over ~0.15 s) between edges instead of dropping to zero.
	double Press = 0;
	if (bTrack && !LastSupN.IsZero())
	{
		TrackRun += FMath::Abs(VF) * H;
		const FVector DN = N - LastSupN;
		if (DN.SizeSquared() > 1e-8)
		{
			const double Curv = FMath::Max(0.0, -FVector::DotProduct(DN, F * Sgn(VF))) / FMath::Max(TrackRun, 0.05);   // 1/r
			TrackPress = FMath::Max(TrackPress * FMath::Exp(-H / 0.15), Curv * VF * VF);
			LastSupN = N;
			TrackRun = 0;
		}
		else TrackPress *= FMath::Exp(-H / 0.15);
		Press = TrackPress;
	}
	else
	{
		LastSupN = bTrack ? N : FVector::ZeroVector;
		TrackPress = 0;
		TrackRun = 0;
	}
	const double PullAway = Gn > 0 ? Gn : 0;
	if (PullAway > G * (Caps.bWalls ? SUCTION : 0.0) * 0.98 + Press + RaceGrip + 1e-3)
	{
		LeaveSurface();
		Vel += N * 0.5;
	}
	bHovering = false;
	Cushion = 0;
}

// Grip handling: a bicycle model with tyres (js vehicle.tyres). Each axle's slip angle gives a
// sideways force along the tyre curve; how hard an axle can push is its load times the friction,
// less what the throttle or brakes already ask of it. Yaw has inertia. Six sub-steps; returns the yaw angle.
double ASkysterCar::Tyres(double H, const FDriverInput& S, double& VFio, double& VRio, double Nf, double Nr, double ALong)
{
	const FSkyHandling& Hd = Handling;
	const double Lw = WHEELBASE, B = Hd.CgF * Lw, A = Lw - B; // centre of mass to the front (A) and rear (B) axle
	const bool bHand = S.bAirRoll;
	const double EscK = bRaceStable ? RACE_ESC : 1.0;   // race assist Full (DriveOnSurface sets it)
	const double MuF = Hd.Mu, MuR = Hd.Mu * Hd.RearGrip * (bHand ? Hd.Handbrake : 1.0);
	const double Split = ALong >= 0 ? Hd.DriveSplit : Hd.BrakeSplit;
	const double Xf = ALong * Split, Xr = ALong * (1 - Split);
	// throttle and brakes use up grip the tyres could turn with, but the car's traction and brake control keep a share
	// of it for cornering (KeepF / KeepR), so lifting off or braking mid-corner doesn't swap ends; the powerslide lets
	// the rear go
	const double KeepR = bHand ? 0.2 : (double)Hd.KeepR;
	const double Df = FMath::Sqrt(FMath::Max(FMath::Square(Hd.KeepF * MuF * Nf), FMath::Square(MuF * Nf) - Xf * Xf));
	const double Dr = FMath::Sqrt(FMath::Max(FMath::Square(KeepR * MuR * Nr), FMath::Square(MuR * Nr) - Xr * Xr));
	const double C = 2 - (2 / UE_DOUBLE_PI) * FMath::Asin(FMath::Clamp((double)Hd.Slide, 0.05, 0.97));
	const double Bc = FMath::Tan(UE_DOUBLE_PI / (2 * C)) / FMath::Max((double)Hd.Peak, 0.02);
	auto Shape = [C, Bc](double X) { return FMath::Sin(C * FMath::Atan(Bc * X)); };
	const double D = SteerAngle, Cd = FMath::Cos(D), Sd = FMath::Sin(D);
	double VF = VFio, Vy = -VRio, Yr = YawRate, Turn = 0, Ay = 0, Af = 0, Ar = 0;
	const double Kin = (VF / Lw) * FMath::Tan(D); // the yaw rate the steering asks for
	constexpr int32 NS = 6;
	const double Hs = H / NS;
	for (int32 i = 0; i < NS; ++i)
	{
		// sideways speed of each axle (+ = right), the front one in its steered wheels' frame
		const double Uf = Vy + A * Yr, Ur = Vy - B * Yr;
		const double Wl = Uf * Cd - VF * Sd, Wf = VF * Cd + Uf * Sd;
		Af = FMath::Atan2(Wl, FMath::Max(FMath::Abs(Wf), VMIN));
		Ar = FMath::Atan2(Ur, FMath::Max(FMath::Abs(VF), VMIN));
		const double Ff = -Df * Shape(Af), Fr = -Dr * Shape(Ar);
		const double Fy = Ff * Cd + Fr, Fx = -Ff * Sd;
		double Yacc = (A * Ff * Cd - B * Fr) / Hd.K2;
		const double Beta = FMath::Atan2(Vy, FMath::Abs(VF) + 0.1);
		if (bHand) Yacc += S.Steer * Hd.DriftYaw * FMath::Clamp(FMath::Abs(VF) / 15, 0.0, 1.0);
		else
		{
			if (Hd.Esc > 0 && (FMath::Abs(Yr) > FMath::Abs(Kin) || Yr * Kin < 0)) Yacc -= Hd.Esc * EscK * (Yr - Kin);
			// stability control: once the tail starts to come round, damp the rotation harder the further it slides
			if (Hd.EscSlip > 0 && VF > 4 && Yr * Beta < 0) Yacc -= Hd.EscSlip * EscK * Yr * Smooth(0.06, 0.30, FMath::Abs(Beta));
		}
		// drift angle limit: a slide past DriftAngle stops rotating further (a held stick holds a drift)
		if (Yr * Beta < 0 && VF > 0) Yacc -= 12 * Yr * Smooth(Hd.DriftAngle - 0.15, Hd.DriftAngle + 0.25, FMath::Abs(Beta));
		Vy += (Fy - VF * Yr) * Hs;
		VF += (Fx + Vy * Yr) * Hs;
		Yr += Yacc * Hs;
		Turn += Yr * Hs;
		Ay = Fy;
	}
	// at walking pace the tyres don't slip: the car simply follows its wheels (total speed, so a car
	// sliding sideways fast is not mistaken for a parked one)
	const double Wk = Smooth(1.5, 5, FMath::Sqrt(VF * VF + Vy * Vy));
	if (Wk < 1)
	{
		Yr = Kin + (Yr - Kin) * Wk;
		Vy *= Wk + (1 - Wk) * FMath::Exp(-20 * H);
		Turn = Turn * Wk + Kin * H * (1 - Wk);
	}
	YawRate = Yr;
	SlipF = Af;
	SlipR = Ar;
	AccelLat = Ay;
	VFio = VF;
	VRio = -Vy;
	return Turn;
}

void ASkysterCar::Fly(double H, FDriverInput& S)
{
	Jump.T += H;
	Jump.AirT += H;
	Vel.Z -= G * H;
	// boost pushes up to the level's top speed (a dive can still go faster)
	if (bBoosting && Vel.Size() < Caps.Top) Vel += Fwd * (BOOST_AIR * H);
	if (S.Throttle > 0.02 && !bFlying) Vel += Fwd * (AIR_THROTTLE * S.Throttle * H);
	if (bFlying)
	{
		// climb: the stick sets the climb rate. Hovering, the floor thrusters give up to 14 m/s up or
		// down; at speed the fins swing the travel up to FlyAngle above or below level without costing
		// speed, so the car climbs (or dives) the way the nose points, like a plane
		const double Sp0 = Vel.Size();
		const double Fast = Smooth(8, 25, Sp0);
		const double VyT = FlyClimb * FMath::Max(14.0, Sp0 * FMath::Sin(Handling.FlyAngle) * Fast);
		const double Lift = FMath::Clamp((VyT - Vel.Z) * 3 + G, -G * 2 * Fast, G * (2.2 + 2 * Fast));
		Vel.Z += Lift * H;
		FlyLift = FMath::Clamp(Lift / (G * 2.2), 0.0, 1.0);
		// the travel swings round to the nose without losing speed
		const double Hd = FlyHeading, Dx = FMath::Cos(Hd), Dy = FMath::Sin(Hd);
		double Vx = Vel.X, Vy = Vel.Y;
		double Sp = FMath::Sqrt(Vx * Vx + Vy * Vy);
		if (Sp > 0.5)
		{
			double Ang = FMath::Atan2(Vy, Vx);
			Ang += FMath::Atan2(FMath::Sin(Hd - Ang), FMath::Cos(Hd - Ang)) * FMath::Min(1.0, 3 * H);
			// at speed the climb is the travel turning upward: what goes into climbing comes out of the
			// forward speed and comes back when you level off
			if (Fast > 0) Sp += (FMath::Sqrt(FMath::Max(0.0, Sp0 * Sp0 - Vel.Z * Vel.Z)) - Sp) * Fast;
			Vx = FMath::Cos(Ang) * Sp;
			Vy = FMath::Sin(Ang) * Sp;
		}
		const double Sp2 = FMath::Sqrt(Vx * Vx + Vy * Vy);
		if (Sp2 > 0.01)
		{
			const double K = FMath::Max(0.0, Sp2 - S.Brake * 18 * H - Sp2 * 0.04 * H) / Sp2; // LT air brake and a little drag
			Vx *= K;
			Vy *= K;
		}
		Vx += Dx * S.Throttle * 20 * H; // RT on the rear thrusters
		Vy += Dy * S.Throttle * 20 * H;
		Vel.X = Vx;
		Vel.Y = Vy;
		BoostTank = FMath::Max(0.0, BoostTank - (14 + S.Throttle * 8) * H / FuelMult);
	}
	// held jump: the first 0.2 s keep pushing (RL hold-jump)
	if (Jump.bHolding && Jump.HoldT < JUMP_HOLD_T && S.bJump)
	{
		Vel += Up * (JUMP_HOLD_A * H);
		Jump.HoldT += H;
	}
	// hover: after both jumps, let go of jump and hold it again for the six floor thrusters. The
	// nozzles vector to hold the car up whatever its attitude, so a roll or flip while hovering stays put.
	bHovering = false;
	if (!Jump.bCanDouble && !Jump.bHolding && !bTumbling)
	{
		if (!S.bJump) { Jump.bHoverArmed = true; Jump.HoverHold = 0; }
		else Jump.HoverHold += H;
		if (S.bJump && Jump.bHoverArmed && Jump.HoverHold > 0.25 && !Caps.bHover) Locked(TEXT("hover"), true);
		else if (!S.bJump) Locked(TEXT("hover"), false);
		if (Caps.bHover && S.bJump && Jump.bHoverArmed && Jump.HoverHold > 0.25 && BoostTank > 0.01)
		{
			const double K = Vel.Z > 4 ? 0.55 : Vel.Z < -1 ? 1.35 : 1.06;
			Vel.Z += G * K * H;
			BoostTank = FMath::Max(0.0, BoostTank - HOVER_RATE * H / FuelMult);
			bHovering = true;
		}
	}
	// landing cushion: floor thrusters catch a hard drop, off the pump's own reserve
	Cushion = 0;
	const double Gy = GroundAt(Pos.X, Pos.Y, Pos.Z);
	const double Vz = Vel.Z;
	if (!bTumbling && Vz < -12 && Up.Z > 0.3 && !bHovering)
	{
		const double Net = G * 1.5;
		const double Stop = (Vz * Vz - 144.0) / (2 * Net);
		if (Pos.Z - Gy < Stop + 1.2)
		{
			Vel.Z += G * 2.5 * H;
			BoostTank = FMath::Max(0.0, BoostTank - 6 * H / FuelMult);
			Cushion = 1;
		}
	}
	// landing protocol: wheels down, descent held to 6 m/s off the tank
	if (bLanding && Up.Z > 0.5 && Vel.Z < -6 && BoostTank > 0.01)
	{
		const double A = FMath::Clamp((-6 - Vel.Z) * 2.5, 0.0, G * 1.6);
		Vel += Up * (A * H);
		BoostTank = FMath::Max(0.0, BoostTank - 10 * H / FuelMult);
		Cushion = FMath::Max(Cushion, 0.9);
	}
	// air brake: the thrusters take the travel away at up to AIR_BRAKE and carry AirLift of the weight
	if (bAirBraking)
	{
		Vel.Z += G * Handling.AirLift * H;
		const double Hz = FMath::Sqrt(Vel.X * Vel.X + Vel.Y * Vel.Y);
		if (Hz > 1e-4)
		{
			const double K = FMath::Max(0.0, Hz - AIR_BRAKE * H) / Hz;
			Vel.X *= K;
			Vel.Y *= K;
		}
		BoostTank = FMath::Max(0.0, BoostTank - 10 * H / FuelMult);
	}
	const double Sp = Vel.Size();
	if (Sp > MAX_SPEED) Vel *= MAX_SPEED / Sp;

	// angular motion, in the car frame: x roll, y pitch (+ = nose down), z yaw (+ = left)
	if (Dodge.bActive)
	{
		// flip cancel: pulling the stick against the flip stops the pitch rotation
		if (Dodge.PitchSign != 0 && Sgn(S.Pitch) == -Dodge.PitchSign && FMath::Abs(S.Pitch) > 0.5) Dodge.bCancelled = true;
		FVector Wl = Dodge.Extra;
		if (Dodge.T > DODGE_LOCK)
		{
			Wl.Z += (-T_YAW * S.Yaw - D_YAW * Wl.Z * (1 - FMath::Abs(S.Yaw))) * H;
			Wl.X += (T_ROLL * S.Roll - D_ROLL * Wl.X) * H;
			const double M = Wl.Size();
			if (M > MAX_ANG) Wl *= MAX_ANG / M;
		}
		Dodge.Extra = Wl;
		Wl += Dodge.Spin;
		if (Dodge.bCancelled) Wl.Y = Dodge.Extra.Y;
		W = Q.RotateVector(Wl);
	}
	else if (!bTumbling)
	{
		FVector Wl = Q.Inverse().RotateVector(W);
		const double P = S.Pitch, Y = S.Yaw, R = S.Roll;
		Wl.Y += (T_PITCH * P - D_PITCH * Wl.Y * (1 - FMath::Abs(P))) * H;
		Wl.Z += (-T_YAW * Y - D_YAW * Wl.Z * (1 - FMath::Abs(Y))) * H;
		Wl.X += (T_ROLL * R - D_ROLL * Wl.X) * H;
		// roll assist: no roll input (and no pitch held, so loops stay loops) banks back to wheels-down
		if (bRollAssist && FMath::Abs(R) < 0.05 && FMath::Abs(P) < 0.3)
		{
			const double Cu = Up.Z, Cl = Left.Z;
			const double Mag = FMath::Sqrt(Cu * Cu + Cl * Cl);
			if (Mag > 0.15)
			{
				double E = FMath::Atan2(-Cl, Cu);
				if (UE_DOUBLE_PI - FMath::Abs(E) < 0.15) E = UE_DOUBLE_PI * (Wl.X >= 0 ? 1 : -1);
				Wl.X += FMath::Clamp(E * 16, -T_ROLL, T_ROLL) * Mag * H;
			}
		}
		// hovering with the pitch stick idle: the nose levels out too, so a roll or flip in the hover
		// comes back wheels down and pointing the way it started
		if (bHovering && bRollAssist && FMath::Abs(P) < 0.3)
		{
			const double E = FMath::Asin(FMath::Clamp(Fwd.Z, -1.0, 1.0)); // nose above the horizon
			Wl.Y += FMath::Clamp(E * 16, -T_PITCH, T_PITCH) * Up.Z * H;
		}
		const double M = Wl.Size();
		if (M > MAX_ANG) Wl *= MAX_ANG / M;
		W = Q.RotateVector(Wl);
	}
	else
	{
		W *= FMath::Exp(-0.8 * H);
	}
	const double Ang = W.Size() * H;
	if (Ang > 1e-7) Q = (FQuat(W.GetSafeNormal(), Ang) * Q).GetNormalized();
	SteerAngle = Damp(SteerAngle, S.Steer * 0.3, 6, H);
	bBraking = bReversing = bDrifting = false;
	AccelLong = AccelLat = 0;
	Vf = FVector::DotProduct(Vel, Fwd);
	Vr = FVector::DotProduct(Vel, Left);
	Fans = Damp(Fans, 0.1, 3, H);
}

// --- contacts ------------------------------------------------------------------------------

void ASkysterCar::Collide(double H, const FVector& PrevPos)
{
	UpdateAxes();
	// driving down a wall onto the street: re-seat on the ground instead of crashing (only onto flat ground
	// below a vertical wall, not further along a curved ramp)
	FHitResult Below;
	FCollisionQueryParams BelowParams(SCENE_QUERY_STAT(SkysterBelow), false, this);
	if (bGrounded && Sup.Kind == ESurface::Wall && FMath::Abs(Sup.N.Z) < 0.3 && Vel.Z < 0 && GroundY > -900 && Pos.Z <= GroundY + 0.9
		&& GetWorld()->LineTraceSingleByChannel(Below, ToUE(Pos + FVector(0, 0, 1.5)), ToUE(Pos - FVector(0, 0, 3.0)), ECC_Visibility, BelowParams)
		&& Below.ImpactNormal.Z > 0.9 && Below.GetComponent() != Sup.Comp.Get())
	{
		Pos.Z = GroundY;
		const double Sp = Vel.Size();
		TransitionTo(UPV, nullptr, ESurface::Ground, Pos);
		// a building has no curved corner: coming down fast means a hard hit on the sills
		if (Sp > 28)
		{
			Hurt((Sp - 28) * 0.5 + 6, 0.8);
			Event(ESkyEv::Impact, FString(), (Sp - 28) * 0.5 + 6);
		}
		return;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SkysterBody), false, this);
	const FCollisionShape Ball = FCollisionShape::MakeSphere(80.f);
	// sample the body along its length, in the car's own plane (js: offsets 1.5, 0, -1.45);
	// on a wall the samples stay level with the car so the street below isn't a "wall"
	FVector Along = Fwd;
	if (bGrounded && Sup.Kind == ESurface::Wall && FMath::Abs(Sup.N.Z) < 0.3) { Along.Z = 0; Along = Along.GetSafeNormal(); }
	for (const double Off : { 1.5, 0.0, -1.45 })
	{
		const FVector Lift = Up * 1.0 + Along * Off;
		const FVector From = ToUE(PrevPos + Lift);
		const FVector To = ToUE(Pos + Lift);
		FHitResult Hit;
		if (!GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Visibility, Ball, Params) || !Hit.bBlockingHit) continue;
		const FVector N = DirFromUE(FVector(Hit.bStartPenetrating ? Hit.Normal : Hit.ImpactNormal)).GetSafeNormal();
		// the surface under the wheels (floor, ramp, the wall being ridden) is the support's business, and so is
		// more of the same surface curving up ahead (the McGregor ramp into its overhang)
		if (FVector::DotProduct(N, Up) > 0.6) continue;
		if (bGrounded && Hit.GetComponent() == Sup.Comp.Get() && FVector::DotProduct(N, Sup.N) > 0.5) continue;
		// Course Builder bumpers (SkyRail, Design/RaceHandling.md): glance off, like toy-track walls. The push is taken
		// across the deck (its plane, not the horizontal: decks bank, roll and loop), with a soft bounce; the car keeps
		// nearly all its speed, turns to run along the rail and takes no damage
		if (Hit.GetComponent() && Hit.GetComponent()->ComponentHasTag(SkyCourse::RailTag()))
		{
			const FVector DeckUp = bGrounded ? Sup.N : Up;
			FVector Nd = N - DeckUp * FVector::DotProduct(N, DeckUp);
			if (Nd.SizeSquared() < 1e-4) continue;   // its top: the support's business
			Nd.Normalize();
			if (Hit.bStartPenetrating) Pos += Nd * (Hit.PenetrationDepth / 100.0 + 0.02);
			else Pos = FromUE(FVector(Hit.Location)) - Lift + Nd * 0.01;
			const double Vn = FVector::DotProduct(Vel, Nd);
			if (Vn < 0)
			{
				const FVector Vt = Vel - Nd * Vn;
				Vel = Vt * (1.0 - RAIL_SCRUB * FMath::Clamp(-Vn / 20.0, 0.0, 1.0)) - Nd * (Vn * RAIL_BOUNCE);
				if (-Vn > 6) Event(ESkyEv::Impact, TEXT("rail"), FMath::Min(-Vn, 12.0));
			}
			// nose into the rail: turn it to run along (most of the way this step), and calm the spin
			const double Into = FVector::DotProduct(Fwd, Nd);
			if (Into < 0)
			{
				const FVector RunDir = (Fwd - Nd * Into * 1.15).GetSafeNormal();
				Q = (RotTo(Fwd, RunDir, 0.6) * Q).GetNormalized();
				YawRate *= 0.5;
				UpdateAxes();
			}
			return;
		}
		if (N.Z > 0.7) continue; // ground under a car on its side or roof: the rest-on-floor clamp handles it
		if (Hit.bStartPenetrating)
		{
			Pos += N * (Hit.PenetrationDepth / 100.0 + 0.02);
			const double Vn = FVector::DotProduct(Vel, N);
			if (Vn < 0) Vel -= N * Vn;
			return;
		}
		const FVector Centre = FromUE(FVector(Hit.Location));
		if (N.Z < -0.7)
		{
			// a ceiling or overhang: stop under it
			Pos = Centre - Lift + N * 0.01;
			const double Vn = FVector::DotProduct(Vel, N);
			if (Vn < 0) Vel -= N * Vn;
			return;
		}
		FVector Nh(N.X, N.Y, 0);
		Nh.Normalize();
		const FVector ImpactSim = FromUE(FVector(Hit.ImpactPoint));
		UPrimitiveComponent* Comp = Hit.GetComponent();
		// a wall the car can ride: still there 2.5 m higher (poles, posts and kerbs aren't), not tagged off
		FHitResult High;
		const FVector Probe = ToUE(ImpactSim + FVector(0, 0, 2.5) + Nh * 0.6);
		const bool bTall = GetWorld()->LineTraceSingleByChannel(High, Probe, Probe - DirToUE(Nh) * 120.0, ECC_Visibility, Params)
			&& FMath::Abs(High.ImpactNormal.Z) < 0.5;
		const bool bNoWall = Comp && Comp->GetOwner() && Comp->GetOwner()->ActorHasTag(TEXT("NoWallRide"));
		const bool bRideable = bTall && !bNoWall && Caps.bWalls;
		const double Vn = FVector::DotProduct(Vel, Nh);
		const double HeadOn = -FVector::DotProduct(Fwd, Nh);
		const double HSpeed = FMath::Sqrt(Vel.X * Vel.X + Vel.Y * Vel.Y);
		const double WheelsFirst = FVector::DotProduct(Up, Nh);
		if (bTall && !bNoWall && !Caps.bWalls && bGrounded && HeadOn > 0.5 && HSpeed > 7) Event(ESkyEv::Locked, TEXT("walls"));
		// in the air, any contact with a tall wall short of roof-first: the fans grab it (RL wall landing)
		if (!bGrounded && !bTumbling && bRideable && WheelsFirst > -0.3 && Vn <= 0.5 && Jump.T > 0.2)
		{
			const double Into = FMath::Max(0.0, -Vn);
			TransitionTo(Nh, Comp, ESurface::Wall, ImpactSim);
			Dodge.bActive = false;
			Jump.bCanDouble = Jump.bFree = Jump.bHolding = false;
			StuckT = 0;
			if (Into > 25 && WheelsFirst < 0.35)
			{
				Hurt((Into - 25) * 0.4 + 5, 0.6);
				Event(ESkyEv::Impact, FString(), Into * 0.5);
			}
			Event(ESkyEv::Touchdown, TEXT("wall"), Into);
			return;
		}
		// drive up the wall: head-on into a tall wall with speed, fans sucking the car on
		if (bGrounded && !bTumbling && HeadOn > 0.5 && HSpeed > 7 && bRideable && Sup.Kind == ESurface::Ground)
		{
			TransitionTo(Nh, Comp, ESurface::Wall, ImpactSim);
			return;
		}
		// round an inside corner from one wall onto the next
		if (bGrounded && Sup.Kind == ESurface::Wall && HeadOn > 0.5 && bRideable && FVector::DotProduct(Nh, Sup.N) < 0.7)
		{
			TransitionTo(Nh, Comp, ESurface::Wall, ImpactSim);
			return;
		}
		// otherwise bounce off it
		Pos = Centre - Lift + Nh * 0.01;
		if (Vn < 0)
		{
			Vel -= Nh * (Vn * 1.35);
			Vel.X *= 0.96;
			Vel.Y *= 0.96;
			if (-Vn > 4)
			{
				Hurt(-Vn, 1.0);
				Event(ESkyEv::Impact, FString(), -Vn);
				if (!bGrounded && -Vn > 9) Tumble(-Vn * 0.12);
			}
		}
		return;
	}
}

void ASkysterCar::TransitionTo(const FVector& N, UPrimitiveComponent* Comp, ESurface Kind, const FVector& HitPoint)
{
	const double Sp = Vel.Size();
	LastSupN = FVector::ZeroVector;   // a jump onto a new surface isn't a curve
	Q = (RotTo(Up, N, 1.0) * Q).GetNormalized();
	UpdateAxes();
	if (Kind == ESurface::Wall)
	{
		Pos.X = HitPoint.X + N.X * 0.05;
		Pos.Y = HitPoint.Y + N.Y * 0.05;
		// off the street the wheels start a little way up the face, clear of the kerb line
		if (GroundY > -900) Pos.Z = FMath::Max(Pos.Z, GroundY + 1.5);
	}
	FVector F = Fwd - N * FVector::DotProduct(Fwd, N);
	F.Normalize();
	Vel = F * (Sp * 0.92);
	bGrounded = true;
	Sup.bOn = true;
	Sup.N = N;
	Sup.Comp = Comp;
	Sup.Kind = Kind;
	W = FVector::ZeroVector;
	YawRate = 0;
	Event(ESkyEv::WallRide, Kind == ESurface::Wall ? TEXT("wall") : TEXT("ground"));
}

void ASkysterCar::ResolveSupport(double H)
{
	UpdateAxes();
	const double Gy = GroundAt(Pos.X, Pos.Y, Pos.Z);
	GroundY = Gy;
	FSupport Out = Sup;
	const bool bFound = FindSupport(Out, bGrounded);
	if (bGrounded)
	{
		if (!bFound || Out.Dist > 0.7)
		{
			// drove off an edge, over the top of a wall or past the end of a ramp
			LeaveSurface();
			Jump.T = 99;
			Jump.bCanDouble = true; // RL: you keep one jump after driving off an edge
			Jump.bFree = true;      // with no timer
			Jump.AirT = 0;
			Jump.Takeoff = Pos;
			Jump.bFromWall = Sup.Kind != ESurface::Ground;
			St.Roll = St.Pitch = St.Yaw = 0;
		}
		else
		{
			// seat on the surface; a new surface kind (ramp to wall etc.) carries over
			Pos = Out.P;
			Sup.N = Out.N;
			Sup.Kind = Out.Kind;
			Sup.Comp = Out.Comp;
			Sup.P = Out.P;
			const double Vn = FVector::DotProduct(Vel, Out.N);
			// race assist (Light/Full) on Course Builder track: small crests keep you on the deck (a jump's lip still
			// launches you: the deck ends there)
			const UPrimitiveComponent* OutComp = Out.Comp.Get();
			const double CrestV = (bInCourseRace && RaceAssist > 0 && OutComp && OutComp->ComponentHasTag(TEXT("SkyTrack"))) ? RACE_CREST : 2.5;
			if (Vn < 0) Vel -= Out.N * Vn;
			else if (Vn > CrestV && Out.Kind == ESurface::Ground)
			{
				// over a crest or off a ramp lip faster than the street falls away: airborne
				LeaveSurface();
				Jump.T = 99;
				Jump.bCanDouble = true;
				Jump.bFree = true;
				Jump.AirT = 0;
				Jump.bFromWall = true;
				Jump.Takeoff = Pos;
			}
		}
	}
	else
	{
		// a crash only takes control away for a moment; after that you can steer and jump out of it
		if (bTumbling && (TumbleT += H) > 0.6) bTumbling = false;
		// airborne: land when a surface is under the wheels and the car is facing it
		// in deep water the car floats: it only lands where the bed comes up to its float line (the banks)
		const bool bFloatOver = bInWater && Out.P.Z < WaterZ - SkyP::WATER_DRAFT - 0.3;
		if (bFound && !bFloatOver && Out.Dist < 0.35 && FVector::DotProduct(Vel, Out.N) <= 0.6)
		{
			const double Align = FVector::DotProduct(Up, Out.N);
			const double Vn = -FVector::DotProduct(Vel, Out.N);
			Sup.N = Out.N;
			Sup.P = Out.P;
			Sup.Kind = Out.Kind;
			Sup.Comp = Out.Comp;
			if (Align > 0.35) LandOn(Vn, Align);
			else CrashLand(Vn, Align);
		}
		// never fall through the floor, even on the roof or nose: rest there, don't bounce
		const double Lift = RestLift();
		if (Pos.Z < Gy + Lift && Gy > -900)
		{
			Pos.Z = Gy + Lift;
			if (Vel.Z < 0)
			{
				const double Vn = -Vel.Z;
				Vel.Z = Vn > 6 ? Vn * 0.2 : 0;
				Vel.X *= 0.6;
				Vel.Y *= 0.6;
				if (Vn > 6)
				{
					Hurt(Vn, 1.3);
					Event(ESkyEv::Impact, FString(), Vn);
					if (Up.Z < 0.45) Tumble(Vn * 0.1);
				}
			}
		}
		// on the roof or side near the ground: after a moment the thrusters flip it back over
		if (Up.Z < 0.45 && FMath::Abs(Vel.Z) < 3 && Pos.Z - Gy < Lift + 0.4)
		{
			StuckT += H;
			if (StuckT > 0.8) RightSelf();
		}
		else StuckT = 0;
	}
}

// --- water (provisional: floats and slows) ----------------------------------------------------------
// The generated city's water surfaces (building-types water_ue.py: L9_River_*, L9_Lake_*, tag "citywater") are flat and
// have no collision, so the car drives through them onto the riverbed. Here: once the body is under the surface, strong
// drag slows it to a crawl and a buoyancy spring holds it at a float line near the surface; R puts it back on the road.

void ASkysterCar::ScanWater()
{
	WaterBoxes.Reset();
	if (!GetWorld()) return;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (!It->ActorHasTag(TEXT("citywater")) && !It->ActorHasTag(TEXT("SkyWater"))) continue;
		const FBox B = It->GetComponentsBoundingBox(true);
		if (B.IsValid) WaterBoxes.Add(B);
	}
}

bool ASkysterCar::WaterSurfaceAt(const FVector& SimPos, double& OutZ) const
{
	// A water surface sits below the street (the channel is cut into the ground), so anywhere inside its box and
	// under its top is in the water: the banks, bridges and streets around it are all above it.
	const FVector P = ToUE(SimPos);
	bool bAny = false;
	for (const FBox& B : WaterBoxes)
	{
		if (P.X < B.Min.X || P.X > B.Max.X || P.Y < B.Min.Y || P.Y > B.Max.Y) continue;
		const double Z = B.Max.Z / 100.0;
		if (SimPos.Z > Z || SimPos.Z < Z - SkyP::WATER_MAX_DEPTH) continue;
		if (!bAny || Z < OutZ) OutZ = Z;
		bAny = true;
	}
	return bAny;
}

void ASkysterCar::WaterForces(double H)
{
	using namespace SkyP;
	double Wz = 0;
	const bool bWet = bAlive && WaterSurfaceAt(Pos, Wz) && Pos.Z < Wz - WATER_WET;
	bInWater = bWet;
	if (!bWet) return;
	WaterZ = Wz;
	// strong drag: the car bleeds speed fast above a crawl and a little below it (the throttle still paddles it along)
	const FVector Hv(Vel.X, Vel.Y, 0);
	const double Hs = Hv.Size();
	if (Hs > 1e-3)
	{
		double NewS = Hs * FMath::Exp(-WATER_DRAG * H);
		if (NewS > WATER_CRAWL) NewS = WATER_CRAWL + (NewS - WATER_CRAWL) * FMath::Exp(-WATER_DRAG_FAST * H);
		Vel.X *= NewS / Hs;
		Vel.Y *= NewS / Hs;
	}
	const double Float = Wz - WATER_DRAFT;
	if (bGrounded && Pos.Z < Float - 0.3)
	{
		// the bed is deeper than the float line: the water lifts the car off it
		LeaveSurface();
		Jump.T = 99;
		Jump.bCanDouble = false;
		Jump.bFree = false;
		Jump.AirT = 0;
		Jump.Takeoff = Pos;
		Vel.Z = FMath::Max(Vel.Z, 0.5);
	}
	if (!bGrounded)
	{
		// buoyancy: cancels gravity (Fly applies it) and springs the car to the float line, well damped
		Vel.Z += (G + WATER_K * (Float - Pos.Z) - WATER_C * Vel.Z) * H;
		// level out on the water and stop spinning
		Q = (RotTo(Up, UPV, 1.0 - FMath::Exp(-WATER_LEVEL * H)) * Q).GetNormalized();
		W *= FMath::Exp(-WATER_SPIN * H);
		UpdateAxes();
	}
}

double ASkysterCar::RestLift() const
{
	return Up.Z < -0.5 ? 1.1 : FMath::Abs(Up.Z) < 0.5 ? 0.85 : 0.0;
}

void ASkysterCar::LandOn(double Vn, double Align)
{
	bGrounded = true;
	Sup.bOn = true;
	Pos = Sup.P;
	Q = (RotTo(Up, Sup.N, 1.0) * Q).GetNormalized();
	UpdateAxes();
	const double Vnow = FVector::DotProduct(Vel, Sup.N);
	if (Vnow < 0) Vel -= Sup.N * Vnow;
	YawRate = FMath::Clamp(-FVector::DotProduct(W, Sup.N), -4.0, 4.0); // land still turning, and slide if it's crooked
	W = FVector::ZeroVector;
	Dodge.bActive = false;
	Jump.bCanDouble = false;
	Jump.bHolding = false;
	bTumbling = false;
	StuckT = 0;
	// only a really hard landing hurts (the cushion keeps normal drops under this); crooked on the sills does too
	if (Vn > 22) Hurt((Vn - 22) * 0.5 + 5, 0.8);
	else if (Align < 0.6 && Vn > 8) Hurt(Vn - 4, 0.6);
	const FString Kind = Sup.Kind == ESurface::Ground ? TEXT("ground") : TEXT("wall");
	if (Vn > 6) Event(ESkyEv::Land, Kind, Vn);
	Event(ESkyEv::Touchdown, Kind, Vn);
}

// Came down on the roof, nose or side: rest against the surface and take a hit for a real impact.
void ASkysterCar::CrashLand(double Vn, double Align)
{
	const FVector N = Sup.N;
	const double Vnow = FVector::DotProduct(Vel, N);
	if (Vnow < 0) Vel -= N * (Vn > 6 ? Vnow * 1.2 : Vnow);
	Vel *= Vn > 6 ? 0.7 : 0.9;
	Pos = Sup.P + N * (Sup.Kind == ESurface::Ground ? RestLift() : 0.7);
	if (Vn > 6)
	{
		// a roof landing from a normal jump is a scrape; a long drop onto the roof is a wreck
		Hurt(Vn - 6, Align < 0 ? 1.1 : 0.9);
		Event(ESkyEv::Impact, TEXT("crash"), Vn);
		Tumble(Vn * 0.15);
	}
	else W *= 0.5;
	Dodge.bActive = false;
	Jump.bCanDouble = false;
}

void ASkysterCar::Tumble(double K)
{
	bTumbling = true;
	W = FVector(FMath::FRandRange(-0.5, 0.5) * K, FMath::FRandRange(-0.5, 0.5) * K, FMath::FRandRange(-0.5, 0.5) * K * 0.5);
	TumbleT = 0;
}

void ASkysterCar::Hurt(double Vn, double Mult)
{
	double Dmg = FMath::Max(0.0, Vn - 5) * 0.75 * Mult;
	// repeated scrapes in quick succession count once, not every frame
	if (SimTime - LastHurt < 0.6) Dmg *= 0.2;
	Dmg = FMath::Min(Dmg, 50.0); // one wreck never totals a full hull; two do
	if (Dmg < 0.5) return;
	LastHurt = SimTime;
	Health = FMath::Max(0.0, Health - Dmg);
	Event(ESkyEv::Damage, FString(), Dmg);
	if (Health <= 0 && bAlive)
	{
		bAlive = false;
		DeadT = 0;
		Event(ESkyEv::Explode);
	}
}

// --- pickups -------------------------------------------------------------------------------

void ASkysterCar::Pickups(double Dt)
{
	if (!bAlive) return;
	const FVector PosUE = ToUE(Pos);
	if (const int32 Pad = World.CollectPad(PosUE))
	{
		BoostTank = FMath::Min(100.0, BoostTank + (Pad == 2 ? 100.0 : 12.0));
		Event(ESkyEv::Pad, FString(), 0, 0, Pad == 2 ? 1 : 0);
	}
	// Fast-charger bays: stop on one and the hull charges for as long as you stay, quickly to 80%
	// (from empty in 15 s), then slower (the last 20% takes 30 s)
	const bool bWas = bCharging;
	const bool bOn = bGrounded && Speed < 3 && Health < 100 && World.ChargerAt(PosUE, SimTime);
	bCharging = bOn;
	if (bOn)
	{
		const double Before = Health;
		Health = FMath::Min(100.0, Health + (Before < CHARGE_TAPER ? CHARGE_FAST : CHARGE_SLOW) * Dt);
		if (!bWas) Event(ESkyEv::Charge, FString(), Before);
		if (Before < CHARGE_TAPER && Health >= CHARGE_TAPER) Event(ESkyEv::Charge80);
		if (Health >= 100) { Event(ESkyEv::Charged); bCharging = false; }
	}
}

// --- combos and stunts ---------------------------------------------------------------------

void ASkysterCar::AddMove(const FString& Name)
{
	Cb.Moves.Add(Name);
	Cb.bActive = true;
	Cb.GroundT = 0;
	Cb.Mult = Cb.Moves.Num();
	const int32 Pts = Skyster::MovePoints(Name);
	Cb.Score += Pts;
	FSkyEvent E;
	E.Type = ESkyEv::Move;
	E.Name = Name;
	E.A = Pts;
	E.B = Cb.Score * Cb.Mult;
	E.I = Cb.Mult;
	E.Moves = Cb.Moves;
	Events.Add(E);
}

void ASkysterCar::BankCombo(const TCHAR* Result)
{
	if (!Cb.bActive) return;
	const bool bLanded = FCString::Strcmp(Result, TEXT("landed")) == 0;
	const double Banked = bLanded ? Cb.Score * Cb.Mult : 0;
	Cb.Total += Banked;
	if (bLanded && Banked > Cb.BestScore) { Cb.BestScore = Banked; Cb.Best = Cb.Mult; }
	FSkyEvent E;
	E.Type = ESkyEv::Combo;
	E.Name = Result;
	E.A = Banked;
	E.B = Cb.Total;
	E.I = Cb.Mult;
	E.Moves = Cb.Moves;
	Events.Add(E);
	Cb.Moves.Reset();
	Cb.Score = 0;
	Cb.Mult = 1;
	Cb.bActive = false;
	Cb.GroundT = 0;
}

void ASkysterCar::TrackStunts(double Dt, const FDriverInput& S)
{
	constexpr double FULL = UE_DOUBLE_PI * 2 * 0.92;
	if (!bGrounded)
	{
		// integrate body rotation in the car frame; each full turn is a move the moment it completes
		const FVector Wl = Q.Inverse().RotateVector(W);
		St.Roll += Wl.X * Dt;
		St.Pitch += Wl.Y * Dt;
		St.Yaw += Wl.Z * Dt;
		Cb.R += Wl.X * Dt;
		Cb.P += Wl.Y * Dt;
		Cb.Y += Wl.Z * Dt;
		if (FMath::Abs(Cb.R) >= FULL) { AddMove(TEXT("barrelroll")); Cb.R -= Sgn(Cb.R) * UE_DOUBLE_PI * 2; }
		if (Cb.P <= -FULL) { AddMove(TEXT("backflip")); Cb.P += UE_DOUBLE_PI * 2; }
		if (Cb.P >= FULL) { AddMove(TEXT("frontflip")); Cb.P -= UE_DOUBLE_PI * 2; }
		if (FMath::Abs(Cb.Y) >= FULL) { AddMove(TEXT("spin")); Cb.Y -= Sgn(Cb.Y) * UE_DOUBLE_PI * 2; }
		if (bHovering) Cb.HoverT += Dt; else Cb.HoverT = FMath::Max(0.0, Cb.HoverT - Dt * 0.5);
		if (Cb.HoverT > 1.2 && !Cb.bHoverDone) { Cb.bHoverDone = true; AddMove(TEXT("hover")); }
		Cb.MaxH = FMath::Max(Cb.MaxH, Pos.Z - GroundY);
		// McGregor: over the fleet line-up
		if (!Cb.bLineupDone && World.OverLineup(ToUE(Pos))) { Cb.bLineupDone = true; AddMove(TEXT("lineup")); }
		Cb.WallT = 0;
		Cb.InvT = 0;
		Cb.GroundT = 0;
	}
	else if (Sup.Kind != ESurface::Ground)
	{
		// riding a wall or hanging from the ceiling keeps the chain alive
		Cb.WallT += Dt;
		if (Cb.WallT > 0.5 && !Cb.bWallDone) { Cb.bWallDone = true; AddMove(TEXT("wallride")); }
		if (Sup.N.Z < -0.45 && FMath::Abs(Vf) < 1.2)
		{
			Cb.InvT += Dt;
			if (Cb.InvT > 0.8 && !Cb.bInvDone) { Cb.bInvDone = true; AddMove(TEXT("inverted")); }
		}
		else Cb.InvT = 0;
		Cb.GroundT = 0;
		Cb.bHoverDone = false;
	}
	else
	{
		// flat ground: a short grace to jump straight back into the chain, then it banks
		Cb.WallT = 0;
		Cb.bWallDone = false;
		Cb.InvT = 0;
		Cb.bInvDone = false;
		Cb.bHoverDone = false;
		if (Cb.bActive && !Macro.bOn && (Cb.GroundT += Dt) > 0.6) BankCombo(TEXT("landed"));
	}
	const TArray<FSkyEvent> Snapshot = Events;
	for (const FSkyEvent& E : Snapshot)
	{
		if (E.Type == ESkyEv::Damage && E.A > 2 && Cb.bActive) BankCombo(TEXT("dropped"));
		if (E.Type != ESkyEv::Touchdown) continue;
		const double Roll = FMath::Abs(St.Roll), Pitch = FMath::Abs(St.Pitch);
		const double Dist = FVector::Dist2D(Pos, Jump.Takeoff);
		const double AirT = Jump.AirT;
		if (E.Name != TEXT("ground"))
		{
			// wheels onto a wall mid-flight: a flip reset (from the ground) or wall-to-wall (from a wall)
			if (AirT > 0.3) AddMove(Jump.bFromWall ? TEXT("walltowall") : TEXT("flipreset"));
		}
		else
		{
			if (Jump.bFromWall && Roll + Pitch > 1.3 && AirT > 0.6) AddMove(TEXT("walllaunch"));
			else if (Roll > UE_DOUBLE_PI * 1.7 && Dist < 4.5 && Dist > 0.6 && AirT < 2.2) AddMove(TEXT("parallel"));
			// the McGregor kickflip: a full barrel roll on the move, over whatever was in the way
			else if (Roll > UE_DOUBLE_PI * 1.7 && Dist > 8) AddMove(TEXT("kickflip"));
			if (SimTime - Cb.LastDodge < 0.35 && Cb.DodgeF > 0.5 && E.A < 10) AddMove(TEXT("wavedash"));
			if (AirT > 2.5) AddMove(TEXT("bigair"));
			if (Cb.MaxH > 25) AddMove(TEXT("highflyer"));
		}
		St.Roll = St.Pitch = St.Yaw = 0;
		Cb.R = Cb.P = Cb.Y = 0;
		Cb.MaxH = 0;
		Cb.HoverT = 0;
		Cb.bLineupDone = false;
	}
	// supersonic
	if (Speed > SUPERSONIC && !St.bSuperDone) { St.bSuperDone = true; Event(ESkyEv::Stunt, TEXT("supersonic")); }
	if (Speed < 40) St.bSuperDone = false;
	// 0-60 timer: starts from rest with throttle, stops at 60 mph
	if (!St.bSixtyOn && St.bSixtyRest && (S.Throttle > 0.5 || bBoosting)) { St.bSixtyOn = true; St.SixtyT = 0; }
	if (St.bSixtyOn)
	{
		St.SixtyT += Dt;
		if (Speed >= SIXTY) { St.bSixtyOn = false; Event(ESkyEv::Sixty, FString(), St.SixtyT); }
		else if ((S.Throttle < 0.3 && !bBoosting) || St.SixtyT > 6) St.bSixtyOn = false;
	}
}

// --- scripted manoeuvres (the demo moves, through the same physics) -------------------------

bool ASkysterCar::StartMacro(const FString& Name, double Side)
{
	if (bTumbling || Macro.bOn) return false;
	if ((Name == TEXT("kickflip") || Name == TEXT("parallel")) && !Caps.bDoubleJump) { Event(ESkyEv::Locked, TEXT("doubleJump")); return true; }
	if (!bGrounded)
	{
		if (Name == TEXT("launch"))
		{
			FVector D(Fwd.X, Fwd.Y, 0);
			if (D.SizeSquared() < 0.01) D = FVector(1, 0, 0);
			Macro = FMacro();
			Macro.bOn = true;
			Macro.Name = Name;
			Macro.Side = Side;
			Macro.Phase = 2;
			Macro.Dir = D.GetSafeNormal();
			return true;
		}
		// in the air the move spends the second jump (kickflip = a pure barrel roll keeping momentum)
		if (!Jump.bCanDouble || (!Jump.bFree && Jump.T >= DOUBLE_T) || Dodge.bActive) return false;
		StartDodge(0, Side, Name == TEXT("kickflip") ? 0.0 : 1.0);
		Jump.bCanDouble = false;
		Jump.bHolding = false;
		return true;
	}
	Macro = FMacro();
	Macro.bOn = true;
	Macro.Name = Name;
	Macro.Side = Side;
	Macro.Phase = 0;
	return true;
}

// A first jump at a chosen speed: the show's hops are smaller than a Rocket League jump.
void ASkysterCar::Hop(double V)
{
	Vel += Up * V;
	Jump.T = 0;
	Jump.AirT = 0;
	Jump.bCanDouble = true;
	Jump.bHolding = false;
	Jump.HoldT = 0;
	Jump.bFromWall = Sup.Kind != ESurface::Ground;
	Jump.Takeoff = Pos;
	LeaveSurface();
	BurstAll(1);
	Event(ESkyEv::Jump);
	St.Roll = St.Pitch = St.Yaw = 0;
}

void ASkysterCar::RunMacro(double Dt, const FDriverInput& Live)
{
	FMacro& M = Macro;
	FDriverInput& S = M.S;
	M.T += Dt;
	S.bJumpHit = false;
	S.Throttle = Live.Throttle;
	S.Brake = Live.Brake;
	S.Stop = Live.Stop;
	S.Steer = Live.Steer;
	S.bBoost = Live.bBoost;
	if (M.Name == TEXT("kickflip"))
	{
		// the demo kickflip: a full jump on the move and one barrel roll over the top (over the line-up
		// at McGregor), no sideways shove, landing on the wheels still going forward
		if (M.Phase == 0) { S.bJumpHit = true; S.bJump = true; M.Phase = 1; }
		else if (M.Phase == 1 && M.T > 0.4)
		{
			M.Phase = 2;
			S.bJump = false;
			if (Jump.bCanDouble) { StartDodge(0, M.Side, 0); Jump.bCanDouble = false; }
		}
		else if (M.Phase == 1) S.bJump = true;
		else if (M.Phase == 2) { S.bJump = false; if (bGrounded && M.T > 1) M.bOn = false; }
		if (M.T > 4) M.bOn = false;
	}
	else if (M.Name == TEXT("parallel"))
	{
		// the demo's parallel park: a low hop, one sideways barrel roll, down one car-width over
		if (M.Phase == 0) { Hop(9.5); M.Phase = 1; }
		else if (M.Phase == 1 && M.T > 0.06)
		{
			M.Phase = 2;
			if (Jump.bCanDouble) { StartDodge(0, M.Side, 0.16); Jump.bCanDouble = false; }
		}
		else if (M.Phase == 2 && bGrounded && M.T > 0.6) M.bOn = false;
		if (M.T > 4) M.bOn = false;
	}
	else if (M.Name == TEXT("launch"))
	{
		// the wall launch: push off the wall, pitch over until the wheels face the sky with the nose
		// pointing away from the wall, then half a barrel roll onto the wheels, landing facing away
		if (M.Phase == 0)
		{
			FVector D = FVector(Up.X, Up.Y, 0) + FVector(Fwd.X, Fwd.Y, 0) * 0.5;
			if (D.SizeSquared() < 0.01) D = FVector(Fwd.X, Fwd.Y, 0);
			if (D.SizeSquared() < 0.01) D = FVector(-1, 0, 0);
			M.Dir = D.GetSafeNormal();
			Hop(JUMP_V);
			Vel.Z += 4; // the floor thrusters lob it a little for air time
			M.Phase = 1;
		}
		else if (M.Phase == 1)
		{
			Aim(S, M.Dir, DOWNV, M.Side);
			if (M.T > 0.25 && ((Up.Z < -0.8 && FVector::DotProduct(Fwd, M.Dir) > 0.8) || M.T > 1.1)) M.Phase = 2;
		}
		else if (M.Phase == 2)
		{
			Aim(S, M.Dir, UPV, M.Side);
		}
		if (bGrounded && M.T > 0.8) M.bOn = false;
		if (M.T > 5 || bTumbling) M.bOn = false;
	}
	else M.bOn = false;
}

// Air-control inputs that turn the car toward a target heading and roof direction, using RL's
// torques and damping to do the work (js: Vehicle.aim). A half roll is ambiguous; Side picks.
void ASkysterCar::Aim(FDriverInput& S, const FVector& FwdT, const FVector& UpT, double Side)
{
	FVector L = FVector::CrossProduct(UpT, FwdT);
	if (L.SizeSquared() < 1e-6) L = FVector::CrossProduct(UpT, FVector(-FwdT.Y, FwdT.X, 0));
	L.Normalize();
	const FVector U = FVector::CrossProduct(FwdT, L).GetSafeNormal();
	const FVector F = FVector::CrossProduct(L, U);
	const FQuat Target(FMatrix(F, L, U, FVector::ZeroVector));
	const FQuat Inv = Q.Inverse();
	const FVector Wl = Inv.RotateVector(W);
	FQuat Need = Inv * Target; // rotation still needed, in the car frame
	if (Need.W < 0) Need = FQuat(-Need.X, -Need.Y, -Need.Z, -Need.W);
	const double Ang = 2 * FMath::Acos(FMath::Clamp(Need.W, -1.0, 1.0));
	const double Sn = FMath::Sqrt(FMath::Max(0.0, 1 - Need.W * Need.W));
	double Er = 0, Ep = 0, Ey = 0; // roll (x), pitch (y), yaw (z)
	if (Sn > 1e-5) { Er = Need.X / Sn * Ang; Ep = Need.Y / Sn * Ang; Ey = Need.Z / Sn * Ang; }
	if (Ang > 2.8 && FMath::Abs(Er) > FMath::Abs(Ep) + FMath::Abs(Ey)) Er = FMath::Abs(Er) * (Side != 0 ? Side : 1);
	S.Pitch = FMath::Clamp(3 * Ep - 0.6 * Wl.Y, -1.0, 1.0);
	S.Yaw = FMath::Clamp(-(3 * Ey - 0.6 * Wl.Z), -1.0, 1.0);
	S.Roll = FMath::Clamp(3 * Er - 0.6 * Wl.X, -1.0, 1.0);
	S.bAirRoll = false;
}

// --- events -> toasts (js main.js handleEvents) ----------------------------------------------

void ASkysterCar::HandleEvents()
{
	for (const FSkyEvent& E : Events)
	{
		switch (E.Type)
		{
		case ESkyEv::Flight:
			if (SimTime - FlightTip > 25) { FlightTip = SimTime; Toast(TEXT("Flight mode"), TEXT("stick turns and climbs · RT thrust · LT air brake · B boost · let go of LB to drop")); }
			break;
		case ESkyEv::Landing: Toast(TEXT("Landing protocol"), TEXT("wheels down, nose along the travel, thrusters braking the fall")); break;
		case ESkyEv::AirBrake: Toast(TEXT("Air brake"), TEXT("slowing down and turning wheels-down")); break;
		case ESkyEv::Land: DustRing(E.A); KnockShake = FMath::Min(1.2, KnockShake + FMath::Clamp(E.A / 28.0, 0.08, 1.0)); break;
		case ESkyEv::Impact: KnockShake = FMath::Min(1.2, KnockShake + FMath::Clamp(E.A / 30.0, 0.1, 1.0)); BurstSparks(ToUE(Pos) + FVector(0, 0, 50), FMath::Min(50, 8 + (int32)E.A), FLinearColor(4.0f, 2.2f, 0.6f), 9); break;
		case ESkyEv::Explode:
			KnockShake = 1.2;
			ExplodeFX();
			ShowBody(false);
			Toast(TEXT("Hull breached"), TEXT("Thrusters offline · respawning"));
			break;
		case ESkyEv::Damage: HurtFlash = FMath::Min(1.0, HurtFlash + E.A / 40); break;
		case ESkyEv::Pad:
			BurstSparks(ToUE(Pos) + FVector(0, 0, 80), E.I ? 60 : 18, FLinearColor(1.5f, 2.6f, 3.4f), E.I ? 10 : 6);
			if (E.I) Toast(TEXT("Tank full"), TEXT("10,000 psi"));
			break;
		case ESkyEv::Charge:
			BurstSparks(ToUE(Pos) + FVector(0, 0, 100), 30, FLinearColor(0.8f, 3.0f, 1.2f), 7);
			Toast(TEXT("Fast charging"), E.A < CHARGE_TAPER
				? FString::Printf(TEXT("stay on the pad · %d%% now · 80%% in %d s, then slower"), FMath::RoundToInt(E.A), FMath::CeilToInt((CHARGE_TAPER - E.A) / CHARGE_FAST))
				: FString(TEXT("stay on the pad · above 80% it charges slowly")));
			break;
		case ESkyEv::Charge80: Toast(TEXT("80% charged"), TEXT("the last 20% is slower · 30 s to full")); break;
		case ESkyEv::Charged: Toast(TEXT("Fully charged"), TEXT("hull 100%")); break;
		case ESkyEv::Move: ComboShowT = 1.6; break;
		case ESkyEv::Combo:
			if (E.Name == TEXT("landed")) Toast(FString::Printf(TEXT("+%s"), *FText::AsNumber((int64)E.A).ToString()), FString::Printf(TEXT("combo x%d · %s"), E.I, *Skyster::MoveList(E.Moves)));
			else if (E.Moves.Num() > 1) Toast(TEXT("Combo dropped"), Skyster::MoveList(E.Moves));
			ComboShowT = 1.6;
			break;
		case ESkyEv::Stunt: if (E.Name == TEXT("supersonic")) Toast(TEXT("Supersonic"), TEXT("217+ mph")); break;
		case ESkyEv::Sixty:
			LastSixty = E.A;
			if (BestSixty < 0 || E.A < BestSixty) BestSixty = E.A;
			break;
		default: break;
		}
	}
}

// --- presentation -------------------------------------------------------------------------

void ASkysterCar::ApplyToActor(float Dt)
{
	const FRotator Rot = FRotationMatrix::MakeFromXZ(DirToUE(Fwd), DirToUE(Up)).Rotator();
	SetActorLocationAndRotation(ToUE(Pos), Rot, false, nullptr, ETeleportType::None);
	// body squat, dive and roll (js car.js): nose up under throttle, down under braking, lean in turns
	BodyPitch = Damp(BodyPitch, FMath::Clamp(-AccelLong * 0.0007, -0.04, 0.04), 6, Dt);
	BodyRoll = Damp(BodyRoll, FMath::Clamp(AccelLat * 0.0009, -0.06, 0.06), 6, Dt);
	const double Dull = Health < 35 ? 0.012 * (1 - Health / 35) : 0.0;
	Chassis->SetRelativeRotation(FRotator(FMath::RadiansToDegrees(-BodyPitch), 0, FMath::RadiansToDegrees(BodyRoll + Dull)));
	if (bRig && Dt > 0) AnimateRig(Dt);
}

// Thruster state (js vehicle.updateJets): the four rear plumes follow the boost, the six floor jets the jumps,
// flips, hover, flight, landing cushion and air brake, and the stick in the air.
void ASkysterCar::UpdateJets(double Dt, const FDriverInput& S)
{
	double Rear = bBoosting ? 1.0 : 0.0;
	double Want[6] = { 0, 0, 0, 0, 0, 0 };
	auto All = [&Want](double K) { for (double& W : Want) W = FMath::Max(W, K); };
	if (bHovering) All(0.9);
	if (bFlying) { All(0.4 + FlyLift * 0.55); Rear = FMath::Max(Rear, S.Throttle * 0.7); }
	if (Cushion > 0) All(0.8);
	if (bAirBraking) All(0.75);
	if (Jump.bHolding && Jump.HoldT < JUMP_HOLD_T && !bGrounded) All(0.7);
	if (!bGrounded && !Dodge.bActive && !bTumbling)
	{
		const double P = S.Pitch, R = S.Roll, Y = S.Yaw;
		if (P > 0.1) { Want[4] = FMath::Max(Want[4], P * 0.6); Want[5] = FMath::Max(Want[5], P * 0.6); }
		if (P < -0.1) { Want[0] = FMath::Max(Want[0], -P * 0.6); Want[1] = FMath::Max(Want[1], -P * 0.6); }
		if (R > 0.1) for (int32 i : { 0, 2, 4 }) Want[i] = FMath::Max(Want[i], R * 0.55);
		if (R < -0.1) for (int32 i : { 1, 3, 5 }) Want[i] = FMath::Max(Want[i], -R * 0.55);
		if (Y > 0.1) { Want[5] = FMath::Max(Want[5], Y * 0.3); Want[0] = FMath::Max(Want[0], Y * 0.3); }
		if (Y < -0.1) { Want[4] = FMath::Max(Want[4], -Y * 0.3); Want[1] = FMath::Max(Want[1], -Y * 0.3); }
	}
	if (Dodge.bActive && Dodge.T < 0.25)
	{
		if (Dodge.Spin.Y > 1) { Want[4] = Want[5] = 1; }
		if (Dodge.Spin.Y < -1) { Want[0] = Want[1] = 1; }
		if (Dodge.Spin.X > 1) { Want[0] = Want[2] = Want[4] = 1; }
		if (Dodge.Spin.X < -1) { Want[1] = Want[3] = Want[5] = 1; }
		Rear = FMath::Max(Rear, Dodge.Spin.Y > 1 ? 0.5 : 0.0);
	}
	for (int32 i = 0; i < 6; ++i)
	{
		JetBurst[i] = Damp(JetBurst[i], 0, 5, Dt);
		const double T = FMath::Max(Want[i], JetBurst[i]);
		JetDown[i] = Damp(JetDown[i], T, T > JetDown[i] ? 24 : 9, Dt);
	}
	JetRear = Damp(JetRear, Rear, Rear > JetRear ? 20 : 8, Dt);
	// side thrusters: in the air they show the yaw torque the car already has, the stick's turn plus the damping that
	// steadies it (Fly's T_YAW / D_YAW): the left one fires to swing the nose right, the right one to swing it left
	double Side = 0;
	if (!bGrounded && !bTumbling && (!Dodge.bActive || Dodge.T > DODGE_LOCK))
	{
		const double Wz = Q.Inverse().RotateVector(W).Z;     // car-frame yaw rate, + = turning left
		Side = S.Yaw + (D_YAW / T_YAW) * Wz * (1 - FMath::Abs(S.Yaw));
	}
	for (int32 i = 0; i < 2; ++i)
	{
		const double T = FMath::Clamp(i == 0 ? Side : -Side, 0.0, 1.0);
		const double Tw = T > 0.08 ? T : 0.0;
		JetSide[i] = Damp(JetSide[i], Tw, Tw > JetSide[i] ? 24 : 9, Dt);
	}
	if (TestJets > 0)
	{
		JetRear = TestJets;
		for (double& D : JetDown) D = TestJets * 0.9;
		for (double& D : JetSide) D = TestJets * 0.9;
	}
}

// The rig's moving parts and the plumes (js car.js animateModel / thrusters).
void ASkysterCar::AnimateRig(double Dt)
{
	using namespace SkyRig;
	RigT += Dt;
	const FVector F(RIG_FWD, 0, 0);
	// wheels: roll with the road (decaying in the air), front pair steered with Ackermann geometry
	for (int32 i = 0; i < 4; ++i)
	{
		WheelRate[i] = bGrounded ? Vf / WHEEL_R[i] : WheelRate[i] * FMath::Exp(-0.6 * Dt);
		WheelSpin[i] = FMath::Fmod(WheelSpin[i] + WheelRate[i] * Dt, UE_DOUBLE_PI * 2);
	}
	double SteerL = SteerAngle, SteerR = SteerAngle;
	if (FMath::Abs(SteerAngle) > 1e-4)
	{
		const double Lw = WHEELBASE, Tw = 1.70, Rr = Lw / FMath::Tan(FMath::Abs(SteerAngle));
		const double Inner = FMath::Atan(Lw / (Rr - Tw / 2)), Outer = FMath::Atan(Lw / (Rr + Tw / 2));
		// a right turn (+) has the right wheel inside
		SteerL = Sgn(SteerAngle) * (SteerAngle > 0 ? Outer : Inner);
		SteerR = Sgn(SteerAngle) * (SteerAngle > 0 ? Inner : Outer);
	}
	for (int32 i = 0; i < 4; ++i)
	{
		const double Steer = i == 0 ? SteerL : i == 1 ? SteerR : 0.0;
		RigWheels[i]->SetRelativeRotation(FRotator(-FMath::RadiansToDegrees(WheelSpin[i]), FMath::RadiansToDegrees(Steer), 0));
	}
	for (int32 i = 0; i < AltNum; ++i)
	{
		// same rolling distance as the Roadster's wheel on that corner, over this wheel's radius
		const int32 K = AltAxle[i];
		AltSpin[i] = FMath::Fmod(AltSpin[i] + WheelRate[K] * WHEEL_R[K] / AltR[i] * Dt, UE_DOUBLE_PI * 2);
		const double Steer = AltSteer[i] ? (K == 0 ? SteerL : SteerR) : 0.0;
		AltWheels[i]->SetRelativeRotation(FRotator(-FMath::RadiansToDegrees(AltSpin[i]), FMath::RadiansToDegrees(Steer), 0));
	}
	// front wing: up as an air brake (hard braking on the road, or the air brake), trimmed by the climb in flight
	const bool bGroundBrake = bGrounded && bBraking && Vf > 18;
	const double WingT = (bGroundBrake || (bAirBraking && Speed > 5)) ? -35.0 : bFlying ? FMath::RadiansToDegrees(-0.35 * FlyClimb) : 0.0;
	WingAng = Damp(WingAng, WingT, 6, Dt);
	RigWing->SetRelativeRotation(FQuat(AXIS_X, FMath::DegreesToRadians(-WingAng)));
	// tail spoiler: pushes out at speed, braking, in the air and at start-up; tilts to 35 degrees as an air brake
	const bool bOut = Vf > 22 || bBraking || !bGrounded || SimTime - SpawnT < 1.5;
	PushK = Damp(PushK, bOut ? 1.0 : 0.0, 5, Dt);
	double SpT = (bGroundBrake || (bAirBraking && Speed > 5)) ? 35.0 : bFlying ? FMath::RadiansToDegrees(0.05) : !bGrounded ? FMath::RadiansToDegrees(0.03) : Vf > 22 ? FMath::RadiansToDegrees(0.12) : 0.0;
	if (Health < 35) SpT += FMath::RadiansToDegrees(0.2 + 0.05 * FMath::Sin(RigT * 9));
	SpoilerAng = Damp(SpoilerAng, SpT, 7, Dt);
	const FVector Push = PUSH_DIR * (24.0 * PushK);
	RigPush->SetRelativeLocation(F + Push);
	RigSpoiler->SetRelativeLocation(SPOILER + F + Push);
	RigSpoiler->SetRelativeRotation(FQuat(AXIS_X, FMath::DegreesToRadians(-SpoilerAng)));
	// headlight panels tip open with the headlights (the right one sticks at 60% below 45% hull)
	PanelK[0] = Damp(PanelK[0], bLights ? 1.0 : 0.0, 8, Dt);
	PanelK[1] = Damp(PanelK[1], bLights ? (Health < 45 ? 0.6 : 1.0) : (Health < 45 ? 0.6 : 0.0), 8, Dt);
	RigPanelL->SetRelativeRotation(FQuat(PANEL_AXIS_L, FMath::DegreesToRadians(-6.0 * PanelK[0])));
	RigPanelR->SetRelativeRotation(FQuat(PANEL_AXIS_R, FMath::DegreesToRadians(-6.0 * PanelK[1])));
	// side baffles open with speed, in flight, or with the fans working hard
	BaffleK = Damp(BaffleK, FMath::Max3(Smooth(30, 55, Speed), bFlying ? 1.0 : 0.0, Fans > 0.8 ? 1.0 : 0.0), 4, Dt);
	RigBaffleL->SetRelativeLocation(F + BAFFLE_L * (1.9 * BaffleK));
	RigBaffleR->SetRelativeLocation(F + BAFFLE_R * (1.9 * BaffleK));
	for (auto& L : HeadBeams) if (L && L->IsVisible() != (bLights && bAlive)) L->SetVisibility(bLights && bAlive);
	// lamps: daytime running lights, brighter with the headlights; tail lights brighter braking
	if (MatHead) MatHead->SetScalarParameterValue(TEXT("Strength"), bLights ? 9.0f : 5.0f);
	if (MatTail) MatTail->SetScalarParameterValue(TEXT("Strength"), bBraking ? 6.0f : 2.4f);
	// plumes: rear ones with the boost, floor ones with the jets; fuel add-ons recolour and stretch them
	const FLook L = Look(TestLook.IsEmpty() ? Progress.BestAddon() : TestLook);
	const double Flick = 0.85 + 0.15 * FMath::Sin(RigT * 61) * FMath::Sin(RigT * 37);
	double MaxDown = 0;
	for (double D : JetDown) MaxDown = FMath::Max(MaxDown, D);
	if (MatRear) { MatRear->SetVectorParameterValue(TEXT("Color"), L.Rear); MatRear->SetScalarParameterValue(TEXT("Strength"), (float)FMath::Clamp(JetRear * 0.85, 0.0, 0.9) * (L.bFire ? 3.4f : 1.3f)); }
	if (MatDown) { MatDown->SetVectorParameterValue(TEXT("Color"), L.Down); MatDown->SetScalarParameterValue(TEXT("Strength"), 3.0f); }
	if (MatCore) { MatCore->SetVectorParameterValue(TEXT("Color"), L.Core); MatCore->SetScalarParameterValue(TEXT("Strength"), (float)FMath::Clamp(FMath::Max(JetRear, MaxDown) * 0.9, 0.0, 0.95) * 1.2f); }
	if (MatFlame) { MatFlame->SetVectorParameterValue(TEXT("Color"), L.Fire); MatFlame->SetScalarParameterValue(TEXT("Strength"), 6.0f); }
	// Raptor tech and rocket fuel show shock diamonds in the plume and the flame
	if (MatRear) MatRear->SetScalarParameterValue(TEXT("Diamonds"), L.bFire ? 0.7f : 0.0f);
	if (MatFlame) MatFlame->SetScalarParameterValue(TEXT("Diamonds"), 1.2f);
	for (int32 i = 0; i < 4; ++i)
	{
		const bool bOn = JetRear > 0.02 && bAlive;
		RearJets[i]->SetVisibility(bOn);
		RearCores[i]->SetVisibility(bOn);
		RearJets[i]->SetRelativeScale3D(FVector(0.15 + JetRear * 2.4 * Flick * L.Len, 0.85 + JetRear * 0.3, 0.85 + JetRear * 0.3));
		RearCores[i]->SetRelativeScale3D(FVector(0.1 + JetRear * 1.5 * Flick * L.Len, 0.47, 0.47));
		// Raptor tech and rocket fuel burn a flame inside the plume
		const double Fl = 0.85 + 0.15 * FMath::Sin(RigT * 47 + i * 1.7);
		Flames[i]->SetVisibility(L.bFire && bOn && JetRear > 0.3);
		Flames[i]->SetRelativeScale3D(FVector(JetRear * 1.6 * Fl * L.Len, 0.7, 0.7));
	}
	for (int32 i = 0; i < 6; ++i)
	{
		const double K = JetDown[i];
		const bool bOn = K > 0.02 && bAlive;
		DownJets[i]->SetVisibility(bOn);
		DownCores[i]->SetVisibility(bOn);
		DownJets[i]->SetRelativeScale3D(FVector(0.1 + K * 0.6 * Flick, 0.8 + K * 0.3, 0.8 + K * 0.3));
		DownCores[i]->SetRelativeScale3D(FVector(0.08 + K * 0.4 * Flick, 0.8 * 0.47, 0.8 * 0.47));
	}
	for (int32 i = 0; i < 2; ++i)
	{
		const double K = JetSide[i];
		const bool bOn = K > 0.02 && bAlive;
		SideJets[i]->SetVisibility(bOn);
		SideCores[i]->SetVisibility(bOn);
		SideJets[i]->SetRelativeScale3D(FVector(0.1 + K * 0.5 * Flick, 0.55 + K * 0.2, 0.55 + K * 0.2));
		SideCores[i]->SetRelativeScale3D(FVector(0.08 + K * 0.32 * Flick, 0.55 * 0.47, 0.55 * 0.47));
	}
}

// --- particles (js main.js emitContinuous, dustRing, burstSparks, explode) -----------------------

int32 ASkysterCar::FxCount(double Rate, double Dt)
{
	const double E = FMath::Max(0.0, Rate * Dt);
	const int32 N = (int32)E;
	return N + (FxRand.FRand() < E - N ? 1 : 0);
}

// Vapour off the nozzles (tinted by the fuel, with flames for Raptor tech and rocket fuel), gas splashing off the
// ground under the floor jets, tyre smoke in slides and hard braking, and smoke, sparks and fire when damaged.
// js emits per frame at 60 fps; here the same rates per second, spread back along the frame's travel.
void ASkysterCar::UpdateFX(double Dt)
{
	using namespace SkyRig;
	const FVector FwdU = DirToUE(Fwd), UpU = DirToUE(Up), VelU = DirToUE(Vel) * 100.0;
	auto Rn = [this](double A, double B) { return (float)FxRand.FRandRange(A, B); };
	auto Along = [&](const FVector& P) { return P - VelU * (Dt * FxRand.FRand()); };
	const FLook L = Look(TestLook.IsEmpty() ? Progress.BestAddon() : TestLook);
	const float RearFloor = GroundY > -900 ? (float)(GroundY * 100.0 + 25.0) : -1e9f;
	if (bRig && bAlive && JetRear > 0.05)
	{
		for (int32 i = 0; i < 4; ++i)
		{
			const FVector N = RearJets[i]->GetComponentLocation();
			if (L.bFire)
			{
				for (int32 k = FxCount(JetRear * L.FireRate * 60, Dt); k > 0; --k)
				{
					const double Sp = L.FireSpeed * Rn(0.7, 1.3) * 100;
					FirePool.Emit(Along(N), -FwdU * Sp + VelU * 0.92 + FVector(Rn(-50, 50), Rn(-50, 50), Rn(-50, 50)), Rn(0.14, 0.26), L.FireSize * 100, 220, L.Fire, 1.f, 1.2f);
				}
			}
			// (half as many again as js, each fainter, so the trail reads as one plume rather than separate puffs)
			for (int32 k = FxCount(FMath::Min(1.0, JetRear * 1.3) * 90, Dt); k > 0; --k)
			{
				const double Sp = Rn(12, 21) * 100;
				VaporPool.Emit(Along(N), -FwdU * Sp + VelU * 0.75 + FVector(Rn(-100, 100), Rn(-100, 100), Rn(-45, 105)), Rn(0.9, 1.5), 35, 330, L.Vapor, L.Vapor.A * 1.3f, 2.5f, 0.f, RearFloor);
			}
		}
	}
	if (bRig && bAlive)
	{
		// thick smoke columns straight out of each nozzle; with the car upright they reach the ground and roll out along it
		const float Floor = (GroundY > -900 && UpU.Z > 0.3) ? (float)(GroundY * 100.0 + 25.0) : -1e9f;
		for (int32 i = 0; i < 6; ++i)
		{
			const double K = JetDown[i];
			if (K < 0.08) continue;
			const FVector N = DownJets[i]->GetComponentLocation() - UpU * 25.0;
			for (int32 k = FxCount(FMath::Min(1.0, K * 1.1) * 40, Dt); k > 0; --k)
			{
				const double Sp = (9 + K * 5 + Rn(0, 3)) * 100;
				VaporPool.Emit(Along(N), -UpU * Sp + VelU * 0.5 + FVector(Rn(-80, 80), Rn(-80, 80), Rn(-60, 60)), Rn(1.8, 2.6), 45, 190, FLinearColor(0.93f, 0.95f, 0.98f), 0.42f, 0.9f, 0.f, Floor);
			}
		}
		// short puffs out of the side thrusters
		for (int32 i = 0; i < 2; ++i)
		{
			const double K = JetSide[i];
			if (K < 0.1) continue;
			const FVector Out = -SideJets[i]->GetForwardVector();          // the cone points -X
			const FVector N = SideJets[i]->GetComponentLocation() + Out * 20.0;
			for (int32 k = FxCount(K * 22, Dt); k > 0; --k)
			{
				VaporPool.Emit(Along(N), Out * (6 + K * 4 + Rn(0, 2)) * 100 + VelU * 0.6 + FVector(Rn(-40, 40), Rn(-40, 40), Rn(-30, 30)), Rn(0.7, 1.1), 25, 110, FLinearColor(0.93f, 0.95f, 0.98f), 0.32f, 1.0f);
			}
		}
	}
	// tyre smoke under powerslide and heavy braking
	if (bRig && bAlive && bGrounded && ((bDrifting && Speed > 9) || (bBraking && Speed > 26)))
	{
		for (int32 w : { 2, 3 })
		{
			const FVector P = RigWheels[w]->GetComponentLocation() - UpU * 20.0;
			for (int32 k = FxCount(60, Dt); k > 0; --k)
			{
				VaporPool.Emit(Along(P), VelU * 0.2 + FVector(Rn(-100, 100), Rn(-100, 100), Rn(80, 180)), 1.6f, 70, 280, FLinearColor(0.62f, 0.62f, 0.64f), 0.28f, 1.4f);
			}
		}
	}
	// damage: grey smoke, then black smoke and sparks, then fire from the rear deck
	if (bAlive && Health < 65)
	{
		const FVector P = Chassis->GetComponentTransform().TransformPosition(FVector(-150.0 + RIG_FWD, 0, 95));
		const double H = Health;
		const float Dark = H < 35 ? 0.12f : 0.45f;
		for (int32 k = FxCount((H < 18 ? 0.9 : H < 35 ? 0.6 : 0.25) * 60, Dt); k > 0; --k)
		{
			VaporPool.Emit(Along(P), FVector(VelU.X * 0.5 + Rn(-50, 50), VelU.Y * 0.5 + Rn(-50, 50), Rn(150, 350)), Rn(1.6, 2.6), 50, 240, FLinearColor(Dark, Dark, Dark), H < 35 ? 0.6f : 0.35f, 1.2f, -60.f);
		}
		if (H < 35)
		{
			for (int32 k = FxCount(0.06 * 60, Dt); k > 0; --k) BurstSparks(P, 6, FLinearColor(4.0f, 2.2f, 0.6f), 6);
		}
		if (H < 18)
		{
			for (int32 k = FxCount(0.8 * 60, Dt); k > 0; --k)
			{
				FirePool.Emit(P + FVector(Rn(-30, 30), Rn(-30, 30), 0), FVector(VelU.X * 0.4, VelU.Y * 0.4, Rn(150, 400)), Rn(0.3, 0.7), 50, 120, FLinearColor(3.2f, 1.2f, 0.25f), 0.9f, 2.f, -200.f);
			}
		}
	}
	FVector Cam = Camera ? Camera->GetComponentLocation() : GetActorLocation();
	if (bAIDriver)
	{
		// an opponent has no camera of its own: its particles face the player's view
		const APlayerController* PC = GetWorld()->GetFirstPlayerController();
		if (PC && PC->PlayerCameraManager) Cam = PC->PlayerCameraManager->GetCameraLocation();
	}
	VaporPool.Update(Dt, Cam);
	FirePool.Update(Dt, Cam);
	SparkPool.Update(Dt, Cam);
}

// A ring of dust thrown out from under the car on a hard landing.
void ASkysterCar::DustRing(double Strength)
{
	const FVector Nn = DirToUE(Sup.N), FwdU = DirToUE(Fwd), LeftU = DirToUE(Left), P0 = ToUE(Pos);
	const int32 Count = FMath::Min(60, 10 + (int32)(Strength * 2));
	for (int32 i = 0; i < Count; ++i)
	{
		const double A = (double)i / Count * 2 * PI;
		const FVector Off = (LeftU * FMath::Cos(A) * 1.4 + FwdU * FMath::Sin(A) * 2.2) * 100.0;
		const FVector V = Off.GetSafeNormal() * ((4 + Strength * 0.4) * 100.0) + Nn * 60.0;
		VaporPool.Emit(P0 + Off + Nn * 20.0, V, 1.1f, 80, 260, FLinearColor(0.75f, 0.72f, 0.68f), 0.3f, 2.5f);
	}
}

void ASkysterCar::BurstSparks(const FVector& P, int32 Count, const FLinearColor& C, double Spread)
{
	const double S = Spread * 100.0;
	for (int32 i = 0; i < Count; ++i)
	{
		SparkPool.Emit(P, FVector((FxRand.FRand() - 0.5) * S, (FxRand.FRand() - 0.5) * S, FxRand.FRand() * S * 0.6), FxRand.FRandRange(0.35f, 0.7f), 9, 0, C, 1.f, 1.5f, 1800.f);
	}
}

// Fireball, then a column of black smoke, and a shower of sparks.
void ASkysterCar::ExplodeFX()
{
	const FVector P = ToUE(Pos);
	for (int32 i = 0; i < 260; ++i)
	{
		const double A = FxRand.FRand() * 2 * PI, E = FxRand.FRand() * PI, S = 4 + FxRand.FRand() * 16;
		FirePool.Emit(P + FVector(0, 0, 80), FVector(FMath::Cos(A) * FMath::Sin(E) * S, FMath::Sin(A) * FMath::Sin(E) * S, FMath::Abs(FMath::Cos(E)) * S + 4) * 100.0,
			FxRand.FRandRange(0.5f, 1.4f), FxRand.FRandRange(120.f, 220.f), 700, FLinearColor(3.5f, 1.4f + FxRand.FRand(), 0.3f), 1.f, 2.2f, 200.f);
	}
	for (int32 i = 0; i < 180; ++i)
	{
		const double A = FxRand.FRand() * 2 * PI, S = 2 + FxRand.FRand() * 9;
		VaporPool.Emit(P + FVector(0, 0, 100), FVector(FMath::Cos(A) * S, FMath::Sin(A) * S, 3 + FxRand.FRand() * 8) * 100.0,
			FxRand.FRandRange(2.5f, 5.f), 150, 350, FLinearColor(0.12f, 0.11f, 0.1f), 0.8f, 1.2f, -50.f);
	}
	BurstSparks(P + FVector(0, 0, 100), 160, FLinearColor(4.0f, 2.4f, 0.9f), 26);
}

// Chase camera from js/camera.js: RL's default 9.4 m back / 3.5 m up, smoothed up and back
// vectors, right stick orbits and springs back, FOV widens with speed, a slide shows its angle.
void ASkysterCar::UpdateCamera(float Dt, const FDriverInput& S)
{
	OrbitYaw -= S.LookX * 2.4 * Dt;
	OrbitElev = FMath::Clamp(OrbitElev - S.LookY * 1.6 * Dt, -0.45, 1.1);
	if (FMath::Abs(S.LookX) + FMath::Abs(S.LookY) > 0.01) LookIdle = 0;
	else if ((LookIdle += Dt) > 1.2)
	{
		OrbitYaw = Damp(OrbitYaw, 0, 2.5, Dt);
		OrbitElev = Damp(OrbitElev, 0, 2.5, Dt);
	}
	const double Hs = Vel.Size();
	FVector U, B;
	if (bGrounded && !bTumbling)
	{
		U = Sup.N;
		B = -Fwd;
		// grip handling: swing part way toward the direction of travel, so a slide shows its angle
		if (!Handling.bArcade && Handling.CamSlide > 0 && Hs > 6 && Vf > 0)
		{
			B = FMath::Lerp(B, -Vel / Hs, (double)Handling.CamSlide * Smooth(6, 15, Hs)).GetSafeNormal();
		}
	}
	else
	{
		U = UPV;
		if (Dodge.bActive || bTumbling) B = CamBack; // a flip is too fast to chase: keep the line
		else
		{
			B = -Fwd;
			const double Hz = FMath::Sqrt(B.X * B.X + B.Y * B.Y);
			B.Z = FMath::Clamp(B.Z * 0.55, -0.55, 0.55);
			if (Hz < 0.15)
			{
				const double Bz = FMath::Max(FMath::Sqrt(CamBack.X * CamBack.X + CamBack.Y * CamBack.Y), 1e-3);
				B.X = CamBack.X / Bz * 0.6;
				B.Y = CamBack.Y / Bz * 0.6;
			}
		}
		if (B.SizeSquared() < 1e-4) B = FVector(-1, 0, 0);
		B.Normalize();
	}
	if (!bCamInit)
	{
		CamUp = U;
		CamBack = B;
	}
	const double KUp = bGrounded ? 6 : 3;
	const double KBack = bGrounded ? 5 : (Dodge.bActive || bTumbling) ? 1.5 : 6;
	CamUp = FMath::Lerp(CamUp, U, 1.0 - FMath::Exp(-KUp * Dt)).GetSafeNormal();
	CamBack = FMath::Lerp(CamBack, B, 1.0 - FMath::Exp(-KBack * Dt)).GetSafeNormal();

	const double Dist = TestCamDist > 0 ? (double)TestCamDist : (9.4 + FMath::Min(Hs * 0.03, 3.5)) * CamScale;
	FVector F = CamBack - CamUp * FVector::DotProduct(CamBack, CamUp);
	if (F.SizeSquared() < 1e-4) F = FVector(-1, 0, 0);
	F.Normalize();
	F = FQuat(CamUp, OrbitYaw + FMath::DegreesToRadians((double)(TestCamDist > 0 ? TestCamYaw : 0.f))).RotateVector(F);
	double E = FMath::Clamp(0.3 + OrbitElev + FMath::Asin(FMath::Clamp(FVector::DotProduct(CamBack, CamUp), -0.6, 0.6)), -0.75, 1.2);
	if (TestCamDist > 0) E = FMath::DegreesToRadians((double)TestCamElev);
	const FVector T = Pos + Up * (1.0 + CamLift);
	const FVector Want = F * (FMath::Cos(E) * Dist) + CamUp * (FMath::Sin(E) * Dist + 0.5);
	// smooth the offset from the car rather than the world position, so top speed doesn't stretch the chase
	CamOff = bCamInit ? FMath::Lerp(CamOff, Want, 1.0 - FMath::Exp(-14.0 * Dt)) : Want;
	FVector P = T + CamOff;
	// slide in toward the car if a building is in the way
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SkysterCam), false, this);
	FHitResult Hit;
	if (GetWorld()->SweepSingleByChannel(Hit, ToUE(T), ToUE(P), FQuat::Identity, ECC_Camera, FCollisionShape::MakeSphere(30.f), Params))
	{
		P = FromUE(FVector(Hit.Location));
	}
	// the ground under the camera, traced from no higher than the car's own height: from the camera's height it can start
	// inside overhead steel (the L's girders, expressway decks) and land on a flange, lifting the camera into it
	const double Gy = GroundAt(P.X, P.Y, FMath::Min(P.Z, T.Z));
	if (P.Z < Gy + 0.5) P.Z = Gy + 0.5;
	CamPos = P;
	bCamInit = true;
	const FVector Look = TestCamDist > 0 ? Pos + Up * 0.5 - Fwd * 2.0 : Pos + CamUp * (0.9 + CamLift) - CamBack * 2.5;
	const FVector Dir = (Look - CamPos).GetSafeNormal();
	// speed shake (js camera.js): nothing below ~80 mph, building to a hard rumble past supersonic (217 mph) and
	// under boost; the road shakes hardest, the air eases to a light buffet. A slow buffet that sways the view
	// and a fast buzz on top, plus knocks from landings and hits. Smooth sines, so it rumbles rather than jitters.
	ShakeT += Dt;
	const double FastK = FMath::Pow(FMath::Clamp((Hs - 35.0) / 62.0, 0.0, 1.0), 1.6);
	const double WantK = bAlive ? FastK * (bGrounded ? 1.0 : 0.45) + (bBoosting ? 0.3 + FastK * 0.2 : 0.0) + (Hs > 97 ? 0.25 : 0.0) : 0.0;
	SpeedShake = Damp(SpeedShake, WantK, 3, Dt);
	auto Wob = [](double T, double F, double Ph) { return FMath::Sin(T * F + Ph) * 0.5 + FMath::Sin(T * F * 1.73 + Ph * 2.1) * 0.3 + FMath::Sin(T * F * 2.91 + Ph * 3.7) * 0.2; };
	const double K = SpeedShake, Bk = KnockShake;
	FVector ShakeOff = FVector::ZeroVector;
	FRotator ShakeRot = FRotator::ZeroRotator;
	if (K > 0.002 || Bk > 0.001)
	{
		const double PosLow = K * 0.07 + Bk * 0.05, PosHigh = K * 0.022 + Bk * 0.12;
		const double RotLow = K * 0.006 + Bk * 0.008, RotHigh = K * 0.0025 + Bk * 0.02;
		const double Ox = Wob(ShakeT, 15, 0) * PosLow + Wob(ShakeT, 71, 1) * PosHigh;
		const double Oy = Wob(ShakeT, 19, 2) * PosLow + Wob(ShakeT, 83, 3) * PosHigh;
		const FVector CamRight = FVector::CrossProduct(Dir, CamUp).GetSafeNormal();
		ShakeOff = CamRight * Ox + CamUp * Oy;
		ShakeRot = FRotator(FMath::RadiansToDegrees(Wob(ShakeT, 17, 6) * RotLow * 0.6 + Wob(ShakeT, 79, 7) * RotHigh), 0,
		                    FMath::RadiansToDegrees(Wob(ShakeT, 13, 4) * RotLow + Wob(ShakeT, 67, 5) * RotHigh));
		KnockShake = Damp(KnockShake, 0, 5, Dt);
	}
	const FRotator Base = FRotationMatrix::MakeFromXZ(DirToUE(Dir), DirToUE(CamUp)).Rotator();
	Camera->SetWorldLocationAndRotation(ToUE(CamPos + ShakeOff), (FQuat(Base) * FQuat(ShakeRot)).Rotator());
	// the pad hums along with the speed shake (js: buzz every 0.25 s on the road)
	if ((BuzzT -= Dt) <= 0)
	{
		BuzzT = 0.25;
		if (APlayerController* PC = Cast<APlayerController>(GetController()))
		{
			if (SpeedShake > 0.3 && bGrounded) PC->PlayDynamicForceFeedback((float)FMath::Min(0.35, SpeedShake * 0.22), 0.28f, true, true, true, true);
		}
	}

	// RL's 90 degree horizontal default is about 70 vertical; widen with speed and boost
	const double FovV = 70 + FMath::Clamp(Hs * 0.14, 0.0, 16.0) + (bBoosting ? 4 : 0);
	CamFovV = Damp(CamFovV, FovV, 3, Dt);
	double Aspect = 16.0 / 10.0;
	if (GEngine && GEngine->GameViewport)
	{
		FVector2D Size;
		GEngine->GameViewport->GetViewportSize(Size);
		if (Size.Y > 1) Aspect = Size.X / Size.Y;
	}
	const double FovH = FMath::RadiansToDegrees(2 * FMath::Atan(FMath::Tan(FMath::DegreesToRadians(CamFovV) / 2) * Aspect));
	// capped at 112 horizontal (RL's default is 110): wider than that and the towers lean in at the edges
	Camera->SetFieldOfView((float)FMath::Clamp(FovH, 60.0, 112.0));
}
