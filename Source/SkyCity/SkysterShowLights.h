// McGregorNight's show lighting that reacts to the car (Kenny, 20 Oct 2026):
//  1. "those red bar lights, when the car passes by them, they should get brighter as the car gets near them":
//     every red LED bar (the lane posts' red poles, the show wall's LED face, the LED strips along the run-up and in
//     front of / behind the line-up) glows Base x (1 + Boost x s), s = smoothstep from FarDist down to NearDist from the
//     car, eased in time. Driven through the LED material's "Strength" on one dynamic material instance per bar, plus
//     a small red light per lane post / every few metres of strip that only switches on near the car.
//  2. "a set of sky floodlights to turn on facing the fleet lineup, shining toward the roadster ... when the roadster
//     starts to drive on the white line toward the fleet jump. It should stay on for 12 seconds and then fade off":
//     flood masts beyond the line-up aimed back along the fleet line; they are off in game until the car enters the
//     start of the fleet line moving along it toward the line-up, then fade in (0.4 s), hold (12 s), fade out (1.5 s),
//     and re-arm once the car has left the line's corridor.
//
// Everything is placed and tuned by Scripts/mcgregor/show_lights_ue.py (one actor per map, every number below is an
// EditAnywhere property). How the pieces are found at BeginPlay:
//  - reactive bars: static mesh / instanced components on actors tagged ReactiveTag, or whose mesh name is in
//    ReactiveMeshNames; their LED slots are the ones using an LEDMaterials material or a slot name containing an
//    LEDSlotNames word. Instanced pieces (the Demo_MG_* actors are one HISM each) are copied into one component per
//    instance so each bar glows on its own; the original HISM is hidden in game but keeps its collision.
//  - the LED ribbons drawn on the lot (Demo_Lines is one mesh for all of them) can't be split, so the script hands
//    their polylines over as Strips and this actor lays short glowing bars over them (StripMesh, StripMaterial).
//  - floodlights: lights on actors tagged FloodTag (their placed intensity is the "on" value; they start off),
//    lamp-lens slots (FloodLensSlots) on those actors' meshes, and light-shaft meshes on actors tagged FloodBeamTag.
//    Lights (and shafts) on actors also tagged TrackTag turn to follow the car while lit, up to TrackMaxAngle.
// World space throughout (cm).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkysterShowLights.generated.h"

class ULocalLightComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPrimitiveComponent;
class UStaticMesh;
class UStaticMeshComponent;

