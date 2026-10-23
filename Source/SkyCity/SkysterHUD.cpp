#include "SkysterHUD.h"
#include "SkyCourse.h"
#include "SkysterTraffic.h"

#include "Camera/PlayerCameraManager.h"
#include "CanvasItem.h"
#include "Dom/JsonObject.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TextureResource.h"
#include "Engine/Canvas.h"
#include "Engine/Font.h"
#include "Kismet/GameplayStatics.h"
#include "SkysterCar.h"
#include "UObject/ConstructorHelpers.h"

static const FLinearColor Ink(1.f, 1.f, 1.f, 0.95f);
static const FLinearColor Dim(0.75f, 0.85f, 1.f, 0.8f);
static const FLinearColor Faint(0.75f, 0.85f, 1.f, 0.45f);
static const FLinearColor Back(0.02f, 0.03f, 0.05f, 0.55f);
static const FLinearColor Green(0.35f, 1.f, 0.55f, 0.95f);
static const FLinearColor Gold(1.f, 0.82f, 0.35f, 0.95f);

ASkysterHUD::ASkysterHUD()
{
	static ConstructorHelpers::FObjectFinder<UFont> Roboto(TEXT("/Engine/EngineFonts/Roboto.Roboto"));
	if (Roboto.Succeeded()) Font = Roboto.Object;
}

void ASkysterHUD::Text(const FString& T, float X, float Y, float Size, const FLinearColor& C, bool bRight, bool bCentre)
{
	float W = 0, H = 0;
	if (bRight || bCentre) GetTextSize(T, W, H, Font, Size);
	DrawText(T, C, bRight ? X - W : bCentre ? X - W * 0.5f : X, Y, Font, Size);
}

float ASkysterHUD::TextW(const FString& T, float Size)
{
	float W = 0, H = 0;
	GetTextSize(T, W, H, Font, Size);
	return W;
}

