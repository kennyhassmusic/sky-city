// The Skyster: Kenny's Roadster with the car physics from the browser game (Skyster build 4.0,
// js/vehicle.js, signed off 19 Oct 2026), ported to Unreal: grip tyre handling, flight that climbs
// where the nose points, hover, wall riding and parking, the air brake, flips and the demo moves,
// a hull that takes damage, pressure points, fast chargers, fuel add-ons, and car levels earned
// through challenges (js/progress.js).
//
// The simulation runs in its own right-handed frame in metres, like the JS version but z-up:
// x = forward, y = left, z = up. (js world (x, y, z) = sim (y, z, x); js car frame x left, y up,
// z forward.) Unreal is left-handed (x forward, y right, z up) in centimetres, so positions and
// directions cross over with y flipped and a factor of 100 (ToUE / FromUE).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "InputCoreTypes.h"
#include "SkysterTypes.h"
#include "SkysterProgress.h"
#include "SkysterPickups.h"
#include "SkysterFX.h"
#include "SkysterCar.generated.h"

class UCameraComponent;
class USphereComponent;
class UStaticMeshComponent;
class USceneComponent;

UCLASS()
class SKYCITY_API ASkysterCar : public APawn
{
	GENERATED_BODY()

	friend class ASkysterHUD;
	friend struct FSkyProgress;

public:
	ASkysterCar();

	virtual void Tick(float DeltaSeconds) override;

	/** Back on the nearest road (View button / R), full hull, a third of a tank. */
	UFUNCTION(BlueprintCallable, Category = "Skyster")
	void Respawn();

	/** Back to the map's start (PlayerStart): for tests. */
	UFUNCTION(BlueprintCallable, Category = "Skyster|Test")
	void ResetToStart();

	/** Test hook: put the car at a world position (Unreal cm) facing YawDeg, standing on whatever is found from 2 m above
	 *  that point downward (so give a Z just above the road, e.g. 100 for street level). */
	UFUNCTION(BlueprintCallable, Category = "Skyster|Test")
	void TestTeleport(FVector WorldUE, float YawDeg) { SpawnAt(WorldUE, YawDeg); }

	UFUNCTION(BlueprintPure, Category = "Skyster")
	float GetSpeedMph() const { return Speed * 2.23694f; }

	UFUNCTION(BlueprintPure, Category = "Skyster")
	float GetBoostTank() const { return BoostTank; }

	UFUNCTION(BlueprintPure, Category = "Skyster")
	float GetHealth() const { return Health; }

	/** DRIVE, AIR, FLIP, WALL, SLIDE, FLIGHT, HOVER, LANDING, AIR BRAKE, CHARGING or TUMBLE (for the HUD and tests). */
	UFUNCTION(BlueprintPure, Category = "Skyster")
	FString GetMode() const;
	/** The car you drive: 0 = Kenny's Roadster, then the McGregor line-up (Garage D-pad up/down, or V). */
	FString GetVehicleName() const;
	int32 GetVehicle() const { return Vehicle; }
	/** Sky City's traffic (cars on the streets, flying Cybercabs), if this map has it. */
	const class ASkysterTraffic* GetTraffic() const { return Traffic.Get(); }

	UFUNCTION(BlueprintPure, Category = "Skyster")
	bool IsBoosting() const { return bBoosting; }

