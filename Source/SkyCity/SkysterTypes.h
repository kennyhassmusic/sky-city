// Shared types for the Skyster car: what the car can do at its level (caps), the ground-handling
// tuning Kenny signed off in Skyster 4.0 (js/vehicle.js H), events the car raises each frame, and
// toasts for the HUD. Same names as the browser game wherever possible.
#pragma once

#include "CoreMinimal.h"
#include "SkysterTypes.generated.h"

/** Ground handling and feel (js/vehicle.js `H`). Kenny tuned these live in Skyster; edit them on the car in PIE. */
USTRUCT(BlueprintType)
struct FSkyHandling
{
	GENERATED_BODY()

	/** Rocket League's handling (the car turns exactly as the wheels point) instead of the tyre model. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") bool bArcade = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Mu = 1.15f;          // tyre friction
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float RearGrip = 1.08f;   // rear grip relative to the front (a touch more: the car understeers before it oversteers)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Peak = 0.14f;        // slip angle of peak grip, rad
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Slide = 0.82f;       // grip left fully sideways (a gentler fall-off past the peak)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float CgF = 0.47f;         // weight on the front axle
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float CgH = 0.45f;         // centre of mass height, m
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float K2 = 2.2f;          // yaw inertia, m^2
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float FanGrip = 1.0f;      // share of fan suction on the tyres
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Aero = 0.8f;         // wing downforce at top speed, G
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float LongGrip = 1.1f;     // throttle/brake cap (wheelspin, ABS)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float DriveSplit = 0.4f;   // front share of the drive
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float BrakeSplit = 0.6f;   // front share of the braking
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Coast = 6.f;         // m/s^2 lifting off
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Handbrake = 0.5f;    // rear grip while powersliding
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float DriftYaw = 1.5f;     // rad/s^2 from the stick while sliding
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float DriftAngle = 1.1f;   // rad: slides past this stop rotating
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float Esc = 2.5f;          // stability control: pulls the yaw rate back toward what the steering asks, 1/s
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float EscSlip = 8.f;      // stability control: damps rotation as the slide angle grows, 1/s
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float KeepF = 0.3f;      // share of the front tyres' sideways grip kept under throttle or brakes
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float KeepR = 0.7f;      // the same for the rear (traction and brake control; the powerslide drops it to 0.2)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float SteerLock = 0.62f;   // rad at a standstill
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float SteerFade = 16.f;    // m/s: lock halves by this speed
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float CamSlide = 0.15f;    // chase camera swing toward the travel
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float FlyAngle = 0.9f;     // flight: steepest climb or dive, rad
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Handling") float AirLift = 0.5f;      // air brake: share of the weight carried
};

/** What the car can do at its level (js/progress.js capsFor). The default is the full car (level 6). */
struct FSkyCaps
{
	double Drive = 63.1, Accel = 62.4, Top = 103;
	bool bBoost = true, bDoubleJump = true, bWalls = true, bHover = true, bFlight = true;
	double Fans = 1;
};

enum class ESkyEv : uint8
{
	Jump, DoubleJump, Dodge, Righted, Land, Impact, Damage, Explode, Touchdown, WallRide,
	Move, Combo, Stunt, Pad, Charge, Charge80, Charged, Locked, Sixty, AirBrake, Landing, Flight, Addon
};

struct FSkyEvent
{
	ESkyEv Type;
	FString Name;        // move / stunt / locked system / combo result / add-on id / touchdown kind
	double A = 0, B = 0; // strength, points, time, hp ...
	int32 I = 0;         // multiplier, big pad ...
	TArray<FString> Moves;
};

struct FSkyToast
{
	FString Title, Sub;
	double Born = 0;
};

/** One challenge (js/progress.js LEVELS[].goals). */
struct FSkyGoal
{
	const TCHAR* Id;
	const TCHAR* Text;
	const TCHAR* Stat;
	double Target;
	const TCHAR* Unit;
	bool bMin;
};

struct FSkyLevel
{
	const TCHAR* Name;
	const TCHAR* Blurb;
	double Mph, Sixty, BoostMph;
	bool bDoubleJump, bWalls;
	double Fans;
	bool bHover, bFlight;
	int32 NumGoals;
	FSkyGoal Goals[3];
};

namespace Skyster
{
	extern const FSkyLevel Levels[6];
	constexpr int32 NumLevels = 6;
	FSkyCaps CapsFor(int32 Level);
	FString MoveName(const FString& Id);
	int32 MovePoints(const FString& Id);
	FString MoveList(const TArray<FString>& Moves);

	struct FAddon { const TCHAR* Id; const TCHAR* Name; int32 Mult; FLinearColor Col; };
	extern const FAddon Addons[3];
}
