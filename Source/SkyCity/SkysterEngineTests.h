// Timed engine / booster tests at the McGregor test stands (mcgregor-tests agent, 20 Oct 2026).
// Every Interval seconds (6.9 minutes) one of the stands fires: an ignition flash, a roaring plume from the engine (or
// the booster's nine) down into its flame trench, flame and billowing smoke out of the trench's exhaust bay that drifts
// downwind, then shutdown and a lingering cloud. The first test comes FirstDelay seconds after the map loads, at the
// stand nearest the player (from the unveil lot: Raptor North, ~600 m west).
// Everything is data: Sites and the timings are filled by Scripts/mcgregor/engine_tests_ue.py from
// Saved/McGregor/site_features.json (tests.engine_tests, written by site_layout.py / tests_layout.py).
// Looks reuse the car's FX: the SC_JetCone plume with MI_Jet, the smoke flipbook (M_SkyVapor) and M_SkyFire on camera-
// facing quads (same five custom-data floats as SkysterFX's pools). Cheap: one test at a time, two instanced quad pools
// updated only while a test or its cloud is alive, one light only on the night map.
#pragma once

#include "CoreMinimal.h"
#include "Camera/CameraShakeBase.h"
#include "GameFramework/Actor.h"
#include "SkysterEngineTests.generated.h"

class UInstancedStaticMeshComponent;
class UStaticMeshComponent;
class UPointLightComponent;
class UAudioComponent;
class UMaterialInstanceDynamic;

