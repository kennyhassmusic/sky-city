// The race's insides, shared by SkyCourseRace.cpp (laps, gates, routing, respawn, contact, results, HUD) and
// SkyCourseAI.cpp (the AI drivers). Private to the race: nothing else includes this.
#pragma once

#include "CoreMinimal.h"
#include "SkyCourse.h"
#include "SkysterCar.h"

class UFont;

DECLARE_LOG_CATEGORY_EXTERN(LogSkyRace, Log, All);

namespace SkyRaceK
{
	constexpr double G = 650 * 3.9 / 100;          // 25.4 m/s^2: the car's gravity (SkysterCar.cpp SkyP::G)
	constexpr double WHEELBASE = 2.825;
	constexpr double SUCTION = 2.0;                 // the fans' pull on a wall, in G
	constexpr double AERO = 0.8;                    // wing downforce at top speed, G (FSkyHandling::Aero)
	constexpr double MAX_SPEED = 103;               // m/s, 230 mph
	constexpr double STOP_DECEL = 30;               // m/s^2, the brakes
	constexpr double HOP_DV = 20.0;                 // m/s of climb from a held jump at a lip (11.4 + the 0.2 s hold, less gravity)
	constexpr double COUNTDOWN = 3.0;               // s: 3, 2, 1, go
	constexpr int32 SEARCH = 24;                    // frames (12 m) each way the tracker looks for a car
	constexpr double OFF_LAT = 3.0;                 // m past the deck's edge that counts as off the track
	constexpr double OFF_T = 1.0;                   // s off the track before a respawn (Lakitu-quick: Design/RaceHandling.md)
	constexpr double GHOST_T = 1.5;                 // s after a respawn with no car-to-car contact
	constexpr double GOOD_BACK = 10.0;              // m a respawn goes back from the last good spot
	constexpr double KEEP_V = 0.7, KEEP_MIN = 25.0; // a respawn keeps this share of the speed it had there, at least this
	constexpr double DRAFT = 0.04;                  // slipstream: up to this much more top speed right behind a car
	constexpr double DRAFT_LEN = 25.0, DRAFT_SIDE = 2.5;   // m behind and across that count
	constexpr double BAND = 0.06;                   // AI rubber band: up to this much less (ahead) or more (behind) top speed
	constexpr double BAND_FROM = 40.0, BAND_FULL = 200.0;  // m from the player where it starts and is full
	constexpr double NUDGE_MAX = 0.35;              // smart steering: the most it adds to the stick
	constexpr double NUDGE_LOOK = 0.6;              // s ahead it looks for the edge
	constexpr double AIR_PULL = 3.0;                // m/s^2 at most: landing help's drift toward the pad's middle
	constexpr double WRONG_T = 1.0;                 // s in a closed branch before the car goes back to the split
}

/** What the race knows about one baked segment beyond its frames. */
struct FSegX
{
	TArray<float> Cum;                // m from the segment's first frame, per frame
	TArray<float> VMax;               // m/s: the bend and bank limit at each frame (a full-skill driver)
	TArray<float> KL;                 // 1/m: how fast the track turns across its own deck at each frame (+ = left)
	TArray<int32> Prev;               // segments that lead into this one
	float Len = 0;
	int32 Split = INDEX_NONE, Branch = INDEX_NONE;   // a split's lead-in to one branch: which split and branch
	// what the AI must plan for
	float NeedV = 0;                  // m/s needed at frame NeedAt: a loop's entry, a jump's take-off speed, a corkscrew's
	float CapV = 0;                   // m/s at most at the lip (a jump that would overshoot); 0 = no limit
	int32 NeedAt = 0;
	int32 LandAt = INDEX_NONE;        // a jump: the first deck frame past the gap
	int32 AimAt = INDEX_NONE;         // a jump: the pad frame its take-off speed lands on
	float MinV = 0;                   // a jump: the least take-off speed that reaches the pad
	float ForkOff = 0;                // a split's lead-in: how far left of the main line's middle it leaves the fork (m)
	bool bHop = false;                // a jump: also jump at the lip
	bool bLoop = false, bJump = false, bBoost = false, bCork = false;
};

