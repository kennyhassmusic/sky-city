// Kenny's McGregor line-up (Model 3, Model Y, Cybertruck, Cybercab, Semi) as vehicles: the player can drive any of them
// (ASkysterCar::SetVehicle) and the city's traffic is made of them (ASkysterTraffic).
#pragma once

#include "CoreMinimal.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"

// Kenny's McGregor line-up as cars you can drive (Scripts/vehicles/blender_split_lineup.py -> SourceArt/Vehicles/parts.json,
// imported by Scripts/vehicles/lineup_ue.py): Unreal cm in the car frame, ground at z = 0, axles centred on the physics
// origin by X. Licences: SourceArt/Vehicles stays out of public repos; the Semi is an editorial placeholder.
namespace SkyFleet
{
	struct FWheel { const TCHAR* Part; FVector P; double R; bool bSteer; };
	// Label: what the HUD calls it; generic on purpose (no carmaker names or badges in the game)
	struct FCar { const TCHAR* Name; const TCHAR* Label; FVector Size; double OffX; int32 NumWheels; FWheel W[6]; };
	inline const FCar Cars[] = {
	{ TEXT("Model3"), TEXT("Sedan"), FVector(471.9, 208.8, 131.5), -4.4, 4, { { TEXT("Wheel_FL"), FVector(143.8, -79.8, 33.2), 0.332, true }, { TEXT("Wheel_FR"), FVector(143.8, 79.8, 33.2), 0.332, true }, { TEXT("Wheel_RL"), FVector(-143.8, -79.8, 33.2), 0.332, false }, { TEXT("Wheel_RR"), FVector(-143.8, 79.8, 33.2), 0.332, false } } },
	{ TEXT("ModelY"), TEXT("Crossover"), FVector(478.9, 212.4, 148.6), -3.3, 4, { { TEXT("Wheel_FL"), FVector(145.1, -80.5, 36.9), 0.369, true }, { TEXT("Wheel_FR"), FVector(145.1, 80.5, 36.9), 0.369, true }, { TEXT("Wheel_RL"), FVector(-145.1, -80.5, 36.9), 0.369, false }, { TEXT("Wheel_RR"), FVector(-145.1, 80.5, 36.9), 0.369, false } } },
	{ TEXT("Cybertruck"), TEXT("Pickup"), FVector(598.0, 228.0, 190.0), -15.0, 4, { { TEXT("Wheel_FL"), FVector(195.0, -99.6, 46.1), 0.460, true }, { TEXT("Wheel_FR"), FVector(195.0, 99.6, 46.1), 0.460, true }, { TEXT("Wheel_RL"), FVector(-195.0, -99.6, 46.1), 0.460, false }, { TEXT("Wheel_RR"), FVector(-195.0, 99.6, 46.1), 0.460, false } } },
	{ TEXT("Robotaxi"), TEXT("Robotaxi"), FVector(433.9, 175.4, 124.5), -2.9, 4, { { TEXT("Wheel_FL"), FVector(134.0, -73.8, 36.5), 0.365, true }, { TEXT("Wheel_FR"), FVector(134.0, 73.8, 36.5), 0.365, true }, { TEXT("Wheel_RL"), FVector(-134.0, -73.8, 36.5), 0.365, false }, { TEXT("Wheel_RR"), FVector(-134.0, 73.8, 36.5), 0.365, false } } },
	{ TEXT("Semi"), TEXT("Semi truck"), FVector(734.0, 277.5, 373.2), -44.6, 6, { { TEXT("Wheel_A1L"), FVector(180.7, -111.5, 51.9), 0.519, true }, { TEXT("Wheel_A1R"), FVector(180.7, 111.3, 51.9), 0.519, true }, { TEXT("Wheel_A2L"), FVector(-125.6, -101.7, 51.9), 0.519, false }, { TEXT("Wheel_A2R"), FVector(-125.6, 101.7, 51.9), 0.519, false }, { TEXT("Wheel_A3L"), FVector(-235.8, -101.7, 51.9), 0.519, false }, { TEXT("Wheel_A3R"), FVector(-235.8, 101.7, 51.9), 0.519, false } } },
	};
	constexpr int32 Num = UE_ARRAY_COUNT(Cars) + 1;           // + the Roadster at 0
	inline const FVector ROADSTER(470.0, 199.0, 124.0);
	// Blocky stand-ins with the same size, wheels, glass and lamps (Scripts/vehicles/blender_placeholder_cars.py ->
	// /Game/Vehicles/Placeholder) stand in for a car that's listed in DefaultGame.ini [SkyFleet] PlaceholderCars (the
	// public build: models not licensed for distribution) or whose licensed model isn't in the project at all (the
	// open-source repo ships without them).
	inline bool UsePlaceholder(const TCHAR* Car)
	{
		static const TArray<FString> Listed = [] { TArray<FString> A; if (GConfig) GConfig->GetArray(TEXT("SkyFleet"), TEXT("PlaceholderCars"), A, GGameIni); return A; }();
		if (Listed.Contains(FString(Car))) return true;
		return !FPackageName::DoesPackageExist(FString::Printf(TEXT("/Game/Vehicles/Tesla/%s/TV_%s_Body/StaticMeshes/TV_%s_Body"), Car, Car, Car));
	}
	inline FString MeshPath(const TCHAR* Car, const TCHAR* Part)
	{
		const TCHAR* Root = UsePlaceholder(Car) ? TEXT("/Game/Vehicles/Placeholder") : TEXT("/Game/Vehicles/Tesla");
		return FString::Printf(TEXT("%s/%s/TV_%s_%s/StaticMeshes/TV_%s_%s.TV_%s_%s"), Root, Car, Car, Part, Car, Part, Car, Part);
	}
	// the choice outlives the pawn, so it rides along through the Garage's map changes
	inline int32 GChoice = 0;
}

