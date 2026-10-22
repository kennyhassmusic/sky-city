// Course Builder: players (or their LLM, through the in-game MCP server) snap track pieces together and race on them.
// Design: Design/CourseBuilder.md. This header is the contract between the four parts:
//   SkyCourseModel.cpp  the course file (parse, validate, write) and the bake: every piece turned into centre-line frames
//   SkyCourseTrack.cpp  ASkyCourseTrack: the track you see and drive on (meshes, skins, gates, lights, walls)
//   SkyCourseRace.cpp   ASkyCourseRace: laps, checkpoints, lap routing through splits, timing, respawn, AI opponents
//   SkyCourseMode.cpp   ASkyCourseMode: the game mode's director, build mode (camera, cursor, palette, menus), saving
//   SkyCourseMcp.cpp    FSkyCourseMcp: the local MCP server (127.0.0.1 only) that lets an LLM edit courses
//
// Units and frames: metres and degrees, in the car sim's world frame (ASkysterCar): right-handed, z up, Unreal X = x,
// Unreal Y = -y, so Unreal cm = (x * 100, -y * 100, z * 100). Yaw is counter-clockwise from +x (Unreal yaw = -yaw).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "SkyCourse.generated.h"

class AHUD;
class UCanvas;
class ASkysterCar;
class ASkyCourseTrack;
class ASkyCourseRace;
class FSkyCourseMcp;

namespace SkyCourse
{
	constexpr int32 FormatVersion = 1;
	constexpr double LaneWidth = 5.5;           // m: one lane is the McGregor unveil ramp's deck
	constexpr int32 MinLanes = 1, MaxLanes = 4, DefaultLanes = 2;
	constexpr int32 MaxPieces = 400;            // every piece in the course, branches included
	constexpr int32 MaxCheckpoints = 32;
	constexpr int32 MaxBranches = 4;            // per split
	constexpr int32 MaxSplitDepth = 3;          // splits inside branches inside branches
	constexpr int32 MaxLaps = 9;
	constexpr int32 MaxOpponents = 7;
	constexpr double SampleStep = 0.5;          // m between baked frames
	constexpr int32 McpPort = 47800;

	/** True when the current map was opened as the Course Builder (McGregor with the URL option mode=build). */
	SKYCITY_API bool IsBuildMode(const UWorld* World);
	/** Where courses are saved: <Saved>/Courses (inside the app's sandbox container in the packaged game). */
	SKYCITY_API FString CoursesDir();
	/** A course name made safe for a file name: letters, digits, spaces, dashes and underscores, 1-48 chars ("" if none left). */
	SKYCITY_API FString SafeName(const FString& Name);
	/** Unreal cm <-> course metres. */
	inline FVector ToUE(const FVector& M) { return FVector(M.X * 100.0, -M.Y * 100.0, M.Z * 100.0); }
	inline FVector FromUE(const FVector& C) { return FVector(C.X / 100.0, -C.Y / 100.0, C.Z / 100.0); }
	inline FVector DirToUE(const FVector& D) { return FVector(D.X, -D.Y, D.Z); }
}

enum class ESkyPiece : uint8
{
	Start,       // start gate with the starting grid behind it; must be first; 30 m long
	Finish,      // finish gate; ends a point-to-point course (laps = 1); 6 m long
	Checkpoint,  // gate; 6 m long
	Straight,    // Length
	Curve,       // Angle (+ = left), Radius, Bank (peak bank mid-curve, 0 at both ends)
	Ramp,        // Length, Rise (S-shaped: level at both ends, steepest 45 deg max)
	Jump,        // Gap, Drop: a lip, an open gap (no deck), a landing pad Drop metres higher (+) or lower (-)
	Loop,        // Radius, Offset (sideways shift so the exit clears the entry)
	Corkscrew,   // Length, Turns (track rolls about its own axis, ends level)
	WallRide,    // Length, Side (track twists up to vertical on that side and back)
	Booster,     // Length (speed strip: component tag SkyBoost)
	Lanes,       // Length, Lanes (widens or narrows to the new lane count), Align (-1 left, 0 centre, +1 right)
	Split,       // Length, Branches (each its own piece list), Gate, then the branches rejoin: MergeLength, MergeLanes
	Close,       // last piece of a lap course: an automatic connector back into the start gate
	Count
};

