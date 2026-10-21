// The upgrade path (js/progress.js) and the fuel add-ons on board (js/addons.js), saved between
// sessions in the "Skyster" save slot.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "SkysterTypes.h"
#include "SkysterProgress.generated.h"

class ASkysterCar;

UCLASS()
class SKYCITY_API USkysterSave : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY() int32 Level = 0;
	UPROPERTY() int32 Earned = 0;
	UPROPERTY() TArray<FString> Done;
	UPROPERTY() TArray<FString> Addons;
};

struct FSkyProgress
{
	int32 Level = 0;   // the car as it is now (0-based)
	int32 Earned = 0;  // highest level unlocked by challenges
	TSet<FString> Done;
	TMap<FString, double> Best;
	TSet<FString> Owned; // fuel add-ons on board
	double RunDriftT = 0, RunWallT = 0;
	TMap<FString, double> LockToastT;
	int32 PendingLevel = -1;
	double PendingT = 0;

	void Load();
	void Save() const;
	const FSkyLevel& Current() const { return Skyster::Levels[Level]; }
	void SetLevel(int32 I, ASkysterCar& Car);
	void Reset(ASkysterCar& Car);
	void Update(double Dt, ASkysterCar& Car);
	bool Met(const FSkyGoal& G) const;
	double FuelMult() const;
	FString BestAddon() const;
	bool Grant(const FString& Id);
};