/** One tick of an AI car, kept for the last few seconds so a respawn can say what led up to it. */
struct FAITrace
{
	float T = 0, S = 0, Lat = 0, VLat = 0, Vf = 0, Psi = 0, Beta = 0, Roll = 0, Vert = 0;
	float Steer = 0, Thr = 0, Brk = 0, Want = 0, TargetV = 0, Pitch = 0, Yaw = 0;
	int16 Seg = 0, Frame = 0;
	bool bGround = false, bBoost = false, bSlide = false, bBump = false, bYield = false;
};

/** A car's way round for one lap: the segments it drives, start gate to finish (or back round to the start gate). */
struct FRoute
{
	TArray<int32> Segs;
	TArray<double> At;                // route distance where each segment starts
	TArray<int32> Choice;             // the branch taken at each split (FSkyBaked::Splits)
	TArray<int32> Checks;             // checkpoint gates (FSkyBaked::Gates) on this route, in order
	TArray<double> CheckS;
	double Len = 0;                   // m, the segments end to end
	double GateS = 0;                 // route distance of the start gate
	double EndS = 0;                  // where the lap ends: round to the start gate again (Len + GateS), or the finish gate
	double LapLen() const { return FMath::Max(1.0, EndS - GateS); }
};

struct FAIDriver
{
	FRandomStream Rand;
	double K = 0.5;                   // skill mapped onto 0..1 (0.3..1.2)
	double Pace = 1, Cap = 100, BrakeA = 20, React = 0.1, WanderAmp = 0.5;
	double Steer = 0, Throttle = 0;
	double WanderOff = 0, WanderGoal = 0, WanderT = 0;
	double AvoidLat = 0, AvoidT = 0;
	double HopT = -1;                 // s the jump has been held at a lip (-1: not jumping)
	int32 JumpSeg = INDEX_NONE;       // the jump it last left the deck from
	double TargetV = 0, NeedV = 0;    // for tests and tuning
	double WatchT = 0, WatchP = 0, WatchDist = 0;   // progress watchdog: s, progress and metres driven since it last looked
	bool bBoost = false;
	double LaunchLat = 0, LaunchVLat = 0;   // across the deck and sideways speed when it last left the ground (diagnostics)
	bool bWasGrounded = true;
	// the lateral controller (SkyCourseAI.cpp)
	double Line = 0, LineV = 0;       // m left of the middle it's steering for now (eases toward the wanted line), and its rate
	bool bLineSet = false;
	int32 LineSeg = INDEX_NONE;       // the segment Line is measured on, and its frame's middle last tick
	FVector LineP = FVector::ZeroVector;
	double PrevPsi = 0;               // the nose against the track last tick, for the yaw rate
	bool bYawSet = false;
	double YawRate = 0;               // rad/s across the deck, + = left (smoothed)
	double SlideT = 0;                // s the tail has been out
	// the last few seconds of driving (a ring), dumped into the log when the car is put back on the track
	TArray<FAITrace> Trace;
	int32 TraceHead = 0, TraceNum = 0;
};