void ASkysterHUD::DrawHUD()
{
	Super::DrawHUD();
	// the Course Builder draws its own screens (build mode, the race) under the car's HUD
	if (Canvas)
	{
		if (ASkyCourseMode* Mode = ASkyCourseMode::Get(GetWorld())) Mode->DrawHud(this, Canvas, Canvas->ClipY / 1080.f);
	}
	const ASkysterCar* Car = Cast<ASkysterCar>(GetOwningPawn());
	if (!Car || !Canvas || !Font) return;
	const float S = Canvas->ClipY / 1080.f; // sized for 1080p, scaled to the window

	// hurt flash
	if (Car->HurtFlash > 0.01) DrawRect(FLinearColor(0.8f, 0.05f, 0.02f, (float)Car->HurtFlash * 0.22f), 0, 0, Canvas->ClipX, Canvas->ClipY);

	// --- bottom right: speed, tank, mode ---
	const float Right = Canvas->ClipX - 56.f * S;
	const float Bottom = Canvas->ClipY - 52.f * S;
	const float BarW = 300.f * S, BarH = 14.f * S;
	const bool bBoostOK = Car->Caps.bBoost;
	const float Tank = FMath::Clamp((float)Car->BoostTank / 100.f, 0.f, 1.f);
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.45f), Right - BarW, Bottom - BarH, BarW, BarH);
	const FLinearColor TankCol = !bBoostOK ? FLinearColor(0.4f, 0.5f, 0.6f, 0.5f) : Car->bBoosting ? FLinearColor(1.f, 0.55f, 0.1f, 0.95f) : FLinearColor(0.2f, 0.85f, 1.f, 0.9f);
	DrawRect(TankCol, Right - BarW, Bottom - BarH, BarW * Tank, BarH);
	const FString Mph = FString::FromInt(FMath::RoundToInt(Car->GetSpeedMph()));
	const float Big = 3.2f * S, Small = 1.1f * S, Tiny = 0.85f * S;
	const float UW = TextW(TEXT("MPH"), Small);
	const float Base = Bottom - BarH - 10.f * S;
	Text(TEXT("MPH"), Right - UW, Base - 22.f * S, Small, Dim);
	Text(Mph, Right - UW - 10.f * S, Base - 70.f * S, Big, Ink, true);
	const FString Mode = Car->GetMode();
	if (Mode != TEXT("DRIVE")) Text(Mode, Right - BarW, Base - 22.f * S, Small, Mode == TEXT("CHARGING") ? Green : Dim);
	Text(bBoostOK ? FString::Printf(TEXT("TANK  %s psi"), *FText::AsNumber(FMath::RoundToInt(Car->BoostTank * 100)).ToString()) : FString(TEXT("TANK  boost unlocks at level 3")),
		Right - BarW, Bottom + 4.f * S, Tiny, bBoostOK ? Dim : Faint);
	if (Car->FuelMult > 1) Text(FString::Printf(TEXT("fuel x%d"), (int32)Car->FuelMult), Right, Bottom + 4.f * S, Tiny, Gold, true);

	// --- bottom left: hull, jump pips, 0-60 ---
	const float L0 = 56.f * S;
	const double Hp = Car->Health;
	const FLinearColor HullCol = Car->bCharging ? Green : Hp > 55 ? FLinearColor(0.85f, 0.95f, 1.f, 0.9f) : Hp > 30 ? FLinearColor(1.f, 0.75f, 0.2f, 0.95f) : FLinearColor(1.f, 0.25f, 0.15f, 0.95f);
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.45f), L0, Bottom - BarH, BarW, BarH);
	DrawRect(HullCol, L0, Bottom - BarH, BarW * FMath::Clamp((float)Hp / 100.f, 0.f, 1.f), BarH);
	const TCHAR* State = Hp > 80 ? TEXT("Nominal") : Hp > 55 ? TEXT("Scraped") : Hp > 30 ? TEXT("Damaged") : Hp > 15 ? TEXT("Critical") : Hp > 0 ? TEXT("Fire") : TEXT("Totaled");
	FString HullTxt = FString::Printf(TEXT("HULL  %d%%  %s"), FMath::RoundToInt(Hp), State);
	if (Car->bCharging) HullTxt = FString::Printf(TEXT("HULL  %d%%  Fast charging +%.1f%%/s"), FMath::RoundToInt(Hp), Hp < 80 ? 80.0 / 15 : 20.0 / 30);
	Text(HullTxt, L0, Bottom + 4.f * S, Tiny, Car->bCharging ? Green : Dim);
	// jump pips: first jump available on a surface, second while the window is open (dim while locked)
	const bool bJ1 = Car->bGrounded;
	const bool bJ2 = Car->bGrounded || Car->Jump.bCanDouble;
	for (int32 i = 0; i < 2; ++i)
	{
		const bool bHave = i == 0 ? bJ1 : bJ2;
		const bool bLock = i == 1 && !Car->Caps.bDoubleJump;
		const FLinearColor C = bLock ? FLinearColor(0.4f, 0.45f, 0.5f, 0.35f) : bHave ? FLinearColor(0.3f, 0.9f, 1.f, 0.95f) : FLinearColor(0.3f, 0.4f, 0.5f, 0.6f);
		DrawRect(C, L0 + i * 22.f * S, Bottom - BarH - 26.f * S, 14.f * S, 14.f * S);
	}
	if (Car->LastSixty > 0)
	{
		Text(FString::Printf(TEXT("0-60  %.2f s   best %.2f s"), Car->LastSixty, Car->BestSixty), L0 + 56.f * S, Bottom - BarH - 30.f * S, Tiny, Dim);
	}

	DrawPanel(*Car, S);
	DrawMiniMap(*Car, S);
	DrawMarkers(*Car, S);
	DrawCombo(*Car, S);
	DrawToasts(*Car, S);
	if (!Car->bAlive)
	{
		DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), 0, 0, Canvas->ClipX, Canvas->ClipY);
		Text(TEXT("WRECKED"), Canvas->ClipX * 0.5f, Canvas->ClipY * 0.42f, 2.6f * S, FLinearColor(1.f, 0.35f, 0.2f, 1.f), false, true);
		Text(TEXT("Thrusters offline · respawning"), Canvas->ClipX * 0.5f, Canvas->ClipY * 0.42f + 70.f * S, 1.2f * S, Dim, false, true);
	}
	if (Car->bGarage) DrawGarage(*Car, S);
}