enum class ESkyGate : uint8 { None, Lights, Wall };   // how a split shows which branch is open this lap
enum class ESkySkin : uint8 { Unveil, Classic, Neon, Count };   // Unveil (default): McGregor ramp concrete, red edge trim

/** One branch of a split. */
struct FSkyBranch
{
	int32 Lanes = 1;
	double Angle = 0;          // deg the branch heads off at, relative to the split (+ = left)
	TArray<int32> Laps;        // laps (1-based) this branch is open on; empty = every lap
	int32 Seq = INDEX_NONE;    // index into FSkyCourse::Seqs: the branch's pieces
};

struct FSkyPiece
{
	ESkyPiece Type = ESkyPiece::Straight;
	double Length = 0, Angle = 0, Radius = 0, Bank = 0, Rise = 0, Gap = 0, Drop = 0, Offset = 0, Turns = 0;
	int32 Side = 1;            // WallRide: +1 left, -1 right
	int32 Lanes = 0;           // Lanes: the new count
	int32 Align = 0;           // Lanes: -1 left, 0 centre, +1 right
	// Split
	TArray<FSkyBranch> Branches;
	ESkyGate Gate = ESkyGate::Lights;
	double MergeLength = 30;
	int32 MergeLanes = 0;      // 0 = the lane count before the split
};

/** A list of pieces laid end to end: Seqs[0] is the main track, the others are split branches. */
struct FSkySeq
{
	TArray<FSkyPiece> Pieces;
};

struct FSkyCourse
{
	FString Name = TEXT("New Course");
	FString Author;
	FVector Start = FVector::ZeroVector;   // m: where the start piece begins (its deck surface)
	double Yaw = 0;                        // deg
	int32 Lanes = SkyCourse::DefaultLanes; // lane count at the start
	ESkySkin Skin = ESkySkin::Unveil;
	int32 Laps = 1;                        // > 1 needs a lap course (ends with Close)
	int32 Opponents = 0;                   // AI opponents by default
	double Skill = 0.8;                    // AI skill 0.3-1.2
	TArray<FSkySeq> Seqs = { FSkySeq() };
};

/** A point on a baked centre-line. */
struct FSkyFrame
{
	FVector P = FVector::ZeroVector;       // m, on the deck surface at the centre of the track
	FVector F = FVector(1, 0, 0);          // forward
	FVector L = FVector(0, 1, 0);          // left (across the deck)
	FVector U = FVector(0, 0, 1);          // up (out of the deck)
	double Width = SkyCourse::LaneWidth * SkyCourse::DefaultLanes;   // m, deck width here
	double S = 0;                          // m along the course from the start gate (main line; branches continue it)
	bool bDeck = true;                     // false over a jump's gap (nothing to drive on)
};

enum class ESkySeg : uint8 { Piece, SplitLead, MergeLead, MergeTrunk, CloseLink };

/** One drivable stretch of baked track: a piece, or a generated part of a split/merge/close. */
struct FSkySegment
{
	ESkySeg Kind = ESkySeg::Piece;
	ESkyPiece Type = ESkyPiece::Straight;
	int32 Seq = 0, Piece = 0;              // the piece it comes from (for a split's leads and merge: the Split piece)
	int32 Branch = INDEX_NONE;             // SplitLead / MergeLead: which branch
	int32 Lanes = SkyCourse::DefaultLanes; // lanes at the end of the segment
	TArray<FSkyFrame> Frames;              // every SampleStep m, first = start, last = end
	TArray<int32> Next;                    // segments that follow (several after a split lead-in point; usually one)
};