	/** Ground handling, live-editable (Skyster's tuning panel). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster")
	FSkyHandling Handling;

	/** Percent of tank per second refilled on a surface. Skyster: 0 (the tank fills from pressure points only). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster")
	float GroundRefill = 0.f;

	/** Let go of air roll and the car banks back to wheels-down (pitch is left alone). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster")
	bool bRollAssist = true;

	/** Maps the Garage (Menu button) can switch between. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster")
	TArray<FName> Maps = { FName(TEXT("/Game/Maps/SkyCityMashup")), FName(TEXT("/Game/Maps/McGregor")), FName(TEXT("/Game/Maps/McGregorNight")), FName(TEXT("/Game/Maps/McGregor?mode=build")) };

	// Scripted input for automated driving tests: while bTestInput is on these replace the pad.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestInput = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestThrottle = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestBrake = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestStop = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestSteer = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestPitch = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestRoll = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestJump = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestBoost = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestFly = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestSlide = false;
	/** Test hook: keep the tank full. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestFullTank = false;
	/** Test hook: put the car at a level (1-6) on the next tick. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") int32 TestSetLevel = 0;
	/** Test hooks for the thrust looks: force the plumes on (0-1, no thrust), a fuel look ("nitrogen", "combustion",
	 *  "rocket"), and a fixed chase camera (distance m, yaw and elevation deg round the car). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestJets = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") FString TestLook;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestCamDist = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestCamYaw = 0.f;
	/** Test hook: set to a vehicle index (0 Roadster, 1-5 the line-up) and the car switches to it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") int32 TestVehicle = -1;
	/** Test hook: set true and the car toggles self-driving (as D-pad right would). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bTestFsd = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") float TestCamElev = 10.f;
	/** A Course Builder AI opponent (ASkyCourseRace), set before BeginPlay (SpawnActorDeferred, then FinishSpawning): driven
	 *  through the test-input hooks, with the level 6 car minus flight, and none of the player's things: no saved progress,
	 *  challenges, toasts, pickups, camera, traffic or course mode. TestVehicle picks its body at BeginPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skyster|Test") bool bAIDriver = false;

	// Course Builder race hooks (Design/RaceHandling.md). ASkyCourseRace sets these on its cars every tick, before the
	// car ticks, and clears them when the race ends; outside a race they stay at rest and nothing below changes.
	// The assists only act while the car is on Course Builder track (SkyTrack) or in the air above it.
	bool bInCourseRace = false;
	uint8 RaceAssist = 0;                   // the player's ESkyAssist (0 Off, 1 Light, 2 Full); opponents stay 0
	float RaceSteerNudge = 0.f;             // smart steering: added to the stick's steer on the ground (-1..1)
	bool bRaceAirAim = false;               // landing help: in the air, turn toward this attitude (sim frame)...
	FVector RaceAimFwd = FVector(1, 0, 0), RaceAimUp = FVector(0, 0, 1);
	FVector RaceAirPull = FVector::ZeroVector;   // ...and drift toward the pad (m/s^2, sim frame, a few at most)
	float RaceSpeedScale = 1.f;             // slipstream and the AI rubber band: scales the drive and boost top speed
	bool bRaceResetHit = false;             // the car's reset (View / R) during a race: the race reads and clears it

	/** Called by the progress system when the level changes. */
	void ApplyCaps(const FSkyCaps& C);
	void Toast(const FString& Title, const FString& Sub = FString());

protected:
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;

	UPROPERTY(VisibleAnywhere, Category = "Skyster")
	TObjectPtr<USphereComponent> Sensor;

	/** Chassis pivot: body roll and dive tilt this, not the actor. */
	UPROPERTY(VisibleAnywhere, Category = "Skyster")
	TObjectPtr<USceneComponent> Chassis;