// Top right: the level and its three challenges (js/progress.js render).
void ASkysterHUD::DrawPanel(const ASkysterCar& Car, float S)
{
	const FSkyProgress& P = Car.Progress;
	const FSkyLevel& L = P.Current();
	const float W = 430.f * S, X = Canvas->ClipX - W - 40.f * S;
	float Y = 40.f * S;
	const float Rows = 3.f + L.NumGoals * 1.6f;
	DrawRect(Back, X - 14.f * S, Y - 10.f * S, W + 28.f * S, (Rows * 30.f + 20.f) * S);
	Text(FString::Printf(TEXT("Level %d · %s"), P.Level + 1, L.Name), X, Y, 1.25f * S, Ink);
	Y += 34.f * S;
	Text(L.Blurb, X, Y, 0.8f * S, Dim);
	Y += 30.f * S;
	for (int32 i = 0; i < L.NumGoals; ++i)
	{
		const FSkyGoal& G = L.Goals[i];
		const bool bDone = P.Done.Contains(G.Id);
		DrawRect(bDone ? Green : FLinearColor(1, 1, 1, 0.25f), X, Y + 4.f * S, 14.f * S, 14.f * S);
		if (!bDone) DrawRect(FLinearColor(0.02f, 0.03f, 0.05f, 0.9f), X + 2.f * S, Y + 6.f * S, 10.f * S, 10.f * S);
		Text(G.Text, X + 24.f * S, Y, 0.85f * S, bDone ? Faint : Ink);
		if (!bDone)
		{
			const FString Tgt = FMath::IsNearlyEqual(G.Target, FMath::RoundToDouble(G.Target)) ? FString::FromInt(FMath::RoundToInt(G.Target)) : FString::Printf(TEXT("%.1f"), G.Target);
			FString Goal = FString::Printf(TEXT("goal %s%s%s%s"), G.bMin ? TEXT("under ") : TEXT(""), *Tgt, FString(G.Unit).IsEmpty() ? TEXT("") : TEXT(" "), G.Unit);
			if (const double* B = P.Best.Find(G.Stat))
			{
				if (G.Target > 1)
				{
					const bool bInt = FString(G.Unit) == TEXT("mph") || FString(G.Unit) == TEXT("m");
					Goal += bInt ? FString::Printf(TEXT(" · best %d %s"), FMath::RoundToInt(*B), G.Unit) : FString::Printf(TEXT(" · best %.1f %s"), *B, G.Unit);
				}
			}
			Text(Goal, X + 24.f * S, Y + 22.f * S, 0.7f * S, Dim);
		}
		Y += 48.f * S;
	}
	const FString Next = P.Level + 1 < Skyster::NumLevels
		? FString::Printf(TEXT("Next: %s · %s"), Skyster::Levels[P.Level + 1].Name, Skyster::Levels[P.Level + 1].Blurb)
		: FString(TEXT("Every system unlocked. Find the three fuel add-ons to fly longer."));
	Text(Next, X, Y, 0.72f * S, Faint);
}

// Top centre: the latest toasts, fading after four seconds.
void ASkysterHUD::DrawToasts(const ASkysterCar& Car, float S)
{
	float Y = 70.f * S;
	const float Cx = Canvas->ClipX * 0.42f;
	for (int32 i = Car.Toasts.Num() - 1; i >= 0 && i >= Car.Toasts.Num() - 3; --i)
	{
		const FSkyToast& T = Car.Toasts[i];
		const double Age = Car.SimTime - T.Born;
		if (Age > 4.5 || Age < 0) continue;
		const float A = (float)FMath::Clamp(4.5 - Age, 0.0, 1.0);
		const float W = FMath::Max(TextW(T.Title, 1.15f * S), TextW(T.Sub, 0.8f * S)) + 40.f * S;
		DrawRect(FLinearColor(0.02f, 0.03f, 0.05f, 0.6f * A), Cx - W * 0.5f, Y, W, (T.Sub.IsEmpty() ? 40.f : 66.f) * S);
		Text(T.Title, Cx, Y + 6.f * S, 1.15f * S, FLinearColor(1, 1, 1, 0.95f * A), false, true);
		if (!T.Sub.IsEmpty()) Text(T.Sub, Cx, Y + 38.f * S, 0.8f * S, FLinearColor(0.75f, 0.85f, 1.f, 0.85f * A), false, true);
		Y += (T.Sub.IsEmpty() ? 48.f : 74.f) * S;
	}
}