/** The baked course: everything the track, the race, the builder and the MCP server need to know about the geometry. */
struct FSkyBaked
{
	bool bValid = false;                   // no errors: safe to build and race
	TArray<FString> Errors;                // "pieces[3] (curve): radius 4 is below 8" style, with the JSON path
	TArray<FString> Warnings;
	TArray<FSkySegment> Segs;              // Segs[0] starts at the start gate
	struct FGate { ESkyPiece Type; int32 Seg; FSkyFrame At; int32 Index; };   // start, finish, checkpoints (Index = order)
	TArray<FGate> Gates;
	struct FSplitInfo { int32 Seq, Piece; ESkyGate Gate; TArray<int32> LeadSegs; TArray<TArray<int32>> OpenLaps; FSkyFrame At; };
	TArray<FSplitInfo> Splits;             // in course order
	TArray<FTransform> Grid;               // Unreal transforms of the starting grid slots (player first)
	FSkyFrame End;                         // where the last main piece ends (the builder's cursor for the main line)
	bool bLapCourse = false;               // ends with Close
	double Length = 0;                     // m, main line start gate to finish (or around once)
	FBox Bounds = FBox(ForceInit);         // m
	double MinZ = 0, MaxZ = 0;             // m, deck surface
	int32 PieceCount = 0;
};

namespace SkyCourse
{
	/** Course JSON (format skycity-course v1, see Design/CourseBuilder.md) -> course. False with errors if it's not a course. */
	SKYCITY_API bool Parse(const FString& Json, FSkyCourse& Out, TArray<FString>& Errors);
	/** Course -> JSON (pretty, the same format Parse reads). */
	SKYCITY_API FString Write(const FSkyCourse& Course);
	/** One piece object <-> JSON (for the MCP server's add/update tools). Path is used in error messages. */
	SKYCITY_API bool ParsePiece(const TSharedPtr<class FJsonObject>& Obj, FSkyCourse& Course, FSkyPiece& Out, const FString& Path, TArray<FString>& Errors);
	SKYCITY_API TSharedPtr<class FJsonObject> PieceToJson(const FSkyCourse& Course, const FSkyPiece& Piece);
	/** Validate and bake: limits, the build area (BuildArea, m; an empty box = no limit), clearances, then the frames. */
	SKYCITY_API void Bake(const FSkyCourse& Course, const FBox& BuildArea, FSkyBaked& Out);
	/** Where the next piece would start at the end of a sequence (the builder's cursor), and the lane count there. */
	SKYCITY_API FSkyFrame EndOf(const FSkyBaked& Baked, const FSkyCourse& Course, int32 Seq, int32* OutLanes = nullptr);
	/** The segments to drive for a lap (1-based), from the start gate round to the finish (or back to the start):
	 *  at every split, the first branch open on that lap (or Choice[SplitIndex] if that branch is open). */
	SKYCITY_API TArray<int32> Route(const FSkyBaked& Baked, int32 Lap, const TArray<int32>& Choice = TArray<int32>());
	/** Piece names in the file format ("straight", "curve", ...) and back. */
	SKYCITY_API const TCHAR* PieceName(ESkyPiece Type);
	SKYCITY_API ESkyPiece PieceFromName(const FString& Name);
	SKYCITY_API const TCHAR* SkinName(ESkySkin Skin);
	/** A default piece of a type with sensible settings (the builder's palette, the MCP guide's examples). */
	SKYCITY_API FSkyPiece DefaultPiece(ESkyPiece Type, int32 LanesHere);
	/** Plain-text guide for an LLM: the format, every piece with its limits, tips (loops need speed, etc.). */
	SKYCITY_API FString Guide();
	/** A short example course near Start facing Yaw (used for "new course" and tests). */
	SKYCITY_API FSkyCourse Example(const FVector& Start, double Yaw);
}

