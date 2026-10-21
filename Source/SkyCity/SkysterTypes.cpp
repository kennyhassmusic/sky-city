#include "SkysterTypes.h"

namespace Skyster
{
	// js/progress.js LEVELS: start in a quick road car and earn the rocket car one system at a time.
	const FSkyLevel Levels[6] = {
		{ TEXT("Stock"), TEXT("motors only: 0-60 in 2 s, 150 mph, one jump"), 150, 2.0, 0, false, false, 0, false, false, 3, {
			{ TEXT("l1-top"), TEXT("Top out at 150 mph"), TEXT("mph"), 148, TEXT("mph"), false },
			{ TEXT("l1-drift"), TEXT("Hold a powerslide for 2 s (X through a turn)"), TEXT("driftT"), 2, TEXT("s"), false },
			{ TEXT("l1-air"), TEXT("Catch 1.5 s of air (hold jump, or off a ramp)"), TEXT("airT"), 1.5, TEXT("s"), false } } },
		{ TEXT("Sport"), TEXT("sport motors and a second jump: double jumps and flips"), 165, 1.5, 0, true, false, 0.3, false, false, 3, {
			{ TEXT("l2-front"), TEXT("Front flip (jump, then stick forward + jump)"), TEXT("frontflip"), 1, TEXT(""), false },
			{ TEXT("l2-back"), TEXT("Backflip (jump, then stick back + jump)"), TEXT("backflip"), 1, TEXT(""), false },
			{ TEXT("l2-sixty"), TEXT("0-60 in under 1.6 s from a standstill"), TEXT("sixty"), 1.6, TEXT("s"), true } } },
		{ TEXT("Thrusters"), TEXT("rear cold-gas thrusters: boost (B) to 205 mph"), 180, 1.1, 205, true, false, 0.5, false, false, 3, {
			{ TEXT("l3-boost"), TEXT("Boost to 200 mph"), TEXT("mph"), 199, TEXT("mph"), false },
			{ TEXT("l3-pads"), TEXT("Grab 5 pressure points (they fill the tank)"), TEXT("pads"), 5, TEXT(""), false },
			{ TEXT("l3-high"), TEXT("Get 20 m off the ground (jump, nose up, boost)"), TEXT("height"), 20, TEXT("m"), false } } },
		{ TEXT("Fans"), TEXT("floor fans: drive up walls, hang from ceilings, more grip at speed"), 190, 0.9, 215, true, true, 1, false, false, 3, {
			{ TEXT("l4-wall"), TEXT("Ride a building wall for 3 s (drive straight at it)"), TEXT("wallT"), 3, TEXT("s"), false },
			{ TEXT("l4-w2w"), TEXT("Jump from one wall onto another"), TEXT("walltowall"), 1, TEXT(""), false },
			{ TEXT("l4-inv"), TEXT("Hang upside down (McGregor ramp: stop past vertical, let go of the triggers)"), TEXT("inverted"), 1, TEXT(""), false } } },
		{ TEXT("Plaid"), TEXT("full power: 0-60 under a second, supersonic, hover"), 200, 0.6, 230, true, true, 1, true, false, 3, {
			{ TEXT("l5-sonic"), TEXT("Go supersonic (217 mph)"), TEXT("mph"), 217, TEXT("mph"), false },
			{ TEXT("l5-hover"), TEXT("Hover 1 s (both jumps, let go, hold jump)"), TEXT("hover"), 1, TEXT(""), false },
			{ TEXT("l5-combo"), TEXT("Land a x5 combo"), TEXT("combo"), 5, TEXT(""), false } } },
		{ TEXT("Rocket"), TEXT("flight: everything together. Hold LB in the air to fly"), 200, 0.6, 230, true, true, 1, true, true, 0, {} },
	};

	FSkyCaps CapsFor(int32 I)
	{
		const FSkyLevel& L = Levels[FMath::Clamp(I, 0, NumLevels - 1)];
		constexpr double MPH = 0.44704, SIXTY = 26.8224;
		const double Top = L.Mph * MPH;
		FSkyCaps C;
		C.Drive = Top;
		// RL-shaped throttle curve (full push at rest, a tenth at the motors' top): the push that gives this 0-60
		C.Accel = Top / (0.9 * L.Sixty) * -FMath::Loge(1 - 0.9 * SIXTY / Top);
		C.bBoost = L.BoostMph > 0;
		C.Top = L.BoostMph > 0 ? L.BoostMph * MPH : Top;
		C.bDoubleJump = L.bDoubleJump;
		C.bWalls = L.bWalls;
		C.Fans = L.Fans;
		C.bHover = L.bHover;
		C.bFlight = L.bFlight;
		return C;
	}

	struct FMove { const TCHAR* Id; const TCHAR* Name; int32 Points; };
	static const FMove Moves[] = {
		{ TEXT("barrelroll"), TEXT("Barrel roll"), 150 }, { TEXT("backflip"), TEXT("Backflip"), 150 }, { TEXT("frontflip"), TEXT("Front flip"), 120 },
		{ TEXT("spin"), TEXT("360"), 100 }, { TEXT("wallride"), TEXT("Wall ride"), 100 }, { TEXT("inverted"), TEXT("Inverted hold"), 300 },
		{ TEXT("hover"), TEXT("Hover"), 150 }, { TEXT("walllaunch"), TEXT("Wall launch"), 250 }, { TEXT("walltowall"), TEXT("Wall to wall"), 300 },
		{ TEXT("flipreset"), TEXT("Flip reset"), 200 }, { TEXT("wavedash"), TEXT("Wave dash"), 120 }, { TEXT("parallel"), TEXT("Parallel park"), 400 },
		{ TEXT("kickflip"), TEXT("Kickflip"), 300 }, { TEXT("bigair"), TEXT("Big air"), 100 }, { TEXT("highflyer"), TEXT("High flyer"), 150 },
		{ TEXT("lineup"), TEXT("Over the line-up"), 500 },
	};

	FString MoveName(const FString& Id)
	{
		for (const FMove& M : Moves) if (Id == M.Id) return M.Name;
		return Id;
	}

	int32 MovePoints(const FString& Id)
	{
		for (const FMove& M : Moves) if (Id == M.Id) return M.Points;
		return 100;
	}

	// "Barrel roll x2 · Backflip · Wall ride"
	FString MoveList(const TArray<FString>& In)
	{
		TArray<FString> Out;
		FString Last;
		int32 N = 0;
		auto Flush = [&]() { if (N > 0) Out.Add(N > 1 ? FString::Printf(TEXT("%s x%d"), *MoveName(Last), N) : MoveName(Last)); };
		for (const FString& M : In)
		{
			if (M == Last) { ++N; continue; }
			Flush();
			Last = M;
			N = 1;
		}
		Flush();
		return FString::Join(Out, TEXT(" · "));
	}

	// js/addons.js: each stretches the tank, and they stack (x24 with all three)
	const FAddon Addons[3] = {
		{ TEXT("nitrogen"), TEXT("Purified nitrogen"), 2, FLinearColor(0.45f, 1.6f, 2.8f) },
		{ TEXT("combustion"), TEXT("Combustion engines"), 3, FLinearColor(2.8f, 1.0f, 0.25f) },
		{ TEXT("rocket"), TEXT("Rocket fuel"), 4, FLinearColor(3.0f, 2.0f, 1.1f) },
	};
}
