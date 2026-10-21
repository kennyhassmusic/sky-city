// Sky City's traffic, on the street network Scripts/roads/roadnet.py designed (Content/SkyCity/Data/traffic.json):
// cars from Kenny's McGregor line-up driving the streets, and (switched on from the Garage or with C) Cybercabs
// flying the same lanes mirrored in the sky, stopping at floating signals. Everyone keeps to their lane, follows the
// car ahead, stops on red and yellow, and stops at stop signs before going on. The signals run on the same clock as
// the street signal heads' lenses (M_SignalLens2), so the cars and the lights agree.
// The cars live around the player: the ones far away are moved to streets ahead of you.
//
// Solid traffic (20 Oct, traffic-collisions): nobody drives through anybody.
// - Junctions: a car takes a crossing only when no conflicting movement is inside it or has reserved it (paths
//   tested as polylines from the stop line to where the junction box ends), with room to clear it on the far side.
//   Turns, stop-sign streets and slower streets give way to approaching traffic with priority (gap acceptance);
//   after waiting 10 s a car queues a request that later arrivals respect, so nobody starves.
// - Following sees anything across the car's own lane (lane changes, merges, the real crossing length, bodies
//   straight ahead on short links and bends, the player); lane changes wait for a gap.
// - Cars are placed only on free road, never onto or next to another car or the player.
// - Last resort: a move that would make two bodies overlap is not made (the later car holds). Stuck cars (deadlocks,
//   flaws in traffic.json) are moved away after a while: at once out of sight, with a quick shrink in sight.
// - Hit boxes: every body has a box that blocks the Visibility channel the Roadster's sweeps use, so it crashes into
//   traffic like into anything solid (the actor is tagged NoWallRide). A hit car brakes to a stop, gets shoved a
//   little, waits a few seconds and carries on; one pinned by the player shrinks away and reappears elsewhere.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkysterTraffic.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UBoxComponent;

UCLASS()
class SKYCITY_API ASkysterTraffic : public AActor
{
	GENERATED_BODY()

public:
	ASkysterTraffic();
	virtual void Tick(float DeltaSeconds) override;

	/** True once the network loaded. */
	bool IsReady() const { return Links.Num() > 0; }
	UFUNCTION(BlueprintCallable, Category = "Traffic") void SetGround(bool bOn);
	UFUNCTION(BlueprintCallable, Category = "Traffic") void SetSky(bool bOn);
	UFUNCTION(BlueprintPure, Category = "Traffic") bool IsGround() const { return bGround; }
	UFUNCTION(BlueprintPure, Category = "Traffic") bool IsSky() const { return bSky; }
	/** Test hook: counters as JSON (cars, commits, holds, relocations, crashes, lanes dropped from traffic.json...). */
	UFUNCTION(BlueprintCallable, Category = "Traffic|Test") FString GetDebugStats() const;

	UPROPERTY(EditAnywhere, Category = "Traffic") int32 GroundCars = 56;
	UPROPERTY(EditAnywhere, Category = "Traffic") int32 SkyCabs = 36;
	/** Height of the sky lanes over the streets, m. */
	UPROPERTY(EditAnywhere, Category = "Traffic") float SkyHeight = 48.f;

	// the switches outlive the actor (map changes), like the vehicle choice
	static bool GGround;
	static bool GSky;

	// --- self-driving for the player's car (D-pad right / Z): it drives the lanes to a destination (a charger, else
	// somewhere across town), turns from the right lane, stops on red and yellow and at stop signs, takes junctions by
	// the same rules as the traffic (reserves its crossing, gives way), and keeps its distance from the traffic, like
	// the city's own cars. The car turns the look-ahead point and the target speed into steering, throttle and brake
	// (ASkysterCar::FsdControl).
	struct FFsdStep
	{
		FVector2D Look = FVector2D::ZeroVector;   // plan metres
		double VTarget = 0;                        // m/s
		FString Hint;                              // "Turn left onto Michigan Avenue · 120 m"
		double DistLeft = 0;                       // m to the destination
		bool bArrived = false;
	};
	/** Snap onto the lane under the car and plan a route; false (with the reason) when there's no mapped street. */
	bool FsdStart(const FVector& PosUE, double YawDeg, const TArray<FVector>& GoalsUE, FString& OutWhy);
	void FsdStop() { Fsd.bOn = false; Fsd.bCommit = false; Fsd.ReqT = -1; }
	bool FsdOn() const { return Fsd.bOn; }
	/** One step: false when the car has left the route (the driver should take over). */
	bool FsdStep(const FVector& PosUE, double YawDeg, double Speed, double Dt, FFsdStep& Out);
	/** The route still ahead, plan metres (for the mini map). */
	void FsdRoute(TArray<FVector2D>& Out) const;
	FString FsdDestination() const { return Fsd.DestName; }

protected:
	virtual void BeginPlay() override;

private:
	typedef TArray<FVector2D, TInlineAllocator<16>> FPath;