// The running combo: multiplier, score and the moves so far.
void ASkysterHUD::DrawCombo(const ASkysterCar& Car, float S)
{
	if (!Car.Cb.bActive) return;
	const float Cx = Canvas->ClipX * 0.5f, Y = Canvas->ClipY * 0.68f;
	Text(FString::Printf(TEXT("x%d"), Car.Cb.Mult), Cx, Y, 2.0f * S, Gold, false, true);
	Text(FText::AsNumber(FMath::RoundToInt(Car.Cb.Score * Car.Cb.Mult)).ToString(), Cx, Y + 52.f * S, 1.1f * S, Ink, false, true);
	Text(Skyster::MoveList(Car.Cb.Moves), Cx, Y + 84.f * S, 0.85f * S, Dim, false, true);
}

// Markers to the fuel add-ons not yet on board: name, distance and height.
void ASkysterHUD::DrawMarkers(const ASkysterCar& Car, float S)
{
	APlayerController* PC = GetOwningPlayerController();
	if (!PC || !PC->PlayerCameraManager) return;
	const FVector CarUE = Car.GetActorLocation();
	for (const FSkyPickups::FAddonSpot& Spot : Car.World.AddonSpots)
	{
		if (Car.Progress.Owned.Contains(Spot.Id)) continue;
		const FVector Mark = Spot.P + FVector(0, 0, 400);
		FVector2D Sc;
		if (!PC->ProjectWorldLocationToScreen(Mark, Sc, true)) continue;
		const FVector CamFwd = PC->PlayerCameraManager->GetCameraRotation().Vector();
		if (FVector::DotProduct(Mark - PC->PlayerCameraManager->GetCameraLocation(), CamFwd) < 0) continue;
		const float X = FMath::Clamp((float)Sc.X, 60.f * S, Canvas->ClipX - 60.f * S), Y = FMath::Clamp((float)Sc.Y, 60.f * S, Canvas->ClipY - 120.f * S);
		FString Name = Spot.Id;
		FLinearColor Col = Gold;
		for (const Skyster::FAddon& A : Skyster::Addons)
		{
			if (Spot.Id == A.Id) { Name = A.Name; Col = FLinearColor(FMath::Min(A.Col.R, 1.f), FMath::Min(A.Col.G, 1.f), FMath::Min(A.Col.B, 1.f), 0.95f); }
		}
		const double Dist = FVector::Dist2D(Spot.P, CarUE) / 100.0;
		const double Hgt = (Spot.P.Z - CarUE.Z) / 100.0;
		DrawRect(Col, X - 5.f * S, Y - 5.f * S, 10.f * S, 10.f * S);
		Text(Name, X, Y + 8.f * S, 0.8f * S, Col, false, true);
		Text(FString::Printf(TEXT("%d m%s"), FMath::RoundToInt(Dist), FMath::Abs(Hgt) > 8 ? *FString::Printf(TEXT(" · %+d m"), FMath::RoundToInt(Hgt)) : TEXT("")), X, Y + 32.f * S, 0.7f * S, Dim, false, true);
	}
}