struct FRacer
{
	TWeakObjectPtr<ASkysterCar> Car;
	FString Name;
	FLinearColor Color = FLinearColor::White;
	bool bPlayer = false, bAI = false;
	double Skill = 1.0;
	double Lane = 0;                  // -1..1: its line across the deck (+ = left)
	double Radius = 1.0, HalfLen = 1.4;   // contact shape: two balls along the car
	FTransform Slot;                  // its grid slot (Unreal)
	// where it is
	int32 Seg = 0, Frame = 0, Ri = 0; // segment, frame on it, index in Route.Segs (INDEX_NONE: off its route)
	bool bWrapped = false;            // round the end of the lap into the start piece, not over the line yet
	double S = 0;                     // m along its route
	double Lat = 0, Vert = 0, D2 = 0; // m across and above the deck at its frame; squared distance to the frame
	double Progress = -1;             // laps done plus the share of this one
	FVector Prev = FVector::ZeroVector;
	FRoute Route;
	TArray<bool> Entered;             // per split: into a branch this lap
	TArray<bool> Passed;              // per gate: passed this lap
	// race
	int32 Lap = 1, NextCheck = 0, Place = 0;
	bool bStarted = false, bFinished = false, bLapBest = false;
	double LapStart = 0, FinishT = -1, BestLap = -1, LastLap = -1;
	TArray<double> LapTimes, Splits;
	TArray<double> LapSplits, BestSplits;   // per gate: split this lap, split on its best lap (-1 none)
	TArray<FString> Branches;
	// recovery
	struct FGood { int32 Seg = 0, Frame = 0; double S = 0, V = 0; };
	TArray<FGood> Good;               // the last good spots on the deck this lap (every 2 m, newest last): where a fall goes back to
	int32 GoodLap = 0;
	double GhostUntil = -99;          // no car-to-car contact until then (just put back on the track)
	// race assists and catch-up (Design/RaceHandling.md)
	double Nudge = 0, NudgeT = -99, Draft = 0;
	int32 SafeSeg = INDEX_NONE, SafeFrame = 0;   // the last gate passed (INDEX_NONE: its grid slot)
	double OffT = 0, SlowT = 0, DeadT = 0, WrongT = 0, ReverseT = 0;
	double BumpT = -99;               // the last time it touched another car (s since Begin)
	int32 WrongSplit = INDEX_NONE, Respawns = 0, WrongWays = 0;
	FString OffInfo;                  // where and how it left the track (for the respawn's log line)
	// shown on the HUD
	double SplitDelta = 0, SplitRef = -1, SplitT = -99, MissT = -99, WrongShowT = -99, LapT = -99, RespawnT = -99;
	int32 SplitGate = 0;
	FAIDriver AI;
};

class FSkyCourseRaceImpl
{
public:
	explicit FSkyCourseRaceImpl(ASkyCourseRace* InOwner) : Owner(InOwner) {}
	~FSkyCourseRaceImpl();

	bool Begin(ASkyCourseTrack* InTrack, const FSkyCourse& InCourse, ASkysterCar* Player, int32 Opponents, double Skill);
	void End();
	void Tick(float DeltaSeconds);
	TArray<ASkyCourseRace::FResult> Results() const;
	FString ResultsJson() const;
	void DrawHud(AHUD* Hud, UCanvas* Canvas, float S);

	ASkyCourseRace* Owner;
	TWeakObjectPtr<ASkyCourseTrack> Track;
	FSkyBaked B;                      // the bake as the race began (the course can't change under it)
	FSkyCourse Course;
	int32 Laps = 1;
	TArray<FSegX> X;
	TArray<int32> GateFrame;          // the frame each gate stands on
	int32 StartGate = INDEX_NONE, FinishGate = INDEX_NONE;
	TArray<TArray<bool>> Shown;       // per split, per branch: open as the gates show it now
	TArray<TArray<FString>> BranchDir;   // per split, per branch: "LEFT", "RIGHT"...
	TArray<TArray<int32>> LapChoice;  // per lap: the branch at each split on that lap's own route
	int32 ShownLap = 0;
	TArray<FRacer> Racers;
	enum class EPhase : uint8 { Countdown, Racing, Done } Phase = EPhase::Countdown;
	double T = 0;                     // s since Begin
	double Clock() const { return T - SkyRaceK::COUNTDOWN; }   // the race clock: 0 at GO
	double DoneT = -1;
	struct FHeld
	{
		bool bOn = false;
		float Thr = 0, Brk = 0, Stop = 0, Steer = 0, Pitch = 0, Roll = 0;
		bool bBoost = false, bJump = false, bSlide = false, bFly = false;
		void Save(const ASkysterCar& C);
		void Restore(ASkysterCar& C) const;
	} Held;                           // the player's own test input, kept over the countdown hold
	bool bHolding = false;
	ESkyAssist PlayerAssist = ESkyAssist::Full;   // the player's race assists (the course menu's setting, read at Begin)
	// the player's best on this course
	FString TimesPath;
	double PbLap = -1, PbRace = -1;
	TMap<int32, double> PbSplits;
	bool bNewPbLap = false, bNewPbRace = false, bSaved = false;
	int32 PlayerIdx = INDEX_NONE;
	TArray<FString> Events;
	TArray<FString> Traces;           // the AI's last seconds before each respawn (tests and tuning)
	TArray<FVector> GlowPts;
	TArray<int32> Order;              // racers by place
	TArray<uint8> Seen;
	int32 Bumps = 0;
	double TickSecs = 0, TickMax = 0;  // the race's own cost per tick (all cars: tracking, gates, contact, AI)
	int64 Ticks = 0;
	TWeakObjectPtr<UFont> Font;
	FDelegateHandle DrawHandle;