/** The track you see and drive on: one procedural mesh component per segment (tags SkyTrack, and SkyBoost on boosters),
 *  gates, the starting grid, signal lights and switching walls at splits. Rebuilds only the segments that changed. */
UCLASS()
class SKYCITY_API ASkyCourseTrack : public AActor
{
	GENERATED_BODY()
public:
	ASkyCourseTrack();
	/** Bake and build. Keeps the last good track standing if the course has errors (they're in the returned bake). */
	const FSkyBaked& Build(const FSkyCourse& Course, const FBox& BuildArea);
	const FSkyBaked& GetBaked() const { return Baked; }
	/** Signal lights green/red and switching walls down/up for one branch of a split (FSkyBaked::Splits index). */
	void SetBranchOpen(int32 SplitIndex, int32 Branch, bool bOpen);
	/** A see-through ghost of the piece the builder is about to place, starting at Start with Lanes lanes (nullptr hides it). */
	void ShowPreview(const FSkyPiece* Piece, const FSkyFrame& Start, int32 Lanes, bool bFits);
	/** Highlight a segment (the builder's selection), or none. */
	void Highlight(int32 Seg);
	/** Red trim glows brighter as cars pass (like the unveil's LED bars); call with the cars' positions (Unreal cm). */
	void UpdateGlow(const TArray<FVector>& Cars, float Dt);
	void Clear();
private:
	FSkyBaked Baked;
	UPROPERTY() TArray<TObjectPtr<class UProceduralMeshComponent>> SegMeshes;
	UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> Props;   // gates, lights, walls, grid markers
	UPROPERTY() TObjectPtr<class UProceduralMeshComponent> Preview;
	TArray<uint32> SegHashes;
	ESkySkin BuiltSkin = ESkySkin::Count;
	friend class FSkyCourseTrackImpl;
};

/** The race: the player's car and optional AI opponents (more ASkysterCars driven through their test-input hooks)
 *  from the starting grid, laps, checkpoints in order, lap routing (which branch is open on which lap), timing and
 *  splits, respawn at the last checkpoint after a fall, results. */
UCLASS()
class SKYCITY_API ASkyCourseRace : public AActor
{
	GENERATED_BODY()
public:
	ASkyCourseRace();
	virtual void Tick(float DeltaSeconds) override;
	/** Countdown, then go. Opponents 0-7, Skill 0.3-1.2. */
	void Begin(ASkyCourseTrack* Track, const FSkyCourse& Course, ASkysterCar* Player, int32 Opponents, double Skill);
	/** Stop and remove the opponents (the player's car stays). */
	void End();
	bool IsRunning() const { return bRunning; }
	struct FResult { FString Name; bool bPlayer = false; int32 Lap = 0; double Time = -1; TArray<double> LapTimes; TArray<double> Splits; int32 Place = 0; bool bFinished = false; };
	TArray<FResult> GetResults() const;
	double BestLap() const { return Best; }
	/** Race HUD: countdown, lap x/y, time, splits, position, "take the left branch" hints, wrong-way warnings. */
	void DrawHud(AHUD* Hud, UCanvas* Canvas, float S);
private:
	bool bRunning = false;
	double Best = -1;
	friend class FSkyCourseRaceImpl;
	TSharedPtr<class FSkyCourseRaceImpl> Impl;
};

/** The Course Builder game mode's director: spawned by the player's ASkysterCar when the map opens in build mode.
 *  Owns the course, the track, the race and the MCP server; switches between building (its own camera pawn,
 *  ASkyCourseBuilderPawn) and driving (the player's car). */
UCLASS()
class SKYCITY_API ASkyCourseMode : public AActor
{
	GENERATED_BODY()
public:
	ASkyCourseMode();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	static ASkyCourseMode* Get(const UWorld* World);