// The Garage: car level for testing, challenges reset, map switch, add-ons on board, controls.
void ASkysterHUD::DrawGarage(const ASkysterCar& Car, float S)
{
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.55f), 0, 0, Canvas->ClipX, Canvas->ClipY);
	const float W = 900.f * S, X = (Canvas->ClipX - W) * 0.5f;
	float Y = Canvas->ClipY * 0.16f;
	DrawRect(Back, X - 30.f * S, Y - 24.f * S, W + 60.f * S, 780.f * S);
	Text(TEXT("GARAGE"), X, Y, 1.8f * S, Ink);
	Text(FString::Printf(TEXT("map: %s"), SkyCourse::IsBuildMode(Car.GetWorld()) ? TEXT("Course Builder") : *UGameplayStatics::GetCurrentLevelName(&Car, true)), X + W, Y + 14.f * S, 0.85f * S, Dim, true);
	Y += 64.f * S;
	for (int32 i = 0; i < Skyster::NumLevels; ++i)
	{
		const FSkyLevel& L = Skyster::Levels[i];
		const bool bHere = i == Car.Progress.Level;
		const bool bEarned = i <= Car.Progress.Earned;
		if (bHere) DrawRect(FLinearColor(0.2f, 0.6f, 1.f, 0.25f), X - 10.f * S, Y - 4.f * S, W + 20.f * S, 40.f * S);
		Text(FString::Printf(TEXT("%d · %s"), i + 1, L.Name), X, Y, 1.0f * S, bHere ? Ink : bEarned ? Dim : Faint);
		Text(L.Blurb, X + 220.f * S, Y + 4.f * S, 0.8f * S, bHere ? Ink : Faint);
		Y += 44.f * S;
	}
	Y += 16.f * S;
	TArray<FString> On;
	for (const Skyster::FAddon& A : Skyster::Addons) if (Car.Progress.Owned.Contains(A.Id)) On.Add(FString::Printf(TEXT("%s x%d"), A.Name, A.Mult));
	Text(On.Num() ? FString::Printf(TEXT("Fuel add-ons on board: %s · flight time x%d"), *FString::Join(On, TEXT(", ")), (int32)Car.FuelMult)
	              : FString(TEXT("Fuel add-ons: none yet (follow the markers: nitrogen, combustion engines, rocket fuel)")), X, Y, 0.85f * S, Gold);
	Y += 46.f * S;
	Text(FString::Printf(TEXT("Vehicle: %s"), *Car.GetVehicleName()), X, Y, 1.0f * S, Ink);
	Text(TEXT("D-pad up / down (or V) to switch"), X + W, Y + 4.f * S, 0.8f * S, Dim, true);
	Y += 40.f * S;
	if (const ASkysterTraffic* Tr = Car.GetTraffic())
	{
		Text(FString::Printf(TEXT("Street traffic: %s   ·   Flying robotaxis: %s"), Tr->IsGround() ? TEXT("on") : TEXT("off"), Tr->IsSky() ? TEXT("on") : TEXT("off")), X, Y, 0.95f * S, Ink);
		Text(TEXT("RB / T: traffic   ·   LB / C: cabs"), X + W, Y + 4.f * S, 0.8f * S, Dim, true);
		Y += 40.f * S;
	}
	if (!SkyCourse::IsBuildMode(Car.GetWorld()))
	{
		Text(TEXT("COURSE BUILDER: press View (R)"), X, Y, 1.0f * S, Gold);
		Text(TEXT("build your own Hot Wheels-style tracks, race AI cars, let Claude build with you"), X + W, Y + 4.f * S, 0.8f * S, Dim, true);
		Y += 40.f * S;
	}
	Text(TEXT("D-pad left / right: car level (testing)   ·   A: handling   ·   X: next map   ·   Y: reset challenges   ·   B / Menu: back"), X, Y, 0.8f * S, Dim);
	Y += 40.f * S;
	Text(TEXT("RT throttle · X brake · LT reverse (air: air brake) · A jump, again + stick = flip · B boost · RB slide · in the air X / RB roll"), X, Y, 0.72f * S, Faint);
	Y += 28.f * S;
	Text(TEXT("LB in the air: flight · D-pad up kickflip · down parallel park · left lights / landing protocol · right self-driving · View respawn"), X, Y, 0.72f * S, Faint);
}

void ASkysterHUD::Tri(const FVector2D& A, const FVector2D& B, const FVector2D& C, const FLinearColor& Col)
{
	FCanvasTriangleItem T(A, B, C, GWhiteTexture);
	T.SetColor(Col);
	T.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(T);
}