	UPROPERTY(VisibleAnywhere, Category = "Skyster")
	TObjectPtr<UStaticMeshComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "Skyster")
	TObjectPtr<UCameraComponent> Camera;

	// Kenny's rigged Roadster (roadster_rig.glb split by Scripts/unreal/blender_roadster_rig.py): body parts ride the
	// tilting chassis, the wheels the car's root so they stay on the road
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigBody;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigWing;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigPush;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigSpoiler;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigPanelL;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigPanelR;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigBaffleL;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TObjectPtr<UStaticMeshComponent> RigBaffleR;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> RigWheels;
	// cold-gas thrusters: four rear plumes (boost), six floor jets (jumps, flips, hover, flight), fuel flames
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> RearJets;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> RearCores;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> Flames;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> DownJets;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> DownCores;
	/** Side thrusters in the fender camera slots (left, right): show the yaw the car already has in the air. */
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> SideJets;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<UStaticMeshComponent>> SideCores;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatRear;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatDown;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatCore;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatFlame;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatHead;
	/** Headlight beams: on with the headlights (D-pad left / H), and from the start on night maps. */
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Rig") TArray<TObjectPtr<class USpotLightComponent>> HeadBeams;
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MatTail;
	/** The other vehicles you can drive (Kenny's McGregor line-up, /Game/Vehicles/Tesla): a body on the chassis and up
	 *  to six wheels on the root, swapped in for the Roadster's rig; the Skyster physics stay the same. */
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Fleet") TObjectPtr<UStaticMeshComponent> AltBody;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|Fleet") TArray<TObjectPtr<UStaticMeshComponent>> AltWheels;
	/** Particles (js fx.js): vapour and smoke (lit), fire and sparks (additive), each a pool of camera-facing quads. */
	UPROPERTY(VisibleAnywhere, Category = "Skyster|FX") TObjectPtr<class UInstancedStaticMeshComponent> VaporFx;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|FX") TObjectPtr<class UInstancedStaticMeshComponent> FireFx;
	UPROPERTY(VisibleAnywhere, Category = "Skyster|FX") TObjectPtr<class UInstancedStaticMeshComponent> SparkFx;
	/** The car's runtime materials, loaded at BeginPlay (DefaultGame.ini's DirectoriesToAlwaysCook packages them). */
	UPROPERTY(EditDefaultsOnly, Category = "Skyster|FX") TObjectPtr<class UMaterialInterface> JetMaterial;
	UPROPERTY(EditDefaultsOnly, Category = "Skyster|FX") TObjectPtr<class UMaterialInterface> CarLightMaterial;
	UPROPERTY(EditDefaultsOnly, Category = "Skyster|FX") TObjectPtr<class UMaterialInterface> VaporMaterial;
	UPROPERTY(EditDefaultsOnly, Category = "Skyster|FX") TObjectPtr<class UMaterialInterface> FireMaterial;
	UPROPERTY(EditDefaultsOnly, Category = "Skyster|FX") TObjectPtr<class UMaterialInterface> SparkMaterial;

private:
	// --- driver input, one frame ---
	struct FDriverInput
	{
		float Throttle = 0, Brake = 0, Steer = 0, Pitch = 0, Yaw = 0, Roll = 0;
		float Stop = 0;   // the X brake on the road (Brake is LT: reverse, and the air brake in the air)
		bool bAirRoll = false, bJump = false, bJumpHit = false, bBoost = false, bFlyHold = false, bLandHold = false;
		bool bLaunchHit = false, bResetHit = false, bKickHit = false, bParkHit = false, bModeHit = false, bLightsHit = false;
		bool bNavU = false, bNavD = false, bVehicleHit = false, bTrafficHit = false, bCabsHit = false, bNavLB = false, bNavRB = false;
		bool bFsdHit = false, bNavA = false;
		bool bMenuHit = false, bNavL = false, bNavR = false, bNavY = false, bNavX = false, bNavB = false, bLevelDown = false, bLevelUp = false;
		float LookX = 0, LookY = 0;
	};

public:
	enum class ESurface : uint8 { Ground, Wall };

	struct FSupport
	{
		bool bOn = false;
		FVector N = FVector(0, 0, 1);
		FVector P = FVector::ZeroVector;
		ESurface Kind = ESurface::Ground;
		double Dist = 0;
		TWeakObjectPtr<UPrimitiveComponent> Comp;
	};

	struct FJump
	{
		double T = 99, AirT = 0, HoldT = 0, HoverHold = 0;
		bool bCanDouble = false, bHolding = false, bFree = false, bFromWall = false, bHoverArmed = false;
		FVector Takeoff = FVector::ZeroVector;
	};