	struct FLink
	{
		int32 A = 0, B = 0, Ctrl = 0, Unit = -1, Group = 0;
		double V = 11, Len = 0;
		double SB = 1;              // stop line, m back from the end (the junction box can reach into an untrimmed link)
		double EX = 0;              // how far the junction box reaches into the link from its start, m
		bool bHw = false;
		TArray<FVector2D> P;
		TArray<double> S;
		TArray<double> O;           // lane offsets to the right of the centreline, inner first (m)
		TArray<int32> Next;         // links leaving the far end (no U-turns unless it's a dead end)
		FVector2D Mid = FVector2D::ZeroVector;
		FString Name;
	};
	struct FFsdState
	{
		bool bOn = false, bTurn = false, bServed = false, bArrived = false, bCommit = false;
		int32 Link = -1, Lane = 0, FromLane = 0, Next = -1, NextLane = 0, RouteI = 0, GoalLink = -1;
		double S = 0, U = 0, Wait = 0, TurnLen = 1, GoalS = 0, ArriveT = 0, CommitT = 0, YieldT = 0, ReqT = -1;
		FVector2D P0 = FVector2D::ZeroVector, P1 = FVector2D::ZeroVector, P2 = FVector2D::ZeroVector;
		TArray<int32> Route;
		TArray<FVector2D> Goals;
		FString DestName;
	};
	FFsdState Fsd;
	bool FsdPlan();
	void FsdTurnInto(int32 NextLink);
	void FsdMovePath(FPath& Out) const;
	int32 TurnOf(int32 From, int32 To) const;    // -1 left, 0 straight, 1 right
	double Project(const FLink& L, const FVector2D& P, double& OutLat) const;
	double FsdLaneOff(const FLink& L, int32 Lane) const { return L.O[FMath::Clamp(Lane, 0, L.O.Num() - 1)]; }

	struct FCar
	{
		int32 Link = -1, Lane = 0, Next = -1, NextLane = 0, InLane = 0, Model = 0, Comp = -1, Prev = -1;
		double S = 0, V = 0, Want = 1, TurnLen = 1, QLen = 1, Wait = 0, Len = 4.7, W = 2.0, Spin = 0, Bank = 0;
		double LatK = 1, Lat = 0;                    // lane change progress (NextLane -> Lane), lateral offset now
		double CommitT = 0, ReqT = -1, YieldT = 0, Stuck = 0, Hold = 0;
		double Crash = 0, Shove = 0, ShoveV = 0, YawOff = 0, YawV = 0, Pin = 0, Fade = 0;
		bool bServed = false, bSky = false, bWheels = false, bCommit = false, bInOcc = false, bPlaced = false, bBoxOn = true;
		uint8 Why = 0;
		FVector2D P0 = FVector2D::ZeroVector, P1 = FVector2D::ZeroVector, P2 = FVector2D::ZeroVector;   // the crossing being driven (S < 0)
		FVector2D Q0 = FVector2D::ZeroVector, Q1 = FVector2D::ZeroVector, Q2 = FVector2D::ZeroVector;   // the crossing planned at this link's end
		FVector2D Pos = FVector2D::ZeroVector, Dir = FVector2D(0, 1);                                    // the body now, plan metres
	};
	// a junction's occupants: cars crossing it (or still in its box) and cars that reserved or requested it
	struct FOcc
	{
		int32 Car = -1;             // index in Cars, INDEX_NONE for the player's self-driving
		int32 From = -1, FromLane = -1, To = -1, ToLane = -1;
		double W = 2, Req = -1;
		bool bInside = false;
		FPath Path;
	};
	// the player's car as an obstacle
	struct FBody
	{
		bool bOn = false, bSky = false, bHadPrev = false;
		FVector2D P = FVector2D::ZeroVector, D = FVector2D(0, 1), Vel = FVector2D::ZeroVector, Prev = FVector2D::ZeroVector;
		double Len = 4.7, W = 1.99, Speed = 0;   // Speed: what its speedometer says, m/s
	};