/** One LED ribbon on the ground: a polyline at the surface under it (world cm), and its width. */
USTRUCT(BlueprintType)
struct FSkyShowStrip
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show") TArray<FVector> Points;
	/** cm (a little wider than the painted ribbon, which then hides inside the glowing bars). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show") float Width = 14.f;
};

UCLASS()
class SKYCITY_API ASkysterShowLights : public AActor
{
	GENERATED_BODY()

public:
	ASkysterShowLights();
	virtual void Tick(float DeltaSeconds) override;

	// ------------------------------------------------------------------ proximity glow (the red LED bars)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") bool bGlow = true;
	/** Actors with this tag are reactive (all their LED slots). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") FName ReactiveTag = TEXT("SC_ShowBar");
	/** Components whose static mesh name contains one of these are reactive too (survives the unveil rebuilds, which
	 *  respawn the Demo_* actors without the tag). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TArray<FString> ReactiveMeshNames = { TEXT("MG_LanePost"), TEXT("MG_ShowWall"), TEXT("MG_LEDStrip") };
	/** A slot glows if its material is one of these (night_ue.py's MI_Night_LEDRed) ... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TArray<TObjectPtr<UMaterialInterface>> LEDMaterials;
	/** ... or its slot name contains one of these words. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TArray<FString> LEDSlotNames = { TEXT("LEDRed") };
	/** The emissive scalar the glow multiplies (M_SkyEmissive's "Strength"). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") FName GlowParam = TEXT("Strength");
	/** cm: a component bigger than this is not a bar (Demo_Lines holds every ribbon in one mesh: use Strips for those). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float MaxPieceSize = 2500.f;
	/** Brightness = base x (1 + Boost x s): 3 = four times as bright right by the car. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float Boost = 3.f;
	/** cm: full boost within NearDist of the car, none beyond FarDist (smoothstep between). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float NearDist = 1000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float FarDist = 3500.f;
	/** Seconds: time constants of the easing as a bar brightens / dims (the slower fall leaves a short trail). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float RiseTime = 0.12f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float FallTime = 0.6f;
	/** Ignore height when measuring the distance (the bars glow under the car as it flies over). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") bool bPlanDistance = false;

	/** LED ribbons on the lot (demo_layout.json paint "led"), filled in by the script. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TArray<FSkyShowStrip> Strips;
	/** A 100 cm cube centred on its pivot (default /Engine/BasicShapes/Cube), scaled into each strip bar. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TObjectPtr<UStaticMesh> StripMesh;
	/** The strips' LED material (MI_Night_LEDRed); one dynamic instance per strip bar. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TObjectPtr<UMaterialInterface> StripMaterial;
	/** cm: length of each strip bar (the strip is cut into equal bars of about this length). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripSegment = 250.f;
	/** cm: bar thickness, and the gap between the strip points and the bar's underside. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripThickness = 6.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripLift = 0.5f;

	/** Red lights that switch on near the car: one every StripLightSpacing cm along the strips (0 = none) ... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripLightSpacing = 1000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripLightLumens = 420.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripLightRadius = 700.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float StripLightHeight = 40.f;
	/** ... and one on each piece whose mesh name contains one of these (the lane posts' red poles), at PieceLightOffset
	 *  in the piece's own frame (cm). Lumens are at full glow; 0 = none. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") TArray<FString> PieceLightMeshes = { TEXT("MG_LanePost") };
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float PieceLightLumens = 840.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float PieceLightRadius = 900.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") FVector PieceLightOffset = FVector(0.f, -15.f, 230.f);
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") FLinearColor GlowLightColor = FLinearColor(1.f, 0.06f, 0.03f);
	/** Lights already attached to a reactive actor scale by (1 + this x s); below 0 = use Boost. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Glow") float AttachedLightBoost = -1.f;

	// ------------------------------------------------------------------ fleet floodlights
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") bool bFloods = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") FName FloodTag = TEXT("SC_ShowFlood");
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") FName FloodBeamTag = TEXT("SC_ShowFloodBeam");
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") FName TrackTag = TEXT("SC_ShowTrack");
	/** Lamp-lens slots on the flood masts (they glow with the lights). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") TArray<FString> FloodLensSlots = { TEXT("LampLens") };
	/** Lens glow left when the floods are off, as a share of their lit glow. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float LensOffShare = 0.f;
	/** Multiplies the placed light intensities when lit. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float FloodScale = 1.f;
	/** Seconds: fade in, stay on, fade off. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float FadeInTime = 0.4f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float HoldTime = 12.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float FadeOutTime = 1.5f;
	/** Tracking lights turn toward the car while lit, at most TrackMaxAngle deg from where they were placed;
	 *  TrackRate = 1/s easing; aimed TrackAimHeight cm above the car's origin. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") bool bTrackCar = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float TrackMaxAngle = 30.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float TrackRate = 3.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Floods") float TrackAimHeight = 80.f;

	/** The fleet line (the white line toward the fleet jump), world cm: its start, then toward the line-up. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") FVector LineStart = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") FVector LineEnd = FVector(100.f, 0.f, 0.f);
	/** cm along the line from LineStart: the trigger zone at the start of the line. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float TriggerFrom = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float TriggerTo = 3500.f;
	/** cm either side of the line, and the most the car may be above it (not while flying over). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float TriggerHalfWidth = 900.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float TriggerMaxHeight = 800.f;
	/** cm/s along the line toward the line-up (500 = 5 m/s), and the least share of the car's speed that is along it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float MinSpeed = 500.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float MinAlign = 0.6f;
	/** The corridor the car must leave before the floods can trigger again: the whole line, RearmBefore cm before its
	 *  start to RearmPast cm past its end, RearmHalfWidth cm either side. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float RearmHalfWidth = 1400.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float RearmBefore = 1500.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show|Trigger") float RearmPast = 3000.f;
	/** Draw the trigger zone and corridor, show the state on screen, log every bar found. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Show") bool bDebug = false;

	// ------------------------------------------------------------------ control and test hooks
	/** Lights up the floods now (fade in, hold, fade out), as the trigger does. */
	UFUNCTION(BlueprintCallable, Category = "Show") void TriggerFloods();
	/** Starts the fade out now. */
	UFUNCTION(BlueprintCallable, Category = "Show") void StopFloods();
	/** 0 (off) .. 1 (fully lit), after the fade curve. */
	UFUNCTION(BlueprintPure, Category = "Show") float GetFloodLevel() const { return FloodOut; }
	/** "off", "fade_in", "hold" or "fade_out". */
	UFUNCTION(BlueprintPure, Category = "Show") FString GetFloodState() const;
	UFUNCTION(BlueprintPure, Category = "Show") bool IsArmed() const { return bArmed; }
	UFUNCTION(BlueprintPure, Category = "Show") int32 GetTriggerCount() const { return TriggerCount; }
	/** The car in the fleet line's frame: X cm along from LineStart, Y cm to the side, Z cm above the line; and its
	 *  speed along the line (cm/s). */
	UFUNCTION(BlueprintPure, Category = "Show") FVector GetCarLineFrame() const { return CarFrame; }
	UFUNCTION(BlueprintPure, Category = "Show") float GetCarLineSpeed() const { return CarAlongSpeed; }
	UFUNCTION(BlueprintPure, Category = "Show") int32 GetNumBars() const { return Bars.Num(); }
	/** Bar I: what it is ("strip 0/12", "MG_LanePost #3"), where, its eased glow 0..1 and its current Strength. */
	UFUNCTION(BlueprintPure, Category = "Show") FString GetBarName(int32 I) const;
	UFUNCTION(BlueprintPure, Category = "Show") FVector GetBarLocation(int32 I) const;
	UFUNCTION(BlueprintPure, Category = "Show") float GetBarGlow(int32 I) const;
	UFUNCTION(BlueprintPure, Category = "Show") float GetBarBrightness(int32 I) const;
	UFUNCTION(BlueprintPure, Category = "Show") int32 GetNumFloodLights() const { return Floods.Num(); }
	UFUNCTION(BlueprintPure, Category = "Show") float GetFloodLightIntensity(int32 I) const;
	/** One line: bars / strip bars / glow lights / flood lights / shafts found at BeginPlay. */
	UFUNCTION(BlueprintPure, Category = "Show") FString GetSummary() const { return Summary; }