	struct FBest { double D2; int32 Seg, I; };

	void Note(const FString& Msg);
	bool IsOpen(int32 Sp, int32 Br, int32 Lap) const;
	bool Drives(const FRacer& R) const;
	static double AutopilotSkill();   // SkyCourse.RaceAutopilot (0 = off)
	void Prepare();
	void PrepareSeg(int32 S);
	int32 NearestOnSeg(int32 Sg, const FVector& P) const;
	void BuildRoute(FRacer& R, const TArray<int32>& Choice);
	TArray<int32> ChoiceFor(const FRacer& R, int32 Lap) const;
	void RefreshChoice(FRacer& R);
	void FitRoute(FRacer& R);
	void UpdateGates(int32 Lap);
	FTransform GridSlot(int32 K) const;
	static void Hold(ASkysterCar& C);
	static void Paint(ASkysterCar& Car, int32 PaintIdx);
	void SearchFwd(int32 Sg, int32 From, int32 Budget, const FVector& P, FBest& Best, int32 Depth) const;
	void SearchBack(int32 Sg, int32 From, int32 Budget, const FVector& P, FBest& Best, int32 Depth) const;
	void Locate(FRacer& R, const ASkysterCar& Car, double Dt);
	void Gates(FRacer& R, const FVector& A, const FVector& Bp, double Dt);
	void LapDone(FRacer& R, double Tc);
	void Recover(FRacer& R, ASkysterCar& Car, double Dt);
	void Respawn(FRacer& R, const TCHAR* Why);
	void NoteGood(FRacer& R, const ASkysterCar& Car);
	bool RespawnGood(FRacer& R, const TCHAR* Why);
	ESkyAssist AssistFor(const FRacer& R) const;
	void Assists(FRacer& R, ASkysterCar& Car, double Dt);
	static void ClearRaceHooks(ASkysterCar& Car);
	/** Lat: m left of the middle to put it (default: its lane; the player in the middle). */
	void RespawnAt(FRacer& R, int32 Sg, int32 I, double Ahead, const TCHAR* Why, double Lat = TNumericLimits<double>::Max());
	void LimitTransitions();
	void AfterTeleport(FRacer& R, const TCHAR* Why, const TCHAR* Where);
	void Contacts();
	void Places();
	void LoadTimes();
	void SaveTimes();
	UFont* GetFont();
	// SkyCourseAI.cpp
	void InitAI(FRacer& R, int32 Index);
	void Drive(FRacer& R, ASkysterCar& Car, double Dt);
	void DumpTrace(const FRacer& R, const TCHAR* Why);
	/** A point along a car's route (wrapping into the next lap on a lap course): segment, frame, route distance. */
	struct FCursor { int32 Ri = INDEX_NONE; int32 Seg = 0; int32 I = 0; double S = 0; };
	FCursor CursorOf(const FRacer& R) const;
	bool Step(const FRacer& R, FCursor& C) const;
};