	// --- the course (all edits go through here: validated, baked, rebuilt; the MCP server calls these too) ---
	const FSkyCourse& GetCourse() const { return Course; }
	const FSkyBaked& GetBaked() const;
	/** Replace the course. False (and the old course stays) if it has errors, which come back in Errors. */
	bool SetCourse(const FSkyCourse& NewCourse, TArray<FString>& Errors);
	/** Change the course with a function; rolled back if the result has errors. */
	bool Edit(TFunctionRef<void(FSkyCourse&)> Change, TArray<FString>& Errors);
	bool Undo();
	FBox BuildArea() const { return Area; }   // m

	// --- files ---
	TArray<FString> ListCourses() const;
	bool SaveCourse(const FString& Name, FString& Error);
	bool LoadCourse(const FString& Name, FString& Error);

	// --- driving ---
	void StartTestDrive(int32 Opponents = -1);   // -1 = the course's default
	void StopTestDrive();
	bool IsDriving() const { return bDriving; }
	ASkysterCar* GetCar() const;
	ASkyCourseRace* GetRace() const { return Race; }
	ASkyCourseTrack* GetTrack() const { return Track; }

	// --- the MCP server (off until the player or a config switch turns it on) ---
	bool SetMcpEnabled(bool bOn);
	bool IsMcpEnabled() const;
	/** Thread-safe: the MCP server queues work here and it runs on the game thread next tick. */
	void RunOnGameThread(TFunction<void()> Work);

	/** Build-mode and race HUD (called by ASkysterHUD every frame, before the car's own HUD). */
	void DrawHud(AHUD* Hud, UCanvas* Canvas, float S);

private:
	FSkyCourse Course;
	TArray<FSkyCourse> UndoStack;
	FBox Area = FBox(ForceInit);
	bool bDriving = false;
	UPROPERTY() TObjectPtr<ASkyCourseTrack> Track;
	UPROPERTY() TObjectPtr<ASkyCourseRace> Race;
	UPROPERTY() TObjectPtr<class ASkyCourseBuilderPawn> Builder;
	TSharedPtr<FSkyCourseMcp> Mcp;
	TArray<TFunction<void()>> Pending;
	FCriticalSection PendingLock;
	friend class ASkyCourseBuilderPawn;
};

/** The build-mode camera and controls: orbit/top-down camera over the cursor at the end of the track being edited,
 *  the piece palette, the course menu (new, save, load, rename, skin, laps, opponents, LLM link). */
UCLASS()
class SKYCITY_API ASkyCourseBuilderPawn : public APawn
{
	GENERATED_BODY()
public:
	ASkyCourseBuilderPawn();
	virtual void Tick(float DeltaSeconds) override;
	void DrawHud(AHUD* Hud, UCanvas* Canvas, float S);
	UPROPERTY(VisibleAnywhere) TObjectPtr<class UCameraComponent> Camera;
	TWeakObjectPtr<ASkyCourseMode> Mode;
	int32 EditSeq = 0;           // the sequence the cursor is on (0 = main line, else a branch)
	int32 PaletteIndex = 0;      // which piece type is selected
	FSkyPiece Pending;           // the piece about to be placed, with its settings
private:
	friend class FSkyCourseBuilderImpl;
	TSharedPtr<class FSkyCourseBuilderImpl> Impl;
};

/** The local MCP server: Streamable HTTP on 127.0.0.1:SkyCourse::McpPort/mcp, JSON-RPC 2.0, protocol 2025-03-26 and
 *  later, JSON responses (no SSE). Rejects non-local Origin headers. Only course tools: see Design/CourseBuilder.md. */
class SKYCITY_API FSkyCourseMcp
{
public:
	explicit FSkyCourseMcp(ASkyCourseMode* InMode);
	~FSkyCourseMcp();
	bool Start(int32 Port = SkyCourse::McpPort);
	void Stop();
	bool IsRunning() const;
	FString Url() const;
private:
	TWeakObjectPtr<ASkyCourseMode> Mode;
	struct FState;
	TSharedPtr<FState> State;
};