private:
	struct FDodge
	{
		bool bActive = false, bCancelled = false;
		double T = 0, PitchSign = 0;
		FVector Spin = FVector::ZeroVector;   // car frame: x roll, y pitch (+ = nose down), z yaw (+ = left)
		FVector Extra = FVector::ZeroVector;
	};

	struct FMacro
	{
		bool bOn = false;
		FString Name;
		double T = 0, Side = 1;
		int32 Phase = 0;
		FVector Dir = FVector(1, 0, 0);
		FDriverInput S;
	};

	struct FStunts
	{
		double Roll = 0, Pitch = 0, Yaw = 0;
		bool bSuperDone = false;
		bool bSixtyOn = false, bSixtyRest = false;
		double SixtyT = 0;
	};

	struct FCombo
	{
		TArray<FString> Moves;
		double Score = 0, Total = 0, BestScore = 0, GroundT = 0;
		int32 Mult = 1, Best = 0;
		bool bActive = false;
		double R = 0, P = 0, Y = 0, MaxH = 0, HoverT = 0, WallT = 0, InvT = 0;
		bool bHoverDone = false, bWallDone = false, bInvDone = false, bLineupDone = false;
		double LastDodge = -9, DodgeF = 0;
	};

	FDriverInput ReadInput(float Dt);
	void Simulate(float Dt, FDriverInput& S);
	void Step(double H, FDriverInput& S);
	void OnJump(FDriverInput& S);
	void StartDodge(double F, double R, double Impulse = 1.0);
	void LeaveSurface();
	void RightSelf();
	void DriveOnSurface(double H, FDriverInput& S);
	double Tyres(double H, const FDriverInput& S, double& VF, double& VR, double Nf, double Nr, double ALong);
	void Fly(double H, FDriverInput& S);
	void Collide(double H, const FVector& PrevPos);
	void TransitionTo(const FVector& N, UPrimitiveComponent* Comp, ESurface Kind, const FVector& HitPoint);
	void ResolveSupport(double H);
	void LandOn(double Vn, double Align);
	void CrashLand(double Vn, double Align);
	void Tumble(double K);
	void Hurt(double Vn, double Mult);
	double RestLift() const;
	void Aim(FDriverInput& S, const FVector& FwdT, const FVector& UpT, double Side);
	void UpdateAxes();
	void ApplyToActor(float Dt);
	void UpdateJets(double Dt, const FDriverInput& S);
	void AnimateRig(double Dt);
	void BurstAll(double K) { for (double& B : JetBurst) B = FMath::Max(B, K); }
	void UpdateCamera(float Dt, const FDriverInput& S);
	void Locked(const TCHAR* What, bool bOn);
	void Event(ESkyEv Type, const FString& Name = FString(), double A = 0, double B = 0, int32 I = 0);
	void AddMove(const FString& Name);
	void BankCombo(const TCHAR* Result);
	void TrackStunts(double Dt, const FDriverInput& S);
	void Pickups(double Dt);
	bool StartMacro(const FString& Name, double Side);
	void Hop(double V);
	void RunMacro(double Dt, const FDriverInput& Live);
	void SpawnAt(const FVector& PosUE, double YawDeg);
	void HandleEvents();
	// particles (js main.js emitContinuous, dustRing, burstSparks, explode)
	void UpdateFX(double Dt);
	void DustRing(double Strength);
	void BurstSparks(const FVector& P, int32 Count, const FLinearColor& C, double Spread);
	void ExplodeFX();
	int32 FxCount(double Rate, double Dt);
	void Garage(const FDriverInput& S);

	// world queries (sim frame, metres)
	double GroundAt(double X, double Y, double Z) const;
	bool FindSupport(FSupport& Out, bool bGroundedNow) const;

	static FVector ToUE(const FVector& M) { return FVector(M.X * 100.0, -M.Y * 100.0, M.Z * 100.0); }
	static FVector FromUE(const FVector& C) { return FVector(C.X / 100.0, -C.Y / 100.0, C.Z / 100.0); }
	static FVector DirToUE(const FVector& D) { return FVector(D.X, -D.Y, D.Z); }
	static FVector DirFromUE(const FVector& D) { return FVector(D.X, -D.Y, D.Z); }
	static FQuat RotTo(const FVector& A, const FVector& B, double K);

public:
	// --- state (sim frame) ---
	FVector Pos = FVector::ZeroVector;
	FVector Vel = FVector::ZeroVector;
	FQuat Q = FQuat::Identity;
	FVector W = FVector::ZeroVector;  // angular velocity, world frame
	FVector Fwd = FVector(1, 0, 0), Up = FVector(0, 0, 1), Left = FVector(0, 1, 0);
	FSupport Sup;
	FJump Jump;
	bool bGrounded = true;
	double GroundY = 0;
	double BoostTank = 33;
	double Health = 100;
	bool bAlive = true, bCharging = false;
	bool bBoosting = false, bHovering = false, bLanding = false, bLandArmed = false, bAirBraking = false, bFlying = false, bTumbling = false;
	bool bDrifting = false, bBraking = false, bReversing = false;
	double SimTime = 0, Speed = 0, Vf = 0, Vr = 0;
	TArray<FSkyEvent> Events;