// Bottom left, above the hull: the map turns with the car (heading up), the car sits low so more of the road ahead
// shows, and it zooms out with speed and height. On top: the self-driving route in blue, the chargers as red pins
// (an arrow on the rim points to the nearest one when it's off the map), fuel add-ons still out there in gold.
void ASkysterHUD::DrawMiniMap(const ASkysterCar& Car, float S)
{
	if (!bMiniTried)
	{
		bMiniTried = true;
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir() / TEXT("SkyCity/Data/minimap.json")))
			&& FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) && Root.IsValid())
		{
			const TSharedPtr<FJsonObject>* M = nullptr;
			if (Root->TryGetObjectField(UGameplayStatics::GetCurrentLevelName(this, true), M) && M)
			{
				UTexture2D* Tex = LoadObject<UTexture2D>(nullptr, *(*M)->GetStringField(TEXT("tex")));
				UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SkyCity/HUD/M_MiniMap.M_MiniMap"));
				if (Tex && Mat)
				{
					MiniX0 = (*M)->GetNumberField(TEXT("x0"));
					MiniY0 = (*M)->GetNumberField(TEXT("y0"));
					MiniSize = (*M)->GetNumberField(TEXT("size"));
					MiniMID = UMaterialInstanceDynamic::Create(Mat, this);
					MiniMID->SetTextureParameterValue(TEXT("Map"), Tex);
					MiniMID->SetScalarParameterValue(TEXT("Size"), (float)MiniSize);
				}
			}
		}
	}
	if (!MiniMID) return;
	const float W = 380.f * S, H = 250.f * S, X = 56.f * S, Y = Canvas->ClipY - 52.f * S - 14.f * S - 46.f * S - H;
	const float CarY = 0.68f;
	const FVector UE = Car.GetActorLocation();
	const double Px = UE.Y / 100.0, Py = UE.X / 100.0;
	const double Psi = FMath::DegreesToRadians(Car.GetActorRotation().Yaw);
	const double Dt = FMath::Min((double)GetWorld()->GetDeltaSeconds(), 0.1);
	double Want = FMath::GetMappedRangeValueClamped(FVector2D(0.0, 70.0), FVector2D(340.0, 850.0), FMath::Abs(Car.Speed));
	if (!Car.bGrounded) Want = FMath::Max(Want, 700.0);
	MiniMeters = FMath::FInterpTo(MiniMeters, Want, (float)Dt, 1.2f);
	MiniMID->SetScalarParameterValue(TEXT("CenterU"), (float)((Px - MiniX0) / MiniSize));
	MiniMID->SetScalarParameterValue(TEXT("CenterV"), (float)((MiniY0 - Py) / MiniSize));
	MiniMID->SetScalarParameterValue(TEXT("Meters"), (float)MiniMeters);
	MiniMID->SetScalarParameterValue(TEXT("Heading"), (float)Psi);
	MiniMID->SetScalarParameterValue(TEXT("Aspect"), W / H);
	MiniMID->SetScalarParameterValue(TEXT("CarY"), CarY);
	DrawMaterial(MiniMID, X, Y, W, H, 0, 0, 1, 1);

	const double C = FMath::Cos(Psi), Sn = FMath::Sin(Psi), K = H / MiniMeters;
	const auto ToPanel = [&](double Ex, double Ny) -> FVector2D
	{
		const double DE = Ex - Px, DN = Ny - Py;
		return FVector2D(X + W * 0.5 + (DE * C - DN * Sn) * K, Y + H * CarY - (DE * Sn + DN * C) * K);
	};
	const float M = 6.f * S;
	const auto Inside = [&](const FVector2D& P) { return P.X > X + M && P.X < X + W - M && P.Y > Y + M && P.Y < Y + H - M; };
	// the route (clipped to the panel)
	if (Car.bFsd)
	{
		if (const ASkysterTraffic* Tr = Car.GetTraffic())
		{
			TArray<FVector2D> R;
			Tr->FsdRoute(R);
			const FLinearColor Blue(0.24f, 0.45f, 1.f, 0.95f);
			for (int32 i = 0; i + 1 < R.Num(); ++i)
			{
				FVector2D A = ToPanel(R[i].X, R[i].Y), B = ToPanel(R[i + 1].X, R[i + 1].Y);
				// Liang-Barsky against the panel
				double T0 = 0, T1 = 1;
				const FVector2D Dd = B - A;
				const double Pp[4] = { -Dd.X, Dd.X, -Dd.Y, Dd.Y };
				const double Qq[4] = { A.X - (X + M), (X + W - M) - A.X, A.Y - (Y + M), (Y + H - M) - A.Y };
				bool bOut = false;
				for (int32 k = 0; k < 4 && !bOut; ++k)
				{
					if (FMath::Abs(Pp[k]) < 1e-9) { if (Qq[k] < 0) bOut = true; continue; }
					const double R0 = Qq[k] / Pp[k];
					if (Pp[k] < 0) T0 = FMath::Max(T0, R0); else T1 = FMath::Min(T1, R0);
					if (T0 > T1) bOut = true;
				}
				if (bOut) continue;
				DrawLine(A.X + Dd.X * T0, A.Y + Dd.Y * T0, A.X + Dd.X * T1, A.Y + Dd.Y * T1, Blue, 5.f * S);
			}
		}
	}
	// chargers: red pins with a white bolt; the nearest off-map one gets an arrow on the rim
	const FVector2D Mid(X + W * 0.5, Y + H * CarY);
	double NearD = 1e18;
	FVector2D NearDir;
	for (const FVector& Cx : Car.World.Crosses)
	{
		const double Ex = Cx.Y / 100.0, Ny = Cx.X / 100.0;
		const FVector2D P = ToPanel(Ex, Ny);
		if (Inside(P))
		{
			const float R = 8.f * S;
			DrawRect(FLinearColor(0.85f, 0.12f, 0.1f, 0.95f), P.X - R, P.Y - R, 2 * R, 2 * R);
			Tri(FVector2D(P.X + 1.5f * S, P.Y - 6.f * S), FVector2D(P.X - 3.5f * S, P.Y + 1.f * S), FVector2D(P.X + 0.5f * S, P.Y + 1.f * S), FLinearColor::White);
			Tri(FVector2D(P.X - 1.5f * S, P.Y + 6.f * S), FVector2D(P.X + 3.5f * S, P.Y - 1.f * S), FVector2D(P.X - 0.5f * S, P.Y - 1.f * S), FLinearColor::White);
			NearD = -1;                                                   // one's on the map already
		}
		else if (NearD >= 0)
		{
			const double D = FMath::Square(Ex - Px) + FMath::Square(Ny - Py);
			if (D < NearD) { NearD = D; NearDir = (P - Mid).GetSafeNormal(); }
		}
	}
	if (NearD > 0 && NearD < 1e17)
	{
		// walk out from the car to the panel rim
		const double Tx = NearDir.X > 0 ? (X + W - 18.f * S - Mid.X) / NearDir.X : NearDir.X < 0 ? (X + 18.f * S - Mid.X) / NearDir.X : 1e9;
		const double Ty = NearDir.Y > 0 ? (Y + H - 18.f * S - Mid.Y) / NearDir.Y : NearDir.Y < 0 ? (Y + 18.f * S - Mid.Y) / NearDir.Y : 1e9;
		const FVector2D P = Mid + NearDir * (float)FMath::Min(Tx, Ty);
		const FVector2D Nn(-NearDir.Y, NearDir.X);
		Tri(P + NearDir * 9.f * S, P - NearDir * 5.f * S + Nn * 7.f * S, P - NearDir * 5.f * S - Nn * 7.f * S, FLinearColor(0.9f, 0.15f, 0.12f, 0.95f));
		const FString Dist = FMath::Sqrt(NearD) > 950 ? FString::Printf(TEXT("charger %.1f km"), FMath::Sqrt(NearD) / 1000.0) : FString::Printf(TEXT("charger %d m"), FMath::RoundToInt(FMath::Sqrt(NearD) / 10) * 10);
		const float Tw = TextW(Dist, 0.62f * S);
		Text(Dist, FMath::Clamp((float)P.X - Tw * 0.5f, X + 6.f * S, X + W - Tw - 6.f * S), FMath::Clamp((float)P.Y + (NearDir.Y > 0 ? -26.f : 10.f) * S, Y + 4.f * S, Y + H - 20.f * S), 0.62f * S, FLinearColor(1.f, 0.6f, 0.55f, 0.95f));
	}
	// fuel add-ons not on board yet
	for (const FSkyPickups::FAddonSpot& A : Car.World.AddonSpots)
	{
		if (Car.Progress.Owned.Contains(A.Id)) continue;
		const FVector2D P = ToPanel(A.P.Y / 100.0, A.P.X / 100.0);
		if (!Inside(P)) continue;
		const float R = 6.f * S;
		Tri(FVector2D(P.X, P.Y - R), FVector2D(P.X + R, P.Y), FVector2D(P.X, P.Y + R), Gold);
		Tri(FVector2D(P.X, P.Y - R), FVector2D(P.X - R, P.Y), FVector2D(P.X, P.Y + R), Gold);
	}
	// north
	const FVector2D Nd(-(float)Sn, -(float)C);
	const FVector2D NP(FMath::Clamp(Mid.X + Nd.X * H, X + 16.f * S, X + W - 16.f * S), FMath::Clamp(Mid.Y + Nd.Y * H, Y + 16.f * S, Y + H - 16.f * S));
	DrawRect(FLinearColor(0.08f, 0.09f, 0.11f, 0.85f), NP.X - 10.f * S, NP.Y - 10.f * S, 20.f * S, 20.f * S);
	Text(TEXT("N"), NP.X, NP.Y - 9.f * S, 0.68f * S, FLinearColor(0.85f, 0.9f, 1.f, 0.95f), false, true);
	// the car: a blue arrow with a white rim, pointing up the screen
	const FVector2D Tip(Mid.X, Mid.Y - 12.f * S), Lb(Mid.X - 9.f * S, Mid.Y + 9.f * S), Rb(Mid.X + 9.f * S, Mid.Y + 9.f * S), Nt(Mid.X, Mid.Y + 4.f * S);
	const FVector2D Tip2(Mid.X, Mid.Y - 15.f * S), Lb2(Mid.X - 11.5f * S, Mid.Y + 11.f * S), Rb2(Mid.X + 11.5f * S, Mid.Y + 11.f * S), Nt2(Mid.X, Mid.Y + 6.f * S);
	Tri(Tip2, Lb2, Nt2, FLinearColor::White);
	Tri(Tip2, Nt2, Rb2, FLinearColor::White);
	Tri(Tip, Lb, Nt, FLinearColor(0.2f, 0.45f, 1.f, 1.f));
	Tri(Tip, Nt, Rb, FLinearColor(0.2f, 0.45f, 1.f, 1.f));
	// self-driving: where it's going and the next manoeuvre, in a banner over the map
	if (Car.bFsd)
	{
		DrawRect(FLinearColor(0.05f, 0.06f, 0.08f, 0.88f), X, Y - 58.f * S, W, 52.f * S);
		FString Head = TEXT("SELF-DRIVING");
		if (const ASkysterTraffic* Tr = Car.GetTraffic())
		{
			const FString Dist = Car.FsdDistLeft > 950 ? FString::Printf(TEXT("%.1f km"), Car.FsdDistLeft / 1000.0) : FString::Printf(TEXT("%d m"), FMath::RoundToInt(Car.FsdDistLeft / 10) * 10);
			Head = FString::Printf(TEXT("SELF-DRIVING  ·  %s  ·  %s"), *Tr->FsdDestination(), *Dist);
		}
		Text(Head, X + 12.f * S, Y - 54.f * S, 0.68f * S, FLinearColor(0.35f, 0.6f, 1.f, 1.f));
		Text(Car.FsdHint, X + 12.f * S, Y - 34.f * S, 0.82f * S, Ink);
	}
}
