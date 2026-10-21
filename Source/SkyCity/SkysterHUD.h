// The Skyster HUD on the game's canvas (Skyster 4.0 layout): speed, tank in psi, jump pips, hull,
// 0-60, the level's challenges, toasts, the combo, markers to the fuel add-ons still out there,
// and the Garage (Menu) for testing levels and switching maps.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SkysterHUD.generated.h"

class UFont;
class ASkysterCar;

UCLASS()
class SKYCITY_API ASkysterHUD : public AHUD
{
	GENERATED_BODY()

public:
	ASkysterHUD();
	virtual void DrawHUD() override;

private:
	void Text(const FString& T, float X, float Y, float Size, const FLinearColor& C, bool bRight = false, bool bCentre = false);
	float TextW(const FString& T, float Size);
	void DrawPanel(const ASkysterCar& Car, float S);
	void DrawToasts(const ASkysterCar& Car, float S);
	void DrawCombo(const ASkysterCar& Car, float S);
	void DrawMarkers(const ASkysterCar& Car, float S);
	void DrawGarage(const ASkysterCar& Car, float S);
	void DrawMiniMap(const ASkysterCar& Car, float S);
	void Tri(const FVector2D& A, const FVector2D& B, const FVector2D& C, const FLinearColor& Col);

	// the mini map (a navigation map in the style of an EV's centre screen): Content/SkyCity/Data/minimap.json says which
	// image (Scripts/hud/make_minimaps.py) covers this map and where; M_MiniMap turns and zooms it around the car
	UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> MiniMID;
	bool bMiniTried = false;
	double MiniX0 = 0, MiniY0 = 0, MiniSize = 1, MiniMeters = 340;

	UPROPERTY()
	TObjectPtr<UFont> Font;
};
