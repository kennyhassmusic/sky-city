// Things in the map the car picks up or parks on, found at BeginPlay by actor tag (placed by
// Scripts/unreal/place_pickups.py, so the maps need no special actor classes):
//   SC_PadSmall / SC_PadBig  pressure points (js/world.js): instanced "Pool" (ground disc), "Ring", "Core"
//   SC_Chargers              wireless fast-charger bays: instanced "Bay" (custom data 0 = busy) and "Cross" (site markers)
//   SC_Addon                 fuel add-on pickups: a static mesh per spot, component tag = add-on id
//   SC_Lineup                the McGregor fleet deck: flying over it is the "Over the line-up" move
// Everything here is in Unreal world space (cm).
#pragma once

#include "CoreMinimal.h"

class UInstancedStaticMeshComponent;
class USceneComponent;
class UWorld;

class FSkyPickups
{
public:
	struct FPad
	{
		FVector P;          // ground point
		double Yaw = 0;     // road heading (deg), used for respawns
		bool bBig = false, bOn = true;
		double T = 0;       // seconds until it's back
		int32 Index = 0;
		int32 Set = 0;
	};
	struct FPadSet
	{
		TWeakObjectPtr<UInstancedStaticMeshComponent> Pool, Ring, Core;
		bool bBig = false;
	};
	struct FBay
	{
		FVector P;
		FVector Along;      // unit, along the row
		int32 Index = 0;
		double LastBusy = -9;
	};
	struct FAddonSpot
	{
		FString Id;
		FVector P;
		TWeakObjectPtr<USceneComponent> Comp;
	};

	void Gather(UWorld* World);
	/** 0 nothing, 1 small pressure point, 2 big. */
	int32 CollectPad(const FVector& PosUE);
	/** Parked on a fast charger bay? Marks the site busy for the visuals. */
	bool ChargerAt(const FVector& PosUE, double Now);
	/** An add-on not yet on board within reach, or empty. */
	FString CollectAddon(const FVector& PosUE, const TSet<FString>& Owned);
	void HideOwned(const TSet<FString>& Owned);
	/** Over the fleet deck (between 1 and 18 m above it)? */
	bool OverLineup(const FVector& PosUE) const;
	void Update(double Dt, double Now, const FVector& CarUE);
	bool NearestRoad(const FVector& PosUE, FVector& OutUE, double& OutYawDeg) const;

	TArray<FPad> Pads;
	TArray<FPadSet> PadSets;
	TArray<FBay> Bays;
	TWeakObjectPtr<UInstancedStaticMeshComponent> BayComp, CrossComp;
	TArray<FVector> Crosses;
	TArray<FAddonSpot> AddonSpots;
	TArray<FBox> Lineups;

private:
	TMap<FIntPoint, TArray<int32>> Grid;
	static FIntPoint Cell(const FVector& P) { return FIntPoint(FMath::FloorToInt(P.X / 5000.0), FMath::FloorToInt(P.Y / 5000.0)); }
	void PlacePad(const FPad& Pad, double Now, bool bAnimate);
	TSet<UInstancedStaticMeshComponent*> Dirty;
};