	bool Load();
	void SanitizeLanes();
	void BoxExtents();
	void BuildSigns();
	void Populate(bool bSkyLayer, int32 Count);
	void Clear(bool bSkyLayer);
	bool Place(FCar& C, double MinR, double MaxR);
	bool FreeSpot(const FCar& C, const FVector2D& P, const FVector2D& D) const;
	void Enter(FCar& C, int32 Link, int32 FromLane, double S);
	void PlanNext(FCar& C);
	void PlanCurve(FCar& C) const;
	void MakeCurve(const FCar& C, const FLink& L, double LatEnd, const FLink& N, int32 InLane, FVector2D& OutP0, FVector2D& OutP1, FVector2D& OutP2, double& OutLen) const;
	void Step(int32 Ci, double Dt, double T);
	void PoseXY(const FCar& C, FVector2D& OutP, FVector2D& OutD) const;
	void Pose(FCar& C, const FVector& Cam);
	int32 Signal(int32 Unit, int32 Group, double T) const;
	FVector2D At(const FLink& L, double S, double Off, FVector2D* Dir = nullptr) const;
	double LaneOff(const FCar& C, const FLink& L, int32 Lane) const;
	double LatNow(const FCar& C) const;
	UStaticMeshComponent* MakePart(UStaticMesh* Mesh, USceneComponent* Parent, float Cull);

	// junctions
	bool Inside(const FCar& C) const;
	void MovePath(const FCar& C, FPath& Out) const;
	void InsidePath(const FCar& C, FPath& Out) const;
	int32 PrioOf(int32 LinkI, int32 NextI) const;
	bool ExitRoom(int32 Self, bool bSkyLayer, int32 NextI, int32 InLane, double W, double Len) const;
	uint8 CanGo(int32 Self, bool bSkyLayer, int32 LinkI, int32 Lane, int32 NextI, int32 InLane, double W, double Len, double V,
		double YieldT, double ReqT, double QLen, const FPath& Mine, double T);
	bool OccEntry(int32 Ci, int32& OutKey, FOcc& Out);
	void RebuildOcc(double T);
	void UpdateOcc(int32 Ci, int32 OldLink);
	void AddFsdOcc();

	// bodies
	static int64 GKey(const FVector2D& P, bool bSkyLayer);
	void BuildGrid();
	void GridMove(int32 Ci, const FVector2D& OldPos);
	uint8 OverlapAny(int32 Ci, const FVector2D& NP, const FVector2D& ND, const FVector2D& OP, const FVector2D& OD) const;
	double RayAhead(const FVector2D& P, const FVector2D& D, double W, double Len, double Range, bool bSkyLayer, int32 Self, bool bWithPlayer, double& OutV, double& OutDot, bool& bOutPlayer) const;
	bool Visible(const FCar& C) const;
	void Unstick(int32 Ci, double Dt);
	void UpdatePlayer(double Dt);
	void PlayerContact(double Dt);

	TArray<FLink> Links;
	TMap<int32, FVector2D> Nodes;
	TMap<int32, TPair<int32, double>> Units;   // unit -> (groups, phase)
	TMap<int32, TArray<int32>> NodeIn, NodeOut; // links arriving at / leaving each node
	double GroupTime = 22.0;
	TArray<FCar> Cars;
	TArray<TArray<int32>> OnLink;               // cars on each link (rebuilt every tick)
	TArray<int32> Touched;
	TMap<int32, TArray<FOcc>> Occ;              // node * 2 + sky layer -> occupants
	TMap<int64, TArray<int32>> Grid;            // 16 m cells -> cars
	FBody Player;
	FVector2D CamFwd = FVector2D(0, 1);
	bool bGround = true, bSky = false, bPending = true;
	FVector Focus = FVector::ZeroVector;
	FRandomStream Rand{ 2026 };
	int32 LanesDropped = 0;
	int32 StatCommits = 0, StatUncommits = 0, StatRequests = 0, StatHolds = 0, StatRelocated = 0, StatFaded = 0, StatCrashes = 0, StatPinned = 0, StatRejected = 0;

	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Bodies;
	UPROPERTY() TArray<TObjectPtr<UBoxComponent>> Boxes;      // the hit boxes, by the same index as Bodies
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> BodyMeshes;
	UPROPERTY() TArray<TObjectPtr<UStaticMesh>> WheelMeshes;  // per model, per wheel (models x 6)
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> SkyHeads;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> SkyStops;
};