private:
	FDodge Dodge;
	FMacro Macro;
	FStunts St;
	FCombo Cb;
	FSkyCaps Caps;
	FSkyProgress Progress;
	FSkyPickups World;
	double Cushion = 0, FlyHeading = 0, FlyTurn = 0, FlyClimb = 0, FlyLift = 0;
	/** The support normal last step while on Course Builder track (zero off it): how fast it turns gives a curve's grip. */
	FVector LastSupN = FVector::ZeroVector;
	bool bRaceStable = false;              // Full race assist on track this step: stronger stability control (Tyres)
	double TrackPress = 0, TrackRun = 0;   // the curve's grip (m/s^2), held between triangle edges; metres since the normal last turned
	double SteerAngle = 0, StuckT = 0, TumbleT = 0, DeadT = 0, LastHurt = -9;
	double YawRate = 0, SlipF = 0, SlipR = 0, AccelLat = 0, AccelLong = 0, Fans = 0;
	double FuelMult = 1;
	TMap<FString, bool> LockEdge;
	TArray<FSkyToast> Toasts;
	double HurtFlash = 0, LastSixty = -1, BestSixty = -1, FlightTip = -99, ComboShowT = 0;
	bool bGarage = false, bLights = false;
	bool bBrakeHold = false, bThrottleHold = false;
	int32 GarageSel = 0;
	double BodyPitch = 0, BodyRoll = 0;
	// rig and thruster animation state (js car.js)
	double JetRear = 0, JetDown[6] = { 0, 0, 0, 0, 0, 0 }, JetBurst[6] = { 0, 0, 0, 0, 0, 0 };
	double JetSide[2] = { 0, 0 };   // left, right
	double WheelSpin[4] = { 0, 0, 0, 0 }, WheelRate[4] = { 0, 0, 0, 0 };
	double WingAng = 0, PushK = 0, SpoilerAng = 0, PanelK[2] = { 0, 0 }, BaffleK = 0, RigT = 0, SpawnT = 0;
	bool bRig = false;
	// the driven vehicle (see SkyFleet in SkysterCar.cpp)
	int32 Vehicle = 0, AltNum = 0, AltAxle[6] = { 0, 0, 0, 0, 0, 0 };
	double AltSpin[6] = { 0, 0, 0, 0, 0, 0 }, AltR[6] = { 1, 1, 1, 1, 1, 1 };
	bool AltSteer[6] = { false, false, false, false, false, false };
	double CamScale = 1, CamLift = 0;
	void SetVehicle(int32 Index, bool bToast);
	TWeakObjectPtr<class ASkysterTraffic> Traffic;
	void ToggleTraffic(bool bSkyLayer);
	// self-driving (D-pad right / Z): the traffic system plans and paces it, the car steers and drives it
	bool bFsd = false, bFsdHold = false;
	FString FsdHint;
	double FsdDistLeft = 0;
	void ToggleFsd();
	void FsdControl(double Dt, FDriverInput& S);
	void ShowBody(bool bOn);
	FSkyPool VaporPool, FirePool, SparkPool;
	FRandomStream FxRand{ 77 };

	// spawn
	FVector SpawnPosUE = FVector::ZeroVector;
	double SpawnYawDeg = 0;

	// camera (sim frame)
	FVector CamUp = FVector(0, 0, 1), CamBack = FVector(-1, 0, 0), CamPos = FVector::ZeroVector, CamOff = FVector::ZeroVector;
	double OrbitYaw = 0, OrbitElev = 0, LookIdle = 0, CamFovV = 70;
	double ShakeT = 0, SpeedShake = 0, KnockShake = 0, BuzzT = 0;
	bool bCamInit = false;

	// input edge tracking
	TMap<FKey, bool> PrevKeys;
	bool bPrevJumpT = false;
};