/** One stand. World positions in cm (Unreal frame); directions need not be normalised. */
USTRUCT(BlueprintType)
struct FSkysterTestSite
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FName Id;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FString Name;
	/** 0 = single engine, 1 = booster (an engine cluster: bigger, louder, darker smoke), 2 = upper stage */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") int32 Kind = 0;
	/** The nozzle exit (a cluster's centre) and where it points. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FVector Nozzle = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FVector NozzleDir = FVector(0, 0, -1);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") int32 Nozzles = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float NozzleSpread = 0.f;
	/** The visible plume: length (cm, about to the trench floor) and radius at the exit (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float PlumeLength = 1000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float PlumeRadius = 100.f;
	/** The exhaust bay: where flame and smoke leave the trench, the way they go, and how wide the opening is (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FVector Exit = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") FVector ExitDir = FVector(-1, 0, 0.2);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float ExitWidth = 2400.f;
	/** Seconds at full thrust (10-20). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float Duration = 14.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float SmokeScale = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Test") float FireScale = 1.f;
};

UCLASS()
class SKYCITY_API ASkysterEngineTests : public AActor
{
	GENERATED_BODY()

public:
	ASkysterEngineTests();
	virtual void Tick(float DeltaSeconds) override;

	/** Fires a stand now (test hook; -1 = the next one in the rotation). Ignored while a test is running. */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "EngineTests") void RunTestNow(int32 SiteIndex = -1);
	/** One line for test scripts: phase, site, seconds into the test, next test in, live particles, shake, sound. */
	UFUNCTION(BlueprintCallable, Category = "EngineTests") FString GetTestState() const;

	/** The stands, in rotation order. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") TArray<FSkysterTestSite> Sites;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") bool bEnabled = true;
	/** Seconds between test starts (6.9 minutes). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float Interval = 414.f;
	/** The first test, this long after the map loads. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float FirstDelay = 40.f;
	/** The first test at the stand nearest the player (then the rotation carries on from there). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") bool bFirstNearest = true;
	/** Random stand each time (never the same twice running) instead of the rotation. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") bool bRandomOrder = false;
	/** Seconds of tank chill-down venting before ignition. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float VentTime = 3.f;
	/** Wind the smoke drifts with (cm/s, Unreal frame). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") FVector WindVelocity = FVector(490.f, 90.f, 0.f);
	/** Camera rumble when the player is within this distance (cm), and how strong at the stand itself. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float ShakeRadius = 90000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float ShakeStrength = 1.f;
	/** Flickering light over the exhaust bay during a test (worth it on the night map only). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") bool bNightLights = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float LightCandelas = 250000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float LightRadius = 40000.f;
	/** The roar (a loop), heard to SoundRadius (cm), arriving at the speed of sound. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") TObjectPtr<class USoundBase> RoarSound;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float SoundRadius = 300000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") float SoundVolume = 1.f;
	/** Assets (the placement script sets them so they cook with the map; BeginPlay loads the defaults if empty). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests|Assets") TObjectPtr<class UStaticMesh> PlumeMesh;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests|Assets") TObjectPtr<class UStaticMesh> QuadMesh;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests|Assets") TObjectPtr<class UMaterialInterface> JetMaterial;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests|Assets") TObjectPtr<class UMaterialInterface> SmokeMaterial;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests|Assets") TObjectPtr<class UMaterialInterface> FireMaterial;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") int32 MaxSmoke = 900;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "EngineTests") int32 MaxFire = 420;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UStaticMeshComponent> PlumeOuter;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UStaticMeshComponent> PlumeCore;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UInstancedStaticMeshComponent> SmokeFx;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UInstancedStaticMeshComponent> FireFx;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UPointLightComponent> ExitLight;
	UPROPERTY(VisibleAnywhere, Category = "EngineTests") TObjectPtr<UAudioComponent> Roar;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MatOuter;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MatCore;

private:
	enum class EPhase : uint8 { Idle, Vent, Burn, Shutdown, Linger };
	struct FPuff
	{
		FVector P, V;
		FLinearColor C;
		float Life, MaxLife, Size, Grow, MaxSize, A, Drag, RiseVel, Floor, Roll, Spin, Phase;
		bool bLanded;
	};
	struct FPool
	{
		UInstancedStaticMeshComponent* Ism = nullptr;
		TArray<FPuff> Parts;
		TArray<FTransform> Xfs;
		TArray<float> Data;
		TArray<int32> Order;
		int32 Max = 0, LastN = 0;
		bool bSort = false, bWind = false;
		void Init(UInstancedStaticMeshComponent* InIsm, int32 InMax, bool bInSort, bool bInWind);
		FPuff& Add(FRandomStream& R);
		void Update(float Dt, const FVector& Cam, const FVector& Wind);
	};
	FPool Smoke, Fire;
	FRandomStream Rand{ 4141 };

	EPhase Phase = EPhase::Idle;
	int32 Current = -1, Last = -1;
	bool bFirstDone = false;
	double NextTest = 0, PhaseT = 0, TestT = 0, SoundDelay = 0, LightT = 0;
	bool bSoundOn = false, bSoundStopped = false;
	float Thrust = 0.f;                          // 0..1 envelope of the plume
	TWeakObjectPtr<class UCameraShakeBase> Shake;
	float ShakeNow = 0.f;

	int32 PickSite() const;
	void StartTest(int32 Index);
	void EndVisuals();
	void Emit(const FSkysterTestSite& S, float Dt);
	int32 Count(float Rate, float Dt);
	FVector CameraLocation() const;
	FVector PlayerLocation() const;
	void UpdateShake(const FSkysterTestSite& S, float Amp);
};

/** The rumble: perlin-noise wobble whose strength ASkysterEngineTests sets every frame (Amplitude, 0 = still). */
UCLASS()
class SKYCITY_API USkysterTestShakePattern : public UCameraShakePattern
{
	GENERATED_BODY()
public:
	USkysterTestShakePattern(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer) {}
	static float Amplitude;

private:
	virtual void GetShakePatternInfoImpl(FCameraShakeInfo& OutInfo) const override;
	virtual void StartShakePatternImpl(const FCameraShakePatternStartParams& Params) override;
	virtual void UpdateShakePatternImpl(const FCameraShakePatternUpdateParams& Params, FCameraShakePatternUpdateResult& OutResult) override;
	virtual bool IsFinishedImpl() const override { return false; }
	float T = 0.f;
};

UCLASS()
class SKYCITY_API USkysterTestShake : public UCameraShakeBase
{
	GENERATED_BODY()
public:
	USkysterTestShake(const FObjectInitializer& ObjectInitializer);
};