protected:
	virtual void BeginPlay() override;

private:
	struct FGlowMat
	{
		UMaterialInstanceDynamic* Mid = nullptr;   // kept alive by Made
		float Base = 1.f;
	};
	struct FGlowLight
	{
		TWeakObjectPtr<ULocalLightComponent> Light;
		float Base = 0.f;          // attached lights: their placed intensity; auto lights: lumens at full glow
		bool bAuto = false;
	};
	struct FBar
	{
		FString Name;
		TWeakObjectPtr<UPrimitiveComponent> Comp;
		TArray<FGlowMat> Mats;
		TArray<FGlowLight> Lights;
		bool bSegment = false;     // strip bar: distance to the segment A-B, else to the box
		FVector A = FVector::ZeroVector, B = FVector::ZeroVector;
		FBox Box = FBox(ForceInit);
		float Glow = 0.f, Shown = -1.f;
	};
	struct FFloodLight
	{
		TWeakObjectPtr<ULocalLightComponent> Light;
		float On = 0.f;
		FQuat Base = FQuat::Identity, Cur = FQuat::Identity;
		bool bTrack = false;
	};
	struct FFloodMesh
	{
		TWeakObjectPtr<UPrimitiveComponent> Comp;
		TArray<FGlowMat> Mats;
		bool bBeam = false;        // a light shaft: hidden while off
		int32 Follow = INDEX_NONE; // shafts on tracking actors turn with the nearest tracking light
		FQuat Offset = FQuat::Identity;
	};
	enum class EFlood : uint8 { Off, FadeIn, Hold, FadeOut };

	/** Everything made at BeginPlay, held here so the garbage collector keeps it. */
	UPROPERTY(Transient) TArray<TObjectPtr<UObject>> Made;

	TArray<FBar> Bars;
	TArray<FFloodLight> Floods;
	TArray<FFloodMesh> FloodMeshes;
	EFlood FloodState = EFlood::Off;
	float FloodLevel = 0.f;        // linear 0..1
	float FloodOut = 0.f;          // after the fade curve (what the lights show)
	float FloodShown = -1.f;
	float HoldT = 0.f;
	bool bArmed = true;
	int32 TriggerCount = 0;
	FVector CarFrame = FVector::ZeroVector;
	float CarAlongSpeed = 0.f;
	FVector PrevCar = FVector::ZeroVector;
	bool bHavePrev = false;
	FString Summary;
	int32 NumStripBars = 0, NumPieces = 0, NumGlowLights = 0;

	void GatherBars();
	void BuildStrips();
	void GatherFloods();
	bool IsLEDSlot(const UPrimitiveComponent* C, int32 Slot) const;
	int32 AddBar(UPrimitiveComponent* C, const FString& Name, const FBox& Box, bool bAllSlots);
	UStaticMeshComponent* NewMeshPart(UStaticMesh* Mesh, const FTransform& X, bool bShadow);
	ULocalLightComponent* MakeGlowLight(const FVector& At, float Radius);
	void ApplyBar(FBar& Bar);
	void UpdateGlow(float Dt, const FVector& Car, bool bHaveCar);
	void UpdateTrigger(const FVector& Car, const FVector& Vel);
	void UpdateFloods(float Dt);
	void ApplyFloods(const FVector& Car, bool bHaveCar, float Dt);
	void DebugDraw(const FVector& Car) const;
	static bool NameHasAny(const FString& Name, const TArray<FString>& Words);
};
