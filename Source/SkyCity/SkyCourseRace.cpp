// ASkyCourseRace (see SkyCourse.h): racing on a Course Builder course. The player's car and up to seven AI opponents
// (more ASkysterCars, flagged bAIDriver and driven through their test-input hooks: SkyCourseAI.cpp) line up on the
// starting grid, count down 3-2-1 with the cars held, then race: laps, checkpoints in order with split times, lap
// routing at splits (the gates show which branch is open on the player's lap), a respawn at the last checkpoint after a
// fall, contact between the cars, places and results, the race HUD, and the player's best times for each course, saved
// next to the course file (Saved/Courses/<name>.times.json; the car's Progress save is never touched).
//
// Everything is in the car sim's frame (metres, z up, y left: SkyCourse::ToUE at the edges), like the course itself.
// The race ticks before the cars (each racing car waits on it), so the AI's inputs and contact pushes land the same frame.
#include "SkyCourseRaceImpl.h"

#include "Camera/PlayerCameraManager.h"
#include "CanvasItem.h"
#include "Components/StaticMeshComponent.h"
#include "Debug/DebugDrawService.h"
#include "Dom/JsonObject.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SkysterFleet.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY(LogSkyRace);

using namespace SkyRaceK;

static TAutoConsoleVariable<float> CVarAutopilot(TEXT("SkyCourse.RaceAutopilot"), 0.f,
	TEXT("Test: the race drives the player's car with the AI driver at this skill (0 = off, 0.3-1.2)."));
static TAutoConsoleVariable<FString> CVarSkills(TEXT("SkyCourse.RaceSkills"), TEXT(""),
	TEXT("Test: the opponents' skills, comma separated (e.g. 0.5,0.8,1.1); empty = spread round the race's skill."));
static TAutoConsoleVariable<int32> CVarAssist(TEXT("SkyCourse.RaceAssist"), -1,
	TEXT("Test: the player's race assists, 0 off, 1 light, 2 full (also on the autopilot); -1 = the course menu's setting (never on the autopilot)."));
// AI tuning (read when a race begins)
static TAutoConsoleVariable<float> CVarCorkV(TEXT("SkyCourse.AI.CorkV"), 36.f,
	TEXT("AI: the speed (m/s) it drives a corkscrew at, every skill alike (it held on between about 34 and 42 in tests)."));
static TAutoConsoleVariable<float> CVarJumpAim(TEXT("SkyCourse.AI.JumpAim"), 0.5f,
	TEXT("AI: where on a jump's landing pad it aims, as a share of the pad's length (6 to 10 m in)."));

// Opponents: an invented name, a stand-in body and a paint, so the racers are easy to tell apart.
namespace
{
	struct FOpp { const TCHAR* Name; int32 Vehicle; int32 Paint; FLinearColor Tag; };
	const FOpp GOpps[SkyCourse::MaxOpponents] = {
		{ TEXT("Ruby"),    1, 0, FLinearColor(1.f, 0.32f, 0.28f) },
		{ TEXT("Cobalt"),  2, 1, FLinearColor(0.35f, 0.62f, 1.f) },
		{ TEXT("Amber"),   4, 2, FLinearColor(1.f, 0.78f, 0.3f) },
		{ TEXT("Steel"),   3, 3, FLinearColor(0.85f, 0.88f, 0.92f) },
		{ TEXT("Azure"),   1, 1, FLinearColor(0.4f, 0.85f, 1.f) },
		{ TEXT("Topaz"),   2, 2, FLinearColor(1.f, 0.6f, 0.2f) },
		{ TEXT("Garnet"),  4, 0, FLinearColor(0.9f, 0.25f, 0.5f) },
	};
	const TCHAR* GPaints[4] = { TEXT("MI_Paint_RedGloss"), TEXT("MI_Paint_BlueGloss"), TEXT("MI_Paint_Gold"), TEXT("MI_Paint_Silver") };
	// spread round the chosen skill so a field is mixed
	const double GSkillSpread[SkyCourse::MaxOpponents] = { 0.0, -0.15, 0.1, -0.25, 0.05, -0.1, 0.15 };

	const FLinearColor Ink(1.f, 1.f, 1.f, 0.95f);
	const FLinearColor Dim(0.75f, 0.85f, 1.f, 0.8f);
	const FLinearColor Faint(0.75f, 0.85f, 1.f, 0.45f);
	const FLinearColor Back(0.02f, 0.03f, 0.05f, 0.55f);
	const FLinearColor Green(0.35f, 1.f, 0.55f, 0.95f);
	const FLinearColor Gold(1.f, 0.82f, 0.35f, 0.95f);
	const FLinearColor Red(1.f, 0.3f, 0.25f, 0.97f);
	const FLinearColor Orange(1.f, 0.6f, 0.2f, 0.95f);

	FString TimeStr(double T)
	{
		if (T < 0) return TEXT("-:--.--");
		const int32 M = (int32)(T / 60.0);
		return FString::Printf(TEXT("%d:%05.2f"), M, T - M * 60.0);
	}

	// Did the car's travel this frame, A to B, cross the gate's plane forward, through the gate (its width and height)?
	bool Crossed(const FSkyFrame& G, const FVector& A, const FVector& Bp, double& Frac)
	{
		const double Da = FVector::DotProduct(A - G.P, G.F), Db = FVector::DotProduct(Bp - G.P, G.F);
		if (!(Da < 0 && Db >= 0)) return false;
		Frac = Da / (Da - Db);
		const FVector X = A + (Bp - A) * Frac;
		const double Lat = FVector::DotProduct(X - G.P, G.L), H = FVector::DotProduct(X - G.P, G.U);
		return FMath::Abs(Lat) <= G.Width * 0.5 + 1.5 && H > -2.5 && H < 10.0;
	}

	double SmoothStep(double E0, double E1, double X) { const double T = FMath::Clamp((X - E0) / (E1 - E0), 0.0, 1.0); return T * T * (3 - 2 * T); }

	// The fastest the car takes a bend of curvature K (1/m, + = left) on this frame of deck: the tyres' grip (friction
	// times the load from gravity into the deck, the fans and the wing, as SkysterCar's tyre model has it) plus gravity's
	// pull toward the inside of a banked bend. Margin keeps it short of the slide.
	double BendLimit(const FSkyFrame& F, double K, double Mu, double Margin)
	{
		const double Ka = FMath::Abs(K);
		if (Ka < 1e-4) return MAX_SPEED;
		const double Gin = -G * F.L.Z * (K > 0 ? 1.0 : -1.0);
		const bool bWall = F.U.Z < 0.6;
		double V = 40;
		for (int32 i = 0; i < 6; ++i)
		{
			const double Fans = bWall ? 1.0 : 0.15 + 0.45 * SmoothStep(15, 40, V);
			const double Load = FMath::Max(G * 0.25, G * F.U.Z + G * SUCTION * Fans + G * AERO * FMath::Square(V / MAX_SPEED));
			V = FMath::Min(MAX_SPEED, FMath::Sqrt(FMath::Max(1.0, Gin + Margin * Mu * Load) / Ka));
		}
		return V;
	}
}

// --- setup ------------------------------------------------------------------------------------------

void FSkyCourseRaceImpl::Note(const FString& Msg)
{
	const FString Line = FString::Printf(TEXT("%7.2f  %s"), Clock(), *Msg);
	UE_LOG(LogSkyRace, Log, TEXT("%s"), *Line);
	if (Events.Num() < 600) Events.Add(Line);
}

bool FSkyCourseRaceImpl::IsOpen(int32 Sp, int32 Br, int32 Lap) const
{
	if (!B.Splits.IsValidIndex(Sp)) return true;
	const FSkyBaked::FSplitInfo& S = B.Splits[Sp];
	if (S.Gate == ESkyGate::None) return true;   // free choice: every branch open
	return !S.OpenLaps.IsValidIndex(Br) || S.OpenLaps[Br].Num() == 0 || S.OpenLaps[Br].Contains(Lap);
}

void FSkyCourseRaceImpl::Prepare()
{
	const int32 NS = B.Segs.Num();
	X.Reset();
	X.SetNum(NS);
	for (int32 s = 0; s < NS; ++s)
	{
		const TArray<FSkyFrame>& Fr = B.Segs[s].Frames;
		FSegX& Sx = X[s];
		Sx.Cum.SetNumZeroed(Fr.Num());
		for (int32 i = 1; i < Fr.Num(); ++i) Sx.Cum[i] = Sx.Cum[i - 1] + (float)FVector::Dist(Fr[i].P, Fr[i - 1].P);
		Sx.Len = Fr.Num() ? Sx.Cum.Last() : 0.f;
	}
	for (int32 s = 0; s < NS; ++s)
	{
		for (int32 n : B.Segs[s].Next) if (X.IsValidIndex(n)) X[n].Prev.AddUnique(s);
	}
	for (int32 i = 0; i < B.Splits.Num(); ++i)
	{
		for (int32 b = 0; b < B.Splits[i].LeadSegs.Num(); ++b)
		{
			const int32 L = B.Splits[i].LeadSegs[b];
			if (!X.IsValidIndex(L)) continue;
			X[L].Split = i;
			X[L].Branch = b;
			// its slot across the deck before the fork (the AI gets over to that side in time)
			if (X[L].Prev.Num() && B.Segs[L].Frames.Num())
			{
				const FSkyFrame& Pf = B.Segs[X[L].Prev[0]].Frames.Last();
				X[L].ForkOff = (float)FVector::DotProduct(B.Segs[L].Frames[0].P - Pf.P, Pf.L);
			}
		}
	}
	for (int32 s = 0; s < NS; ++s) PrepareSeg(s);
	LimitTransitions();

	// gates: the frame each one stands on
	GateFrame.SetNum(B.Gates.Num());
	StartGate = FinishGate = INDEX_NONE;
	for (int32 g = 0; g < B.Gates.Num(); ++g)
	{
		const FSkyBaked::FGate& Gt = B.Gates[g];
		GateFrame[g] = B.Segs.IsValidIndex(Gt.Seg) ? NearestOnSeg(Gt.Seg, Gt.At.P) : 0;
		if (Gt.Type == ESkyPiece::Start && StartGate == INDEX_NONE) StartGate = g;
		if (Gt.Type == ESkyPiece::Finish && FinishGate == INDEX_NONE) FinishGate = g;
	}

	// which way each branch goes, for the HUD's hints: by the branch angle (+ = left), left first
	BranchDir.SetNum(B.Splits.Num());
	for (int32 i = 0; i < B.Splits.Num(); ++i)
	{
		const FSkyBaked::FSplitInfo& Sp = B.Splits[i];
		const int32 N = Sp.LeadSegs.Num();
		TArray<double> Ang;
		Ang.SetNumZeroed(N);
		const FSkyPiece* Piece = (Course.Seqs.IsValidIndex(Sp.Seq) && Course.Seqs[Sp.Seq].Pieces.IsValidIndex(Sp.Piece)) ? &Course.Seqs[Sp.Seq].Pieces[Sp.Piece] : nullptr;
		for (int32 b = 0; b < N; ++b)
		{
			if (Piece && Piece->Branches.IsValidIndex(b)) Ang[b] = Piece->Branches[b].Angle;
			else if (B.Segs.IsValidIndex(Sp.LeadSegs[b]) && B.Segs[Sp.LeadSegs[b]].Frames.Num() > 1)
			{
				const TArray<FSkyFrame>& Fr = B.Segs[Sp.LeadSegs[b]].Frames;
				Ang[b] = FVector::DotProduct(Fr.Last().P - Fr[0].P, Fr[0].L);   // + = heads off to the left
			}
		}
		TArray<int32> Ord;
		for (int32 b = 0; b < N; ++b) Ord.Add(b);
		Ord.Sort([&Ang](int32 A, int32 Bb) { return Ang[A] > Ang[Bb]; });
		static const TCHAR* Names2[] = { TEXT("LEFT"), TEXT("RIGHT") };
		static const TCHAR* Names3[] = { TEXT("LEFT"), TEXT("CENTRE"), TEXT("RIGHT") };
		static const TCHAR* Names4[] = { TEXT("FAR LEFT"), TEXT("LEFT"), TEXT("RIGHT"), TEXT("FAR RIGHT") };
		BranchDir[i].SetNum(N);
		for (int32 k = 0; k < N; ++k)
		{
			BranchDir[i][Ord[k]] = N == 2 ? Names2[k] : N == 3 ? Names3[k] : N == 4 ? Names4[k] : *FString::Printf(TEXT("BRANCH %d"), Ord[k] + 1);
		}
	}

	// each lap's default route (SkyCourse::Route: the first branch open on that lap), as a branch per split
	LapChoice.SetNum(Laps + 1);
	for (int32 Lap = 1; Lap <= Laps; ++Lap)
	{
		const TArray<int32> Segs = SkyCourse::Route(B, Lap);
		TArray<int32>& C = LapChoice[Lap];
		C.Init(0, B.Splits.Num());
		for (int32 i = 0; i < B.Splits.Num(); ++i)
		{
			int32 Pick = INDEX_NONE;
			for (int32 b = 0; b < B.Splits[i].LeadSegs.Num() && Pick == INDEX_NONE; ++b) if (Segs.Contains(B.Splits[i].LeadSegs[b])) Pick = b;
			for (int32 b = 0; b < B.Splits[i].LeadSegs.Num() && Pick == INDEX_NONE; ++b) if (IsOpen(i, b, Lap)) Pick = b;
			C[i] = FMath::Max(0, Pick);
		}
	}
}

// Speed limits from the bends and banks, and what a loop or a jump asks of the AI (SkyCourseAI.cpp plans with these).
void FSkyCourseRaceImpl::PrepareSeg(int32 s)
{
	const FSkySegment& Sg = B.Segs[s];
	FSegX& Sx = X[s];
	const TArray<FSkyFrame>& Fr = Sg.Frames;
	const int32 N = Fr.Num();
	TArray<float> Raw;
	Raw.SetNumUninitialized(N);
	Sx.KL.SetNumZeroed(N);
	double MaxKU = 0;
	for (int32 i = 0; i < N; ++i)
	{
		const int32 I0 = FMath::Max(0, i - 4), I1 = FMath::Min(N - 1, i + 4);
		const double Ds = Sx.Cum[I1] - Sx.Cum[I0];
		double KL = 0, KU = 0;
		if (Ds > 0.2)
		{
			const FVector Kv = (Fr[I1].F - Fr[I0].F) / Ds;
			KL = FVector::DotProduct(Kv, Fr[i].L);
			KU = FVector::DotProduct(Kv, Fr[i].U);
		}
		MaxKU = FMath::Max(MaxKU, KU);
		Sx.KL[i] = (float)KL;
		Raw[i] = (float)BendLimit(Fr[i], KL, 1.15, 0.72);
	}
	// the least over 2 m back and 6 m ahead: a planner sampling every 2 m can't step over a tight spot, and the car is
	// down to speed a little before a bend rather than braking into it (braking while turning swings the tail)
	Sx.VMax.SetNumUninitialized(N);
	for (int32 i = 0; i < N; ++i)
	{
		float M = Raw[i];
		for (int32 k = FMath::Max(0, i - 4); k <= FMath::Min(N - 1, i + 12); ++k) M = FMath::Min(M, Raw[k]);
		Sx.VMax[i] = M;
	}
	if (Sg.Kind != ESkySeg::Piece) return;
	Sx.bBoost = Sg.Type == ESkyPiece::Booster;
	const FSkyPiece* Piece = (Course.Seqs.IsValidIndex(Sg.Seq) && Course.Seqs[Sg.Seq].Pieces.IsValidIndex(Sg.Piece)) ? &Course.Seqs[Sg.Seq].Pieces[Sg.Piece] : nullptr;
	if (Sg.Type == ESkyPiece::Loop)
	{
		// over the top a loop needs v^2 / r above gravity (with a margin): from the bottom, that plus climbing 2 r
		const double R = (Piece && Piece->Radius > 1) ? Piece->Radius : (MaxKU > 0.01 ? 1.0 / MaxKU : 10.0);
		Sx.bLoop = true;
		Sx.NeedV = (float)(0.9 * FMath::Sqrt(G * R * (1.3 + 4.0)));
		Sx.NeedAt = 0;
		return;
	}
	if (Sg.Type == ESkyPiece::Corkscrew)
	{
		// the deck rolls round an axis above it: speed presses the car in when it's upside down. The bend limit's
		// bank term misreads the rolled deck, and the centre line doesn't turn across the deck anyway
		// in PIE tests the car held on between about 75 and 95 mph: slower it slid off the side as the deck rolled past
		// vertical, faster it came off upside down. Every skill drives it at the one speed (SkyCourse.AI.CorkV)
		const double Vc = FMath::Clamp((double)CVarCorkV.GetValueOnGameThread(), 25.0, 60.0);
		for (float& V : Sx.VMax) V = (float)(Vc + 1.5);
		Sx.bCork = true;
		Sx.NeedV = (float)Vc;
		Sx.NeedAt = 0;
		return;
	}
	if (Sg.Type == ESkyPiece::Jump)
	{
		int32 G0 = INDEX_NONE, G1 = INDEX_NONE;
		for (int32 i = 0; i < N; ++i) if (!Fr[i].bDeck) { if (G0 == INDEX_NONE) G0 = i; G1 = i; }
		if (G0 <= 0 || G1 >= N - 1) return;
		const FSkyFrame& Lip = Fr[G0 - 1];
		FVector H(Lip.F.X, Lip.F.Y, 0);
		if (!H.Normalize()) return;
		const double Th = FMath::Asin(FMath::Clamp(Lip.F.Z, -0.95, 0.95));
		const double C = FMath::Cos(Th), Sn = FMath::Sin(Th);
		// the landing pad, from the lip: its edge, 3 m on (it falls away along the flight path), and the deck's end
		auto Rel = [&](const FSkyFrame& F, double& Dx, double& Dz) { Dx = FVector::DotProduct(F.P - Lip.P, H); Dz = F.P.Z - Lip.P.Z; };
		double D, Dz, D3, Dz3, DE, DzE;
		Rel(Fr[G1 + 1], D, Dz);
		Rel(Fr[FMath::Min(G1 + 7, N - 1)], D3, Dz3);
		Rel(Fr[N - 1], DE, DzE);
		auto Height = [&](double V, double Up, double Xd) { const double Vx = FMath::Max(V * C, 0.1), T = Xd / Vx; return (V * Sn + Up) * T - 0.5 * G * T * T; };
		// clear the pad's edge and come down onto it (Up: a jump at the lip adds that much climb)
		auto Clears = [&](double V, double Up) { return Height(V, Up, D) >= Dz + 0.3 && Height(V, Up, D3) >= Dz3 + 0.1; };
		auto MinV = [&](double Up) { for (double V = 6; V <= MAX_SPEED; V += 0.5) if (Clears(V, Up)) return V; return -1.0; };
		const double V0 = MinV(0.0), V1 = MinV(HOP_DV);
		Sx.bJump = true;
		Sx.NeedAt = G0 - 1;
		Sx.LandAt = G1 + 1;
		// aim several metres onto the pad (a share of its length, 6-10 m in), so a little slow or fast still lands on it:
		// the take-off speed whose flight path (the frames' ballistic formula, from the lip) comes down there. Coming
		// down just past the edge isn't enough: the car's nose (1.5 m ahead of its wheels' contact, 0.2 m up) catches
		// the pad's face and it drops into the gap (PIE, 22 Oct: 45.8 m/s over a 45.5 m/s gap)
		const double PadLen = Sx.Cum[N - 1] - Sx.Cum[G1 + 1];
		const double AimIn = FMath::Clamp(PadLen * (double)CVarJumpAim.GetValueOnGameThread(), 6.0, 10.0);
		int32 Aim = G1 + 1;
		while (Aim < N - 1 && Sx.Cum[Aim] - Sx.Cum[G1 + 1] < AimIn) ++Aim;
		Sx.AimAt = Aim;
		double Da, Dza;
		Rel(Fr[Aim], Da, Dza);
		const double Den = 2.0 * C * C * (Da * Sn / FMath::Max(C, 0.1) - Dza);
		if (V0 > 0 && V0 < 85)
		{
			const double Va = Den > 1e-3 ? FMath::Sqrt(G * Da * Da / Den) : V0 * 1.08;
			Sx.MinV = (float)V0;
			Sx.NeedV = (float)FMath::Clamp(Va, V0 + 2.0, V0 * 1.15 + 2.0);
		}
		else if (V1 > 0) { Sx.MinV = (float)V1; Sx.NeedV = (float)(V1 * 1.04 + 1.0); Sx.bHop = true; }
		else { Sx.NeedV = 95.f; Sx.bHop = true; }
		// and no faster than a little over that: faster lands further down the pad, with less deck left to brake on
		// before whatever comes next (and the car can't brake in the air)
		if (!Sx.bHop) Sx.CapV = Sx.NeedV + 2.f;
		(void)DE; (void)DzE;
		Note(FString::Printf(TEXT("jump seg %d: gap %.1f m, rise %.1f m, lip %.0f deg, pad %.0f m: clears it from %.1f m/s, aims %.0f m in at %.1f m/s%s%s"), s, D, Dz,
			FMath::RadiansToDegrees(Th), PadLen, Sx.MinV, AimIn, Sx.NeedV, Sx.bHop ? TEXT(" and a jump at the lip") : TEXT(""),
			Sx.CapV > 0 ? *FString::Printf(TEXT(", at most %.1f"), Sx.CapV) : TEXT("")));
	}
}

// Where the track's bend changes sharply (a curve's start or end, an S-bend where a fork's lead-in hands over to its
// branch), a car runs a little wide or tight while its steering catches up (~0.25 s of lag): about v^2 dK t^2 / 2. On a
// narrow deck that's the edge (a one-lane branch's S-bend at 60 m/s threw cars off it, 22 Oct), so slow to where it
// stays within the deck, less a car's half width and a margin. Across segment joins too (each segment's curvature is
// worked out on its own frames).
void FSkyCourseRaceImpl::LimitTransitions()
{
	constexpr double Lag = 0.25;
	constexpr int32 Span = 8;   // frames (4 m) each side
	auto KAt = [this](int32 Sg, int32 I) { const FSegX& Sx = X[Sg]; return Sx.KL.IsValidIndex(I) ? (double)Sx.KL[I] : 0.0; };
	auto Limit = [&](double Dk, double Width) { const double Room = FMath::Max(0.6, Width * 0.5 - 1.5); return Dk > 1e-4 ? FMath::Sqrt(2.0 * Room / (Dk * Lag * Lag)) : MAX_SPEED; };
	TArray<TArray<float>> Lim;
	Lim.SetNum(B.Segs.Num());
	for (int32 s = 0; s < B.Segs.Num(); ++s) Lim[s].Init((float)MAX_SPEED, B.Segs[s].Frames.Num());
	for (int32 s = 0; s < B.Segs.Num(); ++s)
	{
		const TArray<FSkyFrame>& Fr = B.Segs[s].Frames;
		const int32 N = Fr.Num();
		if (B.Segs[s].Kind == ESkySeg::Piece && (B.Segs[s].Type == ESkyPiece::Loop || B.Segs[s].Type == ESkyPiece::Corkscrew)) continue;   // planned on their own
		for (int32 i = 0; i < N; ++i)
		{
			const double Dk = FMath::Abs(KAt(s, FMath::Min(N - 1, i + Span)) - KAt(s, FMath::Max(0, i - Span)));
			Lim[s][i] = FMath::Min(Lim[s][i], (float)Limit(Dk, Fr[i].Width));
		}
		// into each following segment
		for (int32 n : B.Segs[s].Next)
		{
			if (!B.Segs.IsValidIndex(n) || B.Segs[n].Frames.Num() < 2) continue;
			const int32 M = B.Segs[n].Frames.Num();
			for (int32 k = 0; k < Span; ++k)
			{
				const double Before = KAt(s, FMath::Max(0, N - 1 - Span + k)), After = KAt(n, FMath::Min(M - 1, k + 1));
				const double Dk = FMath::Abs(After - Before);
				const double W = FMath::Min(Fr.Last().Width, B.Segs[n].Frames[0].Width);
				const float V = (float)Limit(Dk, W);
				Lim[s][FMath::Max(0, N - 1 - Span + k)] = FMath::Min(Lim[s][FMath::Max(0, N - 1 - Span + k)], V);
				Lim[n][FMath::Min(M - 1, k)] = FMath::Min(Lim[n][FMath::Min(M - 1, k)], V);
			}
		}
	}
	int32 Hits = 0;
	for (int32 s = 0; s < B.Segs.Num(); ++s)
	{
		FSegX& Sx = X[s];
		for (int32 i = 0; i < Sx.VMax.Num() && i < Lim[s].Num(); ++i) if (Lim[s][i] < Sx.VMax[i]) { Sx.VMax[i] = Lim[s][i]; ++Hits; }
	}
	if (Hits) UE_LOG(LogSkyRace, Log, TEXT("race: %d frames slowed for sharp bend changes on narrow deck"), Hits);
}

int32 FSkyCourseRaceImpl::NearestOnSeg(int32 Sg, const FVector& P) const
{
	const TArray<FSkyFrame>& Fr = B.Segs[Sg].Frames;
	int32 Best = 0;
	double BestD = TNumericLimits<double>::Max();
	for (int32 i = 0; i < Fr.Num(); ++i)
	{
		const double D = FVector::DistSquared(P, Fr[i].P);
		if (D < BestD) { BestD = D; Best = i; }
	}
	return Best;
}

// --- routes -----------------------------------------------------------------------------------------

// Walk the course from the start piece, taking Choice[split] at every split, to the finish (or back round to the start).
void FSkyCourseRaceImpl::BuildRoute(FRacer& R, const TArray<int32>& Choice)
{
	FRoute& Rt = R.Route;
	Rt.Segs.Reset();
	Rt.At.Reset();
	Rt.Checks.Reset();
	Rt.CheckS.Reset();
	Rt.Choice = Choice;
	Seen.Init(0, B.Segs.Num());
	int32 Sg = 0;
	double D = 0;
	while (B.Segs.IsValidIndex(Sg) && !Seen[Sg])
	{
		Seen[Sg] = 1;
		Rt.Segs.Add(Sg);
		Rt.At.Add(D);
		D += X[Sg].Len;
		const TArray<int32>& N = B.Segs[Sg].Next;
		if (N.Num() == 0) break;
		if (N.Num() == 1) { Sg = N[0]; continue; }
		const int32 Sp = X.IsValidIndex(N[0]) ? X[N[0]].Split : INDEX_NONE;
		const int32 Want = (Sp != INDEX_NONE && Choice.IsValidIndex(Sp)) ? Choice[Sp] : 0;
		int32 Pick = N[0];
		for (int32 n : N) if (X.IsValidIndex(n) && X[n].Branch == Want) { Pick = n; break; }
		Sg = Pick;
	}
	Rt.Len = D;
	auto GateS = [&](int32 g) -> double
	{
		const int32 Ri = B.Gates.IsValidIndex(g) ? Rt.Segs.Find(B.Gates[g].Seg) : INDEX_NONE;
		return Ri == INDEX_NONE ? -1.0 : Rt.At[Ri] + X[B.Gates[g].Seg].Cum[GateFrame[g]];
	};
	Rt.GateS = FMath::Max(0.0, GateS(StartGate));
	if (B.bLapCourse) Rt.EndS = Rt.Len + Rt.GateS;
	else { const double F = GateS(FinishGate); Rt.EndS = F > 0 ? F : Rt.Len; }
	struct FCk { int32 G; double S; };
	TArray<FCk> Cks;
	for (int32 g = 0; g < B.Gates.Num(); ++g)
	{
		if (B.Gates[g].Type != ESkyPiece::Checkpoint) continue;
		const double S = GateS(g);
		if (S >= 0) Cks.Add({ g, S });
	}
	Cks.Sort([](const FCk& A, const FCk& Bb) { return A.S < Bb.S; });
	for (const FCk& C : Cks) { Rt.Checks.Add(C.G); Rt.CheckS.Add(C.S); }
	R.Ri = Rt.Segs.Find(R.Seg);
	R.NextCheck = 0;
	while (Rt.Checks.IsValidIndex(R.NextCheck) && R.Passed.IsValidIndex(Rt.Checks[R.NextCheck]) && R.Passed[Rt.Checks[R.NextCheck]]) ++R.NextCheck;
}

// The branch to take at each split this lap: the ones already entered stay; the rest are the lap's own route, except
// that an opponent (and the test autopilot) takes a branch the gates show open, as Kenny asked.
TArray<int32> FSkyCourseRaceImpl::ChoiceFor(const FRacer& R, int32 Lap) const
{
	TArray<int32> C = LapChoice[FMath::Clamp(Lap, 1, Laps)];
	for (int32 i = 0; i < C.Num(); ++i)
	{
		if (R.Entered.IsValidIndex(i) && R.Entered[i] && R.Route.Choice.IsValidIndex(i)) { C[i] = R.Route.Choice[i]; continue; }
		if (!Drives(R) || !Shown.IsValidIndex(i) || Shown[i].Num() == 0) continue;
		if (Shown[i].IsValidIndex(C[i]) && Shown[i][C[i]]) continue;
		for (int32 b = 0; b < Shown[i].Num(); ++b) if (Shown[i][b]) { C[i] = b; break; }
	}
	return C;
}

void FSkyCourseRaceImpl::RefreshChoice(FRacer& R)
{
	const TArray<int32> C = ChoiceFor(R, R.Lap);
	if (C != R.Route.Choice) BuildRoute(R, C);
}

// After a teleport into a branch: a route through where the car is (one split's choice changed at a time).
void FSkyCourseRaceImpl::FitRoute(FRacer& R)
{
	R.Ri = R.Route.Segs.Find(R.Seg);
	if (R.Ri != INDEX_NONE) return;
	const TArray<int32> Base = R.Route.Choice;
	for (int32 i = 0; i < B.Splits.Num(); ++i)
	{
		for (int32 b = 0; b < B.Splits[i].LeadSegs.Num(); ++b)
		{
			TArray<int32> C = Base;
			if (!C.IsValidIndex(i) || C[i] == b) continue;
			C[i] = b;
			BuildRoute(R, C);
			if (R.Ri != INDEX_NONE) { if (R.Entered.IsValidIndex(i)) R.Entered[i] = true; return; }
		}
	}
	BuildRoute(R, Base);
}

void FSkyCourseRaceImpl::UpdateGates(int32 Lap)
{
	Lap = FMath::Clamp(Lap, 1, Laps);
	if (Lap == ShownLap) return;
	ShownLap = Lap;
	Shown.SetNum(B.Splits.Num());
	FString Desc;
	for (int32 i = 0; i < B.Splits.Num(); ++i)
	{
		const int32 N = B.Splits[i].LeadSegs.Num();
		Shown[i].SetNum(N);
		for (int32 b = 0; b < N; ++b)
		{
			const bool bOpen = IsOpen(i, b, Lap);
			Shown[i][b] = bOpen;
			if (ASkyCourseTrack* Tr = Track.Get()) Tr->SetBranchOpen(i, b, bOpen);
			if (bOpen) Desc += FString::Printf(TEXT(" s%d:b%d"), i, b);
		}
	}
	if (B.Splits.Num()) Note(FString::Printf(TEXT("gates show lap %d: open%s"), Lap, *Desc));
	for (FRacer& R : Racers) if (Drives(R)) RefreshChoice(R);
}

bool FSkyCourseRaceImpl::Drives(const FRacer& R) const
{
	return R.bAI || (R.bPlayer && AutopilotSkill() > 0);
}

double FSkyCourseRaceImpl::AutopilotSkill()
{
	return CVarAutopilot.GetValueOnGameThread();
}

// --- begin / end ------------------------------------------------------------------------------------

bool FSkyCourseRaceImpl::Begin(ASkyCourseTrack* InTrack, const FSkyCourse& InCourse, ASkysterCar* Player, int32 Opponents, double Skill)
{
	UWorld* World = Owner->GetWorld();
	if (!InTrack || !World)
	{
		UE_LOG(LogSkyRace, Warning, TEXT("race: no track"));
		return false;
	}
	Track = InTrack;
	Course = InCourse;
	B = InTrack->GetBaked();
	if (!B.bValid || B.Segs.Num() == 0 || B.Segs[0].Frames.Num() < 2)
	{
		UE_LOG(LogSkyRace, Warning, TEXT("race: the course isn't built (%d errors)"), B.Errors.Num());
		return false;
	}
	for (const FSkySegment& Sg : B.Segs)
	{
		if (Sg.Frames.Num() < 2) { UE_LOG(LogSkyRace, Warning, TEXT("race: the bake has a segment with %d frames"), Sg.Frames.Num()); return false; }
	}
	Laps = B.bLapCourse ? FMath::Clamp(Course.Laps, 1, SkyCourse::MaxLaps) : 1;
	PlayerAssist = ASkyCourseMode::Get(World) ? ASkyCourseMode::Get(World)->GetAssist() : ESkyAssist::Full;
	Opponents = FMath::Clamp(Opponents, 0, SkyCourse::MaxOpponents);
	Skill = FMath::Clamp(Skill, 0.3, 1.2);
	Events.Reset();
	Traces.Reset();
	T = 0;
	Phase = EPhase::Countdown;
	Prepare();
	LoadTimes();
	Note(FString::Printf(TEXT("race on \"%s\": %d lap%s, %.0f m a lap, %d segments, %d gates, %d splits, %d opponents at skill %.2f"),
		*Course.Name, Laps, Laps == 1 ? TEXT("") : TEXT("s"), B.Length, B.Segs.Num(), B.Gates.Num(), B.Splits.Num(), Opponents, Skill));

	// test override of the opponents' skills
	TArray<double> Skills;
	{
		TArray<FString> Parts;
		CVarSkills.GetValueOnGameThread().ParseIntoArray(Parts, TEXT(","));
		for (const FString& P : Parts) Skills.Add(FMath::Clamp(FCString::Atod(*P), 0.3, 1.2));
	}

	Racers.Reset();
	PlayerIdx = INDEX_NONE;
	auto AddRacer = [&](ASkysterCar* Car, const FTransform& Slot) -> FRacer&
	{
		FRacer& R = Racers.AddDefaulted_GetRef();
		R.Car = Car;
		R.Slot = Slot;
		R.Entered.Init(false, B.Splits.Num());
		R.Passed.Init(false, B.Gates.Num());
		R.BestSplits.Init(-1.0, B.Gates.Num());
		R.LapSplits.Init(-1.0, B.Gates.Num());
		R.Seg = 0;
		R.Frame = NearestOnSeg(0, SkyCourse::FromUE(Slot.GetLocation()));
		const int32 V = Car ? Car->GetVehicle() : 0;
		const FVector Size = V > 0 ? SkyFleet::Cars[V - 1].Size : SkyFleet::ROADSTER;
		R.Radius = FMath::Max(0.6, Size.Y / 200.0 * 0.95);
		R.HalfLen = FMath::Max(0.0, Size.X / 200.0 - R.Radius);
		return R;
	};

	// the player first, on the front slot
	if (Player)
	{
		const FTransform Slot = GridSlot(0);
		Player->TestTeleport(Slot.GetLocation() + FVector(0, 0, 60), (float)Slot.Rotator().Yaw);
		FRacer& R = AddRacer(Player, Slot);
		R.bPlayer = true;
		R.Name = TEXT("You");
		R.Color = FLinearColor(0.3f, 0.75f, 1.f);
		R.Skill = 1.0;
		InitAI(R, 7);   // only used by the test autopilot (SkyCourse.RaceAutopilot)
		PlayerIdx = 0;
		Held.Save(*Player);
		Hold(*Player);
		bHolding = true;
		Player->AddTickPrerequisiteActor(Owner);
	}
	// the opponents behind, each its own body, paint and lane
	for (int32 i = 0; i < Opponents; ++i)
	{
		const FOpp& O = GOpps[i];
		const FTransform Slot = GridSlot(i + 1);
		FTransform Xf(Slot.GetRotation(), Slot.GetLocation() + FVector(0, 0, 60));
		ASkysterCar* Car = World->SpawnActorDeferred<ASkysterCar>(ASkysterCar::StaticClass(), Xf, Owner, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
		if (!Car) continue;
		Car->bAIDriver = true;
		Car->TestVehicle = O.Vehicle;
		Hold(*Car);
		Car->FinishSpawning(Xf);
		Paint(*Car, O.Paint);
		Car->AddTickPrerequisiteActor(Owner);
		FRacer& R = AddRacer(Car, Slot);
		R.bAI = true;
		R.Name = O.Name;
		R.Color = O.Tag;
		R.Skill = Skills.IsValidIndex(i) ? Skills[i] : FMath::Clamp(Skill + GSkillSpread[i], 0.3, 1.2);
		// its lane: the side of the deck its grid slot is on (a little spread so the columns don't drive nose to tail)
		{
			const FSkyFrame& F = B.Segs[0].Frames[R.Frame];
			const double Lat = FVector::DotProduct(SkyCourse::FromUE(Slot.GetLocation()) - F.P, F.L);
			static const double Spread[SkyCourse::MaxOpponents] = { 0.0, 0.1, -0.1, 0.2, -0.2, 0.05, -0.05 };
			R.Lane = FMath::Clamp(Lat / FMath::Max(1.0, F.Width * 0.5 - 1.3) + Spread[i], -0.85, 0.85);
		}
		InitAI(R, i);
		Note(FString::Printf(TEXT("%s: %s, skill %.2f, lane %+.2f"), *R.Name, *Car->GetVehicleName(), R.Skill, R.Lane));
	}
	if (Racers.Num() == 0)
	{
		UE_LOG(LogSkyRace, Warning, TEXT("race: no cars"));
		return false;
	}
	ShownLap = 0;
	UpdateGates(1);
	for (FRacer& R : Racers)
	{
		BuildRoute(R, ChoiceFor(R, 1));
		if (ASkysterCar* C = R.Car.Get()) R.Prev = C->Pos;
		R.SafeSeg = INDEX_NONE;
	}
	// no Course Builder director to draw the race HUD (a test race from the console): draw it here
	if (!ASkyCourseMode::Get(World))
	{
		TWeakObjectPtr<ASkyCourseRace> Weak(Owner);
		DrawHandle = UDebugDrawService::Register(TEXT("Game"), FDebugDrawDelegate::CreateLambda([Weak](UCanvas* Canvas, APlayerController* PC)
		{
			ASkyCourseRace* Race = Weak.Get();
			if (!Race || !Canvas || !PC || PC->GetWorld() != Race->GetWorld()) return;
			Race->DrawHud(nullptr, Canvas, Canvas->ClipY / 1080.f);
		}));
	}
	return true;
}

FSkyCourseRaceImpl::~FSkyCourseRaceImpl()
{
	if (DrawHandle.IsValid()) UDebugDrawService::Unregister(DrawHandle);
}

void FSkyCourseRaceImpl::End()
{
	if (DrawHandle.IsValid()) { UDebugDrawService::Unregister(DrawHandle); DrawHandle.Reset(); }
	if (PlayerIdx != INDEX_NONE && !bSaved && (bNewPbLap || bNewPbRace)) SaveTimes();
	for (FRacer& R : Racers)
	{
		ASkysterCar* Car = R.Car.Get();
		if (!Car) continue;
		Car->RemoveTickPrerequisiteActor(Owner);
		ClearRaceHooks(*Car);
		if (R.bAI) Car->Destroy();
		else if (R.bPlayer)
		{
			if (bHolding || CVarAutopilot.GetValueOnGameThread() > 0.f) Held.Restore(*Car);
		}
	}
	bHolding = false;
	// back to building: the gates show lap 1's routing again, as the track does when it's built
	if (ASkyCourseTrack* Tr = Track.Get())
	{
		for (int32 i = 0; i < B.Splits.Num(); ++i) for (int32 b = 0; b < B.Splits[i].LeadSegs.Num(); ++b) Tr->SetBranchOpen(i, b, IsOpen(i, b, 1));
	}
	if (Racers.Num()) Note(TEXT("race ended"));
	Racers.Reset();
}

FTransform FSkyCourseRaceImpl::GridSlot(int32 K) const
{
	if (B.Grid.IsValidIndex(K)) return B.Grid[K];
	// more cars than the grid has slots: two columns further back down the start piece
	const TArray<FSkyFrame>& Fr = B.Segs[0].Frames;
	const int32 Gi = StartGate != INDEX_NONE ? GateFrame[StartGate] : Fr.Num() - 1;
	const int32 Row = K / 2, Col = K % 2;
	int32 I = Gi - 12 - Row * 16;
	FSkyFrame F = Fr[FMath::Clamp(I, 0, Fr.Num() - 1)];
	if (I < 0) F.P -= F.F * (-I * SkyCourse::SampleStep);
	const FVector P = F.P + F.L * (F.Width * (Col == 0 ? 0.22 : -0.22));
	const double Yaw = -FMath::RadiansToDegrees(FMath::Atan2(F.F.Y, F.F.X));
	return FTransform(FRotator(0, Yaw, 0), SkyCourse::ToUE(P));
}

void FSkyCourseRaceImpl::FHeld::Save(const ASkysterCar& C)
{
	bOn = C.bTestInput; Thr = C.TestThrottle; Brk = C.TestBrake; Stop = C.TestStop; Steer = C.TestSteer; Pitch = C.TestPitch; Roll = C.TestRoll;
	bBoost = C.bTestBoost; bJump = C.bTestJump; bSlide = C.bTestSlide; bFly = C.bTestFly;
}

void FSkyCourseRaceImpl::FHeld::Restore(ASkysterCar& C) const
{
	C.bTestInput = bOn; C.TestThrottle = Thr; C.TestBrake = Brk; C.TestStop = Stop; C.TestSteer = Steer; C.TestPitch = Pitch; C.TestRoll = Roll;
	C.bTestBoost = bBoost; C.bTestJump = bJump; C.bTestSlide = bSlide; C.bTestFly = bFly;
}

// Held on the grid: scripted input with nothing pressed but the X brake, which holds a car still on any slope.
void FSkyCourseRaceImpl::Hold(ASkysterCar& C)
{
	C.bTestInput = true;
	C.TestThrottle = C.TestBrake = C.TestSteer = C.TestPitch = C.TestRoll = 0.f;
	C.TestStop = 1.f;
	C.bTestBoost = C.bTestJump = C.bTestSlide = C.bTestFly = false;
}

// A stand-in body's paint slot gets one of the shared paints, so two opponents in the same body still look different.
void FSkyCourseRaceImpl::Paint(ASkysterCar& Car, int32 PaintIdx)
{
	const TCHAR* Name = GPaints[PaintIdx % 4];
	UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/Vehicles/Shared/Materials/%s.%s"), Name, Name));
	if (!M) M = LoadObject<UMaterialInterface>(nullptr, *FString::Printf(TEXT("/Game/Vehicles/Tesla/Materials/%s.%s"), Name, Name));
	if (!M) return;
	TArray<UStaticMeshComponent*> Comps;
	Car.GetComponents<UStaticMeshComponent>(Comps);
	for (UStaticMeshComponent* C : Comps)
	{
		if (!C || C->GetFName() != TEXT("AltBody") || !C->GetStaticMesh()) continue;
		const TArray<FName> Slots = C->GetMaterialSlotNames();
		for (int32 i = 0; i < Slots.Num(); ++i) if (Slots[i].ToString().StartsWith(TEXT("Paint"))) C->SetMaterial(i, M);
	}
}

// --- per frame --------------------------------------------------------------------------------------

void FSkyCourseRaceImpl::Tick(float DeltaSeconds)
{
	const double Dt = FMath::Min((double)DeltaSeconds, 0.05);
	T += Dt;
	if (Phase == EPhase::Countdown && T >= COUNTDOWN)
	{
		Phase = EPhase::Racing;
		for (FRacer& R : Racers)
		{
			ASkysterCar* Car = R.Car.Get();
			if (!Car) continue;
			R.LapStart = 0;
			if (R.bPlayer && !Drives(R)) Held.Restore(*Car);
			else Car->TestStop = 0.f;
			// the test autopilot races the player's car as the opponents' equal: level 6 minus flight, in memory only (the
			// car's own level comes back the next time it changes; the progress save is never written here)
			if (R.bPlayer && Drives(R)) { FSkyCaps Cp = Skyster::CapsFor(Skyster::NumLevels - 1); Cp.bFlight = false; Car->ApplyCaps(Cp); }
		}
		bHolding = false;
		Note(TEXT("GO"));
	}
	// where everyone is, gates crossed, recoveries
	for (FRacer& R : Racers)
	{
		ASkysterCar* Car = R.Car.Get();
		if (!Car) continue;
		const FVector P = Car->Pos;
		Locate(R, *Car, Dt);
		if (Phase != EPhase::Countdown)
		{
			Gates(R, R.Prev, P, Dt);
			if (!R.bFinished) Recover(R, *Car, Dt);
		}
		R.Prev = Car->Pos;
	}
	Contacts();
	Places();
	// the drivers
	for (FRacer& R : Racers)
	{
		ASkysterCar* Car = R.Car.Get();
		if (!Car) continue;
		Assists(R, *Car, Dt);
		if (Phase == EPhase::Countdown)
		{
			Car->bRaceResetHit = false;
			if (R.bAI || Drives(R)) Hold(*Car);
			// not on the deck (the track's collision was still cooking when it was placed): put it back on its slot
			if ((R.Vert < -1.0 || R.D2 > 4.0 * 4.0) && T - R.RespawnT > 0.5 && T < COUNTDOWN - 0.4)
			{
				Car->TestTeleport(R.Slot.GetLocation() + FVector(0, 0, 60), (float)R.Slot.Rotator().Yaw);
				R.Prev = Car->Pos;
				R.RespawnT = T;
				Note(FString::Printf(TEXT("%s re-seated on its grid slot"), *R.Name));
			}
			continue;
		}
		if (Drives(R)) Drive(R, *Car, Dt);
	}
	// the red trim glows as the cars go by
	if (ASkyCourseTrack* Tr = Track.Get())
	{
		GlowPts.Reset();
		for (const FRacer& R : Racers) if (const ASkysterCar* C = R.Car.Get()) GlowPts.Add(C->GetActorLocation());
		Tr->UpdateGlow(GlowPts, (float)Dt);
	}
	// done when everyone is home, or a while after the player
	if (Phase == EPhase::Racing)
	{
		bool bAll = true;
		for (const FRacer& R : Racers) bAll &= R.bFinished || !R.Car.IsValid();
		const FRacer* P = Racers.IsValidIndex(PlayerIdx) ? &Racers[PlayerIdx] : nullptr;
		if (bAll || (P && P->bFinished && Clock() - P->FinishT > 60.0))
		{
			Phase = EPhase::Done;
			DoneT = T;
			Note(TEXT("race over"));
		}
	}
}

// Find the car on the course: the nearest centre-line frame within a window of where it was, across segment joins
// (into any branch), so a car can't jump to another part of the course that happens to be close (a loop's exit).
void FSkyCourseRaceImpl::SearchFwd(int32 Sg, int32 From, int32 Budget, const FVector& P, FBest& Best, int32 Depth) const
{
	const TArray<FSkyFrame>& Fr = B.Segs[Sg].Frames;
	int32 i = FMath::Max(0, From);
	for (; i < Fr.Num() && Budget > 0; ++i, --Budget)
	{
		const double D = FVector::DistSquared(P, Fr[i].P);
		if (D < Best.D2) { Best.D2 = D; Best.Seg = Sg; Best.I = i; }
	}
	if (Budget > 0 && Depth < 4) for (int32 n : B.Segs[Sg].Next) if (B.Segs.IsValidIndex(n)) SearchFwd(n, 1, Budget, P, Best, Depth + 1);
}

void FSkyCourseRaceImpl::SearchBack(int32 Sg, int32 From, int32 Budget, const FVector& P, FBest& Best, int32 Depth) const
{
	const TArray<FSkyFrame>& Fr = B.Segs[Sg].Frames;
	int32 i = FMath::Min(From, Fr.Num() - 1);
	for (; i >= 0 && Budget > 0; --i, --Budget)
	{
		const double D = FVector::DistSquared(P, Fr[i].P);
		if (D < Best.D2) { Best.D2 = D; Best.Seg = Sg; Best.I = i; }
	}
	if (Budget > 0 && Depth < 4) for (int32 p : X[Sg].Prev) SearchBack(p, B.Segs[p].Frames.Num() - 2, Budget, P, Best, Depth + 1);
}

void FSkyCourseRaceImpl::Locate(FRacer& R, const ASkysterCar& Car, double Dt)
{
	const FVector P = Car.Pos;
	R.Frame = FMath::Clamp(R.Frame, 0, B.Segs[R.Seg].Frames.Num() - 1);
	FBest Best{ FVector::DistSquared(P, B.Segs[R.Seg].Frames[R.Frame].P), R.Seg, R.Frame };
	SearchFwd(R.Seg, R.Frame + 1, SEARCH, P, Best, 0);
	SearchBack(R.Seg, R.Frame - 1, SEARCH, P, Best, 0);
	// a split's branches all start at one point with their decks overlapping, so the car may be on another branch than
	// the tracker guessed at the fork: look along the sibling branches too
	if (X[R.Seg].Split != INDEX_NONE)
	{
		for (int32 Pv : X[R.Seg].Prev)
		{
			for (int32 Sib : B.Segs[Pv].Next) if (Sib != R.Seg && X.IsValidIndex(Sib) && X[Sib].Split != INDEX_NONE) SearchFwd(Sib, 0, R.Frame + SEARCH, P, Best, 3);
		}
	}
	R.D2 = Best.D2;
	if (Best.Seg != R.Seg)
	{
		const int32 Old = R.Seg;
		R.Seg = Best.Seg;
		// round the end of the lap into the start piece again (and back out of it)
		if (B.bLapCourse && Best.Seg == 0 && R.Ri != INDEX_NONE && R.Ri == R.Route.Segs.Num() - 1) R.bWrapped = true;
		if (B.bLapCourse && Old == 0 && R.Route.Segs.Num() && Best.Seg == R.Route.Segs.Last()) R.bWrapped = false;
		// back before a split (reversing out of a branch): it chooses again
		const TArray<int32>& Nx = B.Segs[R.Seg].Next;
		if (Nx.Num() > 1 && X.IsValidIndex(Nx[0]) && R.Entered.IsValidIndex(X[Nx[0]].Split)) R.Entered[X[Nx[0]].Split] = false;
		R.Ri = R.Route.Segs.Find(R.Seg);
	}
	R.Frame = Best.I;
	const FSkyFrame& F = B.Segs[R.Seg].Frames[R.Frame];
	const FVector D = P - F.P;
	R.Lat = FVector::DotProduct(D, F.L);
	R.Vert = FVector::DotProduct(D, F.U);
	// into a split's branch: once the car is clearly on that branch's deck and off the others' (or near the end of the
	// lead-in), the route follows it, and a branch the gates show closed sends the car back to the split
	const FSegX& Sx = X[R.Seg];
	if (Sx.Split != INDEX_NONE && Phase != EPhase::Countdown && R.Entered.IsValidIndex(Sx.Split) && !R.Entered[Sx.Split])
	{
		const int32 Sp = Sx.Split, Br = Sx.Branch;
		bool bClear = FMath::Abs(R.Lat) <= F.Width * 0.5 + 0.5 || R.Frame >= B.Segs[R.Seg].Frames.Num() - 6;
		for (int32 b = 0; b < B.Splits[Sp].LeadSegs.Num() && bClear; ++b)
		{
			const int32 Sib = B.Splits[Sp].LeadSegs[b];
			if (b == Br || !B.Segs.IsValidIndex(Sib)) continue;
			const TArray<FSkyFrame>& Fs = B.Segs[Sib].Frames;
			FBest Sb{ TNumericLimits<double>::Max(), Sib, 0 };
			for (int32 i = 0; i < Fs.Num() && i <= R.Frame + SEARCH; ++i) { const double Dd = FVector::DistSquared(P, Fs[i].P); if (Dd < Sb.D2) { Sb.D2 = Dd; Sb.I = i; } }
			if (Sb.D2 < TNumericLimits<double>::Max() && FMath::Abs(FVector::DotProduct(P - Fs[Sb.I].P, Fs[Sb.I].L)) <= Fs[Sb.I].Width * 0.5 + 0.3) bClear = R.Frame >= B.Segs[R.Seg].Frames.Num() - 6;
		}
		if (bClear && R.Frame >= 6)
		{
			R.Entered[Sp] = true;
			const bool bClosed = B.Splits[Sp].Gate != ESkyGate::None && Shown.IsValidIndex(Sp) && Shown[Sp].IsValidIndex(Br) && !Shown[Sp][Br];
			R.Branches.Add(FString::Printf(TEXT("lap %d: split %d branch %d (%s, gates showing lap %d)"), R.Lap, Sp, Br, bClosed ? TEXT("closed") : TEXT("open"), ShownLap));
			Note(FString::Printf(TEXT("%s takes split %d branch %d (%s) on its lap %d: %s (gates show lap %d)"), *R.Name, Sp, Br,
				BranchDir.IsValidIndex(Sp) && BranchDir[Sp].IsValidIndex(Br) ? *BranchDir[Sp][Br] : TEXT("?"), R.Lap, bClosed ? TEXT("CLOSED") : TEXT("open"), ShownLap));
			if (R.Route.Choice.IsValidIndex(Sp) && R.Route.Choice[Sp] != Br && !(bClosed && Drives(R)))
			{
				TArray<int32> C = R.Route.Choice;
				C[Sp] = Br;
				BuildRoute(R, C);
			}
			if (bClosed && R.WrongSplit == INDEX_NONE && !R.bFinished)
			{
				R.WrongSplit = Sp;
				R.WrongT = 0;
				++R.WrongWays;
				Note(FString::Printf(TEXT("%s: wrong way into split %d branch %d (closed on lap %d)"), *R.Name, Sp, Br, ShownLap));
			}
		}
	}
	if (R.Ri != INDEX_NONE)
	{
		const double Along = FMath::Clamp(FVector::DotProduct(D, F.F), -0.5, 0.5);
		R.S = (R.bWrapped && R.Ri == 0 ? R.Route.Len : R.Route.At[R.Ri]) + X[R.Seg].Cum[R.Frame] + Along;
	}
	if (!R.bFinished) R.Progress = (R.Lap - 1) + FMath::Clamp((R.S - R.Route.GateS) / R.Route.LapLen(), -0.99, 1.0);
	// where and how it took off, the moment it leaves the ground (for the off-track log line)
	if (R.AI.bWasGrounded && !Car.bGrounded) { R.AI.LaunchLat = R.Lat; R.AI.LaunchVLat = FVector::DotProduct(Car.Vel, F.L); }
	R.AI.bWasGrounded = Car.bGrounded;
	// driving the wrong way down the track
	const double VAlong = FVector::DotProduct(Car.Vel, F.F);
	R.ReverseT = (Car.bGrounded && VAlong < -5.0) ? R.ReverseT + Dt : 0.0;
}

void FSkyCourseRaceImpl::Gates(FRacer& R, const FVector& A, const FVector& Bp, double Dt)
{
	if (R.bFinished || FVector::DistSquared(A, Bp) > 40.0 * 40.0) return;
	for (int32 g = 0; g < B.Gates.Num(); ++g)
	{
		const FSkyBaked::FGate& Gt = B.Gates[g];
		double Frac = 0;
		if (!Crossed(Gt.At, A, Bp, Frac)) continue;
		const double Tc = FMath::Max(0.0, Clock() - Dt + Frac * Dt);
		if (Gt.Type == ESkyPiece::Start)
		{
			if (!R.bStarted)
			{
				R.bStarted = true;
				R.SafeSeg = Gt.Seg;
				R.SafeFrame = GateFrame[g];
				Note(FString::Printf(TEXT("%s over the start line"), *R.Name));
			}
			else if (B.bLapCourse) LapDone(R, Tc);
		}
		else if (Gt.Type == ESkyPiece::Finish)
		{
			if (!B.bLapCourse && R.bStarted) LapDone(R, Tc);
		}
		else if (Gt.Type == ESkyPiece::Checkpoint && R.bStarted)
		{
			const int32 Want = R.Route.Checks.IsValidIndex(R.NextCheck) ? R.Route.Checks[R.NextCheck] : INDEX_NONE;
			if (g == Want)
			{
				R.Passed[g] = true;
				++R.NextCheck;
				while (R.Route.Checks.IsValidIndex(R.NextCheck) && R.Passed[R.Route.Checks[R.NextCheck]]) ++R.NextCheck;
				const double Split = Tc - R.LapStart;
				R.Splits.Add(Split);
				R.LapSplits[g] = Split;
				R.SafeSeg = Gt.Seg;
				R.SafeFrame = GateFrame[g];
				// the delta: against the player's best lap on this course, else this race's best lap
				double Ref = -1;
				if (R.bPlayer && PbSplits.Contains(g)) Ref = PbSplits[g];
				else if (R.BestSplits[g] > 0) Ref = R.BestSplits[g];
				R.SplitRef = Ref;
				R.SplitDelta = Ref > 0 ? Split - Ref : 0;
				R.SplitT = T;
				R.SplitGate = Gt.Index;
				Note(FString::Printf(TEXT("%s checkpoint %d, lap %d: %s%s"), *R.Name, Gt.Index + 1, R.Lap, *TimeStr(Split),
					Ref > 0 ? *FString::Printf(TEXT(" (%+.2f)"), Split - Ref) : TEXT("")));
			}
			else if (R.Route.Checks.Contains(g) && !R.Passed[g])
			{
				R.MissT = T;
				Note(FString::Printf(TEXT("%s skipped a checkpoint before checkpoint %d"), *R.Name, Gt.Index + 1));
			}
		}
	}
}

void FSkyCourseRaceImpl::LapDone(FRacer& R, double Tc)
{
	if (R.NextCheck < R.Route.Checks.Num())
	{
		R.MissT = T;
		Note(FString::Printf(TEXT("%s crossed the line with %d checkpoint(s) missed: no lap"), *R.Name, R.Route.Checks.Num() - R.NextCheck));
		return;
	}
	// backed over the line and drove through it again: not a lap
	if (B.bLapCourse && !R.bWrapped && R.S < R.Route.GateS + 0.5 * R.Route.Len) return;
	const double Lt = Tc - R.LapStart;
	R.LapTimes.Add(Lt);
	R.LastLap = Lt;
	R.LapStart = Tc;
	R.LapT = T;
	R.bLapBest = R.BestLap < 0 || Lt < R.BestLap;
	if (R.bLapBest) { R.BestLap = Lt; R.BestSplits = R.LapSplits; }
	if (R.bPlayer)
	{
		Owner->Best = R.BestLap;
		if (PbLap < 0 || Lt < PbLap)
		{
			PbLap = Lt;
			PbSplits.Reset();
			for (int32 g = 0; g < R.LapSplits.Num(); ++g) if (R.LapSplits[g] > 0) PbSplits.Add(g, R.LapSplits[g]);
			bNewPbLap = true;
		}
	}
	Note(FString::Printf(TEXT("%s lap %d: %s%s"), *R.Name, R.Lap, *TimeStr(Lt), R.bLapBest ? TEXT(" (best)") : TEXT("")));
	++R.Lap;
	R.Splits.Reset();
	for (double& V : R.LapSplits) V = -1;
	for (bool& V : R.Passed) V = false;
	for (bool& V : R.Entered) V = false;
	R.bWrapped = false;
	R.NextCheck = 0;
	// the line it just crossed is where it comes back to now, not the last lap's last checkpoint
	if (StartGate != INDEX_NONE && B.bLapCourse) { R.SafeSeg = B.Gates[StartGate].Seg; R.SafeFrame = GateFrame[StartGate]; }
	if (R.Lap > Laps)
	{
		R.bFinished = true;
		R.FinishT = Tc;
		R.Lap = Laps;
		Note(FString::Printf(TEXT("%s FINISHED in %s"), *R.Name, *TimeStr(Tc)));
		if (R.bPlayer)
		{
			if (PbRace < 0 || Tc < PbRace) { PbRace = Tc; bNewPbRace = true; }
			SaveTimes();
		}
		return;
	}
	BuildRoute(R, ChoiceFor(R, R.Lap));
	if (R.bPlayer || PlayerIdx == INDEX_NONE) UpdateGates(R.Lap);
}

// Off the track for a while, fallen far below it, wrecked, stuck, or into a closed branch: back on the course.
void FSkyCourseRaceImpl::Recover(FRacer& R, ASkysterCar& Car, double Dt)
{
	// the car's reset (View / R): back to the last good spot, like Trackmania's respawn key
	if (Car.bRaceResetHit)
	{
		Car.bRaceResetHit = false;
		if (Phase == EPhase::Racing && T - R.RespawnT > 1.0) { Respawn(R, TEXT("reset button")); return; }
	}
	NoteGood(R, Car);
	if (R.WrongSplit != INDEX_NONE)
	{
		R.WrongShowT = T;
		if ((R.WrongT += Dt) > WRONG_T)
		{
			const int32 Sp = R.WrongSplit;
			const int32 Lead = B.Splits[Sp].LeadSegs.Num() ? B.Splits[Sp].LeadSegs[0] : 0;
			// it chooses again at that split: the branch its lap (or the gates) say, not the closed one it went into
			R.Entered[Sp] = false;
			BuildRoute(R, ChoiceFor(R, R.Lap));
			// the split's entrance: 10 m before the branches part (the player, in the middle, to choose again). A car
			// the race drives goes 30 m back, lined up on the slot its branch leaves from: from a standstill 10 m short
			// of the fork, in its own lane, it couldn't get across to a branch on the far side, and went wrong again
			// (and again: one car 48 times in a test)
			const bool bAuto = Drives(R);
			int32 Sg = Lead, I = 0;
			if (X[Lead].Prev.Num()) { Sg = X[Lead].Prev[0]; I = FMath::Max(0, B.Segs[Sg].Frames.Num() - 1 - (bAuto ? 60 : 20)); }
			double Lat = TNumericLimits<double>::Max();
			if (bAuto && R.Route.Choice.IsValidIndex(Sp) && B.Splits[Sp].LeadSegs.IsValidIndex(R.Route.Choice[Sp]))
			{
				const int32 Mine = B.Splits[Sp].LeadSegs[R.Route.Choice[Sp]];
				const FSkyFrame& Fs = B.Segs[Sg].Frames[I];
				const FSkyFrame& Fe = B.Segs[Sg].Frames.Last();
				// the slot's offset at the fork, carried back to this frame (the segment before a split runs straight)
				Lat = X[Mine].ForkOff + FVector::DotProduct(Fe.P - Fs.P, Fs.L);
			}
			RespawnAt(R, Sg, I, 0.0, TEXT("wrong way at a split"), Lat);
		}
		return;
	}
	const FSkyFrame& F = B.Segs[R.Seg].Frames[R.Frame];
	const double Excess = FMath::Abs(R.Lat) - F.Width * 0.5;
	const bool bOff = Excess > OFF_LAT || R.Vert < -3.0 || (R.Vert > 7.0 && F.U.Z < 0.5) || R.Vert > 45.0 || R.D2 > 30.0 * 30.0;
	const bool bFell = Car.Pos.Z < F.P.Z - 12.0;
	if (bOff && R.OffT <= 0)
	{
		R.OffInfo = FString::Printf(TEXT("left at seg %d (%s) frame %d: lat %.1f of %.1f, vert %.1f, %.0f mph, %s; sideways %.1f m/s, heading %+.0f deg, steer %+.2f, boost %d, launch lat %.1f vlat %.1f"),
			R.Seg, SkyCourse::PieceName(B.Segs[R.Seg].Type), R.Frame, R.Lat, F.Width * 0.5, R.Vert, Car.GetSpeedMph(), *Car.GetMode(),
			FVector::DotProduct(Car.Vel, F.L), FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(Car.Fwd, F.L), FVector::DotProduct(Car.Fwd, F.F))),
			Car.TestSteer, Car.bTestBoost ? 1 : 0, R.AI.LaunchLat, R.AI.LaunchVLat);
	}
	R.OffT = bOff ? R.OffT + Dt : 0.0;
	if ((bFell && R.OffT > 0.4) || R.OffT > OFF_T) { Respawn(R, *FString::Printf(TEXT("%s; %s"), bFell ? TEXT("fell") : TEXT("off the track"), *R.OffInfo)); return; }
	if (!Car.bAlive)
	{
		if ((R.DeadT += Dt) > 1.5) Respawn(R, TEXT("wrecked"));
		return;
	}
	R.DeadT = 0;
	if (R.bAI && Phase == EPhase::Racing)
	{
		R.SlowT = Car.Speed < 2.0 ? R.SlowT + Dt : 0.0;
		if (R.SlowT > 3.0) { Respawn(R, TEXT("stuck")); return; }
		// going nowhere (spinning against a rail, sliding back down a wall). The distance it drove too: round the lap's
		// end into the start piece the progress can read wrong for a moment, and a car doing 33 m/s was put back once
		if (R.AI.WatchP < -100.0) R.AI.WatchP = R.Progress;   // just put back on the track: measure from here
		R.AI.WatchDist += Car.Speed * Dt;
		if ((R.AI.WatchT += Dt) > 6.0)
		{
			const double Moved = (R.Progress - R.AI.WatchP) * R.Route.LapLen();
			const double Drove = R.AI.WatchDist;
			R.AI.WatchT = 0;
			R.AI.WatchDist = 0;
			R.AI.WatchP = R.Progress;
			if (Moved < 10.0 && Drove < 120.0) { Respawn(R, TEXT("no progress")); return; }
		}
	}
}

void FSkyCourseRaceImpl::Respawn(FRacer& R, const TCHAR* Why)
{
	ASkysterCar* Car = R.Car.Get();
	if (!Car) return;
	if (Drives(R)) DumpTrace(R, Why);
	if (R.SafeSeg == INDEX_NONE)
	{
		// before the start line: back to its grid slot
		Car->TestTeleport(R.Slot.GetLocation() + FVector(0, 0, 60), (float)R.Slot.Rotator().Yaw);
		R.Seg = 0;
		R.Frame = NearestOnSeg(0, Car->Pos);
		AfterTeleport(R, Why, TEXT("its grid slot"));
		return;
	}
	if (!RespawnGood(R, Why)) RespawnAt(R, R.SafeSeg, R.SafeFrame, 5.0, Why);
}

// Lakitu-style recovery (Design/RaceHandling.md): the race keeps the last good spots each car drove this lap (level-ish
// deck, wheels down, well inside the edges; not on a jump, loop or corkscrew), and a fall puts it back about 10 m before
// the last one, moving. It's always somewhere the car already was, so a fall can't be a shortcut.
void FSkyCourseRaceImpl::NoteGood(FRacer& R, const ASkysterCar& Car)
{
	if (R.GoodLap != R.Lap) { R.Good.Reset(); R.GoodLap = R.Lap; }
	if (R.Ri == INDEX_NONE || R.WrongSplit != INDEX_NONE || !Car.bGrounded || !Car.bAlive || !B.Segs.IsValidIndex(R.Seg)) return;
	const TArray<FSkyFrame>& Fr = B.Segs[R.Seg].Frames;
	if (!Fr.IsValidIndex(R.Frame)) return;
	const FSkyFrame& F = Fr[R.Frame];
	const FSegX& Sx = X[R.Seg];
	if (!F.bDeck || F.U.Z < 0.8 || Sx.bJump || Sx.bLoop || Sx.bCork) return;
	if (FMath::Abs(R.Lat) > F.Width * 0.5 - 1.6 || FMath::Abs(R.Vert) > 1.2) return;
	if (R.Good.Num() && FMath::Abs(R.S - R.Good.Last().S) < 2.0) return;
	FRacer::FGood Spot;
	Spot.Seg = R.Seg;
	Spot.Frame = R.Frame;
	Spot.S = R.S;
	Spot.V = Car.Speed;
	R.Good.Add(Spot);
	if (R.Good.Num() > 32) R.Good.RemoveAt(0);
}

bool FSkyCourseRaceImpl::RespawnGood(FRacer& R, const TCHAR* Why)
{
	ASkysterCar* Car = R.Car.Get();
	if (!Car || R.Good.Num() == 0) return false;
	// back from the newest spot by GOOD_BACK (while the spots run in order along the route)
	int32 k = R.Good.Num() - 1;
	const double S0 = R.Good[k].S;
	while (k > 0 && R.Good[k - 1].S < R.Good[k].S && S0 - R.Good[k].S < GOOD_BACK) --k;
	const FRacer::FGood Spot = R.Good[k];
	R.Good.SetNum(k + 1);   // a second fall right away goes from here, not from where it fell
	if (!B.Segs.IsValidIndex(Spot.Seg) || !B.Segs[Spot.Seg].Frames.IsValidIndex(Spot.Frame)) return false;
	// speed: most of what it had there, but what a jump or loop just ahead needs, and no more than the bend allows
	double V = FMath::Max(KEEP_MIN, KEEP_V * Spot.V);
	double Cap = X[Spot.Seg].VMax.IsValidIndex(Spot.Frame) && X[Spot.Seg].VMax[Spot.Frame] > 0 ? X[Spot.Seg].VMax[Spot.Frame] * 0.9 : MAX_SPEED;
	int32 Ri = R.Route.Segs.Find(Spot.Seg);
	double Ahead = X[Spot.Seg].Len - (X[Spot.Seg].Cum.IsValidIndex(Spot.Frame) ? X[Spot.Seg].Cum[Spot.Frame] : 0.f);
	for (int32 n = Ri + 1; Ri != INDEX_NONE && n < R.Route.Segs.Num() && Ahead < 150.0; ++n)
	{
		const FSegX& Nx = X[R.Route.Segs[n]];
		if (Nx.NeedV > 0) V = FMath::Max(V, (double)Nx.NeedV);
		if (Nx.CapV > 0) Cap = FMath::Min(Cap, (double)Nx.CapV);
		Ahead += Nx.Len;
	}
	V = FMath::Clamp(V, 0.0, FMath::Max(KEEP_MIN, Cap));
	RespawnAt(R, Spot.Seg, Spot.Frame, 0.0, Why, R.bPlayer ? 0.0 : TNumericLimits<double>::Max());
	Car->Vel = B.Segs[R.Seg].Frames[R.Frame].F * V;
	return true;
}

ESkyAssist FSkyCourseRaceImpl::AssistFor(const FRacer& R) const
{
	if (!R.bPlayer) return ESkyAssist::Off;   // the opponents drive themselves
	const int32 Forced = CVarAssist.GetValueOnGameThread();
	if (Forced >= 0) return (ESkyAssist)FMath::Clamp(Forced, 0, 2);
	return Drives(R) ? ESkyAssist::Off : PlayerAssist;   // the test autopilot drives as in 0.2.2 unless a test says otherwise
}

void FSkyCourseRaceImpl::ClearRaceHooks(ASkysterCar& Car)
{
	Car.bInCourseRace = false;
	Car.RaceAssist = 0;
	Car.RaceSteerNudge = 0.f;
	Car.bRaceAirAim = false;
	Car.RaceAirPull = FVector::ZeroVector;
	Car.RaceSpeedScale = 1.f;
	Car.bRaceResetHit = false;
}

// Every tick, before the cars tick: the race hooks on the car (SkysterCar.h). Slipstream for everyone, the AI rubber
// band (course setting), and the player's smart steering and landing help.
void FSkyCourseRaceImpl::Assists(FRacer& R, ASkysterCar& Car, double Dt)
{
	const ESkyAssist A = AssistFor(R);
	Car.bInCourseRace = true;
	Car.RaceAssist = (uint8)A;
	const bool bGo = Phase == EPhase::Racing && !R.bFinished;
	// slipstream: right behind another car (same way, close across), up to DRAFT more top speed
	double Want = 0;
	if (bGo && Car.bGrounded && Car.Speed > 15)
	{
		for (const FRacer& O : Racers)
		{
			const ASkysterCar* Oc = O.Car.Get();
			if (&O == &R || !Oc) continue;
			const FVector D = Oc->Pos - Car.Pos;
			const double Along = FVector::DotProduct(D, Car.Fwd), Side = FMath::Abs(FVector::DotProduct(D, Car.Left));
			if (Along > 3.0 && Along < DRAFT_LEN && Side < DRAFT_SIDE && FVector::DotProduct(Oc->Fwd, Car.Fwd) > 0.8)
				Want = FMath::Max(Want, 1.0 - (Along - 3.0) / (DRAFT_LEN - 3.0));
		}
	}
	R.Draft += (Want - R.Draft) * FMath::Min(1.0, Dt * 3.0);
	double Scale = 1.0 + DRAFT * R.Draft;
	// rubber band: an AI well ahead of the player eases off, one well behind pushes (top speed only: its curve speeds
	// are planned from the track and don't change)
	const FRacer* P = Racers.IsValidIndex(PlayerIdx) ? &Racers[PlayerIdx] : nullptr;
	if (R.bAI && Course.bCatchUp && bGo && P && !P->bFinished && P->Progress >= 0 && R.Progress >= 0)
	{
		const double Gap = (R.Progress - P->Progress) * R.Route.LapLen();
		Scale *= Gap > 0 ? 1.0 - BAND * SmoothStep(BAND_FROM, BAND_FULL, Gap) : 1.0 + BAND * SmoothStep(BAND_FROM, BAND_FULL, -Gap);
	}
	Car.RaceSpeedScale = (float)Scale;
	const bool bTracked = R.Ri != INDEX_NONE && B.Segs.IsValidIndex(R.Seg) && B.Segs[R.Seg].Frames.IsValidIndex(R.Frame);
	// smart steering (Full): if the path would leave the deck within NUDGE_LOOK s, a nudge back toward the middle,
	// growing the closer it gets (halved while the car slides, so a drift stays yours)
	double Nudge = 0;
	if (A == ESkyAssist::Full && bGo && bTracked && Car.bGrounded && Car.Speed > 8)
	{
		const FSkyFrame& F = B.Segs[R.Seg].Frames[R.Frame];
		const double Room = F.Width * 0.5 - 1.6;   // the bumper and half the car
		const double Pred = R.Lat + FVector::DotProduct(Car.Vel, F.L) * NUDGE_LOOK;
		const double Over = FMath::Abs(Pred) - (Room - 1.0);
		if (Over > 0 && Room > 1.5)
		{
			// + steer = right; a car heading off the left edge (Pred > 0) is steered right
			Nudge = FMath::Sign(Pred) * NUDGE_MAX * FMath::Clamp(Over / 3.0, 0.0, 1.0);
			if (Car.bDrifting) Nudge *= 0.5;
		}
	}
	R.Nudge += (Nudge - R.Nudge) * FMath::Min(1.0, Dt * 8.0);
	Car.RaceSteerNudge = (float)R.Nudge;
	if (FMath::Abs(R.Nudge) > 0.05) R.NudgeT = T;
	// landing help (Light, Full): in the air over the track, wheels-down along the deck below (a jump's pad), drifting
	// gently toward its middle
	Car.bRaceAirAim = false;
	Car.RaceAirPull = FVector::ZeroVector;
	if (A != ESkyAssist::Off && bGo && bTracked && !Car.bGrounded && Car.bAlive)
	{
		int32 Sg = R.Seg, I = R.Frame;
		if (!B.Segs[Sg].Frames[I].bDeck && X[Sg].LandAt != INDEX_NONE && B.Segs[Sg].Frames.IsValidIndex(X[Sg].LandAt)) I = X[Sg].LandAt;
		const FSkyFrame& F = B.Segs[Sg].Frames[I];
		const double Lat = FVector::DotProduct(Car.Pos - F.P, F.L);
		const double Above = FVector::DotProduct(Car.Pos - F.P, F.U);
		if (F.U.Z > 0.5 && Above > 0.3 && Above < 40.0 && FMath::Abs(Lat) < F.Width * 0.5 + 6.0)
		{
			Car.bRaceAirAim = true;
			Car.RaceAimFwd = F.F;
			Car.RaceAimUp = F.U;
			const double VLat = FVector::DotProduct(Car.Vel, F.L);
			const double Pull = FMath::Clamp(-(0.8 * Lat + 1.2 * VLat), -AIR_PULL, AIR_PULL);
			Car.RaceAirPull = F.L * Pull;
		}
	}
}

// Put the car on the deck Ahead metres along the course from a frame, in its lane (the player in the middle), facing
// along the track, stopped (SpawnAt finds the deck under the point, resets the speed, a third of a tank).
void FSkyCourseRaceImpl::RespawnAt(FRacer& R, int32 Sg, int32 I, double Ahead, const TCHAR* Why, double Lat)
{
	ASkysterCar* Car = R.Car.Get();
	if (!Car || !B.Segs.IsValidIndex(Sg)) return;
	double Left = Ahead;
	while (Left > 0)
	{
		const TArray<FSkyFrame>& Fr = B.Segs[Sg].Frames;
		if (I + 1 < Fr.Num()) { Left -= X[Sg].Cum[I + 1] - X[Sg].Cum[I]; ++I; continue; }
		const int32 Ri = R.Route.Segs.Find(Sg);
		const int32 Nx = (Ri != INDEX_NONE && R.Route.Segs.IsValidIndex(Ri + 1)) ? R.Route.Segs[Ri + 1] : (B.Segs[Sg].Next.Num() ? B.Segs[Sg].Next[0] : INDEX_NONE);
		if (Nx == INDEX_NONE || Nx == 0) break;
		Sg = Nx;
		I = 0;
	}
	const FSkyFrame& F = B.Segs[Sg].Frames[I];
	const double Off = Lat < 1e9 ? FMath::Clamp(Lat, -FMath::Max(0.0, F.Width * 0.5 - 1.6), FMath::Max(0.0, F.Width * 0.5 - 1.6))
		: R.bPlayer ? 0.0 : R.Lane * FMath::Max(0.0, F.Width * 0.5 - 1.6);
	const FVector P = F.P + F.L * Off + F.U * 0.8;
	const double Yaw = -FMath::RadiansToDegrees(FMath::Atan2(F.F.Y, F.F.X));
	Car->TestTeleport(SkyCourse::ToUE(P), (float)Yaw);
	R.Seg = Sg;
	R.Frame = I;
	if (Sg != 0 || I > 0) R.bWrapped = false;
	AfterTeleport(R, Why, *FString::Printf(TEXT("seg %d frame %d"), Sg, I));
}

void FSkyCourseRaceImpl::AfterTeleport(FRacer& R, const TCHAR* Why, const TCHAR* Where)
{
	ASkysterCar* Car = R.Car.Get();
	FitRoute(R);
	// put back before a split it had already gone into this lap (a fall in a branch, back to the last checkpoint): it
	// chooses again there, by the gates as they show now (else it drives back into a branch they've since closed)
	if (R.Ri != INDEX_NONE)
	{
		bool bAny = false;
		for (int32 i = 0; i < B.Splits.Num(); ++i)
		{
			if (!R.Entered.IsValidIndex(i) || !R.Entered[i] || !R.Route.Choice.IsValidIndex(i) || !B.Splits[i].LeadSegs.IsValidIndex(R.Route.Choice[i])) continue;
			const int32 Li = R.Route.Segs.Find(B.Splits[i].LeadSegs[R.Route.Choice[i]]);
			if (Li != INDEX_NONE && Li > R.Ri) { R.Entered[i] = false; bAny = true; }
		}
		if (bAny && Drives(R)) RefreshChoice(R);
	}
	if (Car) R.Prev = Car->Pos;
	R.GhostUntil = T + GHOST_T;   // no shoving while it gets going again
	// the player's view dips to black and back, so being put back reads as a pick-up, not a jump cut
	if (Car && R.bPlayer)
		if (APlayerController* PC = Cast<APlayerController>(Car->GetController()))
			if (PC->PlayerCameraManager) PC->PlayerCameraManager->StartCameraFade(1.f, 0.f, 0.35f, FLinearColor::Black, false, false);
	R.OffT = R.SlowT = R.DeadT = R.WrongT = 0;
	R.WrongSplit = INDEX_NONE;
	R.RespawnT = T;
	++R.Respawns;
	R.AI.Steer = 0;
	R.AI.HopT = -1;
	R.AI.JumpSeg = INDEX_NONE;
	R.AI.bLineSet = false;
	R.AI.bYawSet = false;
	R.AI.YawRate = 0;
	R.AI.TraceNum = 0;
	R.AI.WatchT = 0;
	R.AI.WatchDist = 0;
	R.AI.WatchP = -1000.0;   // re-measured once the tracker has it at its new place
	Note(FString::Printf(TEXT("%s back on the track at %s (%s)"), *R.Name, Where, Why));
}

// Cars bump each other: each is two balls along its length; overlapping cars are pushed apart (along their decks, so
// nobody is shoved into or off the surface) and swap the closing speed with a little bounce. The cars' own sweeps
// ignore each other (no collision on their parts), so a car never drives on another as ground or treats one as a wall
// to bounce off at full speed (SkysterCar::Collide knows only fixed walls).
void FSkyCourseRaceImpl::Contacts()
{
	for (int32 a = 0; a < Racers.Num(); ++a)
	{
		ASkysterCar* A = Racers[a].Car.Get();
		if (!A || !A->bAlive) continue;
		for (int32 b = a + 1; b < Racers.Num(); ++b)
		{
			ASkysterCar* Bc = Racers[b].Car.Get();
			if (!Bc || !Bc->bAlive) continue;
			if (FVector::DistSquared(A->Pos, Bc->Pos) > 100.0) continue;
			const FRacer& Ra = Racers[a];
			const FRacer& Rb = Racers[b];
			if (T < Ra.GhostUntil || T < Rb.GhostUntil) continue;   // just put back on the track: a ghost for a moment
			double Over = 0;
			FVector N = FVector::ZeroVector;
			for (const double Ka : { -1.0, 1.0 })
			{
				const FVector Ca = A->Pos + A->Up * 0.6 + A->Fwd * (Ra.HalfLen * Ka);
				for (const double Kb : { -1.0, 1.0 })
				{
					const FVector Cb = Bc->Pos + Bc->Up * 0.6 + Bc->Fwd * (Rb.HalfLen * Kb);
					const FVector D = Ca - Cb;
					const double L = D.Size();
					const double O = Ra.Radius + Rb.Radius - L;
					if (O > Over && L > 1e-3) { Over = O; N = D / L; }
				}
			}
			if (Over <= 0) continue;
			Racers[a].BumpT = Racers[b].BumpT = T;
			auto Along = [](const ASkysterCar* C, const FVector& V) { if (!C->bGrounded) return V; const FVector P = V - C->Up * FVector::DotProduct(V, C->Up); return P.SizeSquared() > 1e-6 ? P.GetSafeNormal() : V; };
			const FVector Na = Along(A, N), Nb = Along(Bc, -N);
			A->Pos += Na * (Over * 0.5);
			Bc->Pos += Nb * (Over * 0.5);
			const double Vn = FVector::DotProduct(A->Vel - Bc->Vel, N);
			if (Vn < 0)
			{
				const double J = -(1.0 + 0.25) * Vn * 0.5;
				A->Vel += Na * J;
				Bc->Vel += Nb * J;
				if (-Vn > 3.0) ++Bumps;
			}
		}
	}
}

void FSkyCourseRaceImpl::Places()
{
	Order.Reset();
	for (int32 i = 0; i < Racers.Num(); ++i) Order.Add(i);
	// finished first by time, then by how far round
	auto Before = [this](int32 A, int32 Bb)
	{
		const FRacer& Ra = Racers[A];
		const FRacer& Rb = Racers[Bb];
		if (Ra.bFinished != Rb.bFinished) return Ra.bFinished;
		if (Ra.bFinished) return Ra.FinishT < Rb.FinishT;
		return Ra.Progress > Rb.Progress;
	};
	for (int32 i = 1; i < Order.Num(); ++i)
	{
		const int32 V = Order[i];
		int32 j = i - 1;
		while (j >= 0 && Before(V, Order[j])) { Order[j + 1] = Order[j]; --j; }
		Order[j + 1] = V;
	}
	for (int32 k = 0; k < Order.Num(); ++k) Racers[Order[k]].Place = k + 1;
}

// --- results and best times ------------------------------------------------------------------------

TArray<ASkyCourseRace::FResult> FSkyCourseRaceImpl::Results() const
{
	TArray<ASkyCourseRace::FResult> Out;
	for (int32 k = 0; k < Order.Num(); ++k)
	{
		const FRacer& R = Racers[Order[k]];
		ASkyCourseRace::FResult Res;
		Res.Name = R.Name;
		Res.bPlayer = R.bPlayer;
		Res.Lap = R.Lap;
		Res.Time = R.bFinished ? R.FinishT : -1.0;
		Res.LapTimes = R.LapTimes;
		Res.Splits = R.Splits;
		Res.Place = R.Place;
		Res.bFinished = R.bFinished;
		Out.Add(Res);
	}
	return Out;
}

FString FSkyCourseRaceImpl::ResultsJson() const
{
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("course"), Course.Name);
	Root->SetStringField(TEXT("phase"), Phase == EPhase::Countdown ? TEXT("countdown") : Phase == EPhase::Racing ? TEXT("racing") : TEXT("done"));
	Root->SetNumberField(TEXT("time"), Clock());
	Root->SetNumberField(TEXT("laps"), Laps);
	Root->SetBoolField(TEXT("lap_course"), B.bLapCourse);
	Root->SetNumberField(TEXT("lap_length"), B.Length);
	Root->SetNumberField(TEXT("gates_lap"), ShownLap);
	Root->SetNumberField(TEXT("contacts"), Bumps);
	Root->SetNumberField(TEXT("tick_ms_avg"), Ticks ? TickSecs / Ticks * 1000.0 : 0.0);
	Root->SetNumberField(TEXT("tick_ms_max"), TickMax * 1000.0);
	TArray<TSharedPtr<FJsonValue>> Cars;
	for (int32 k = 0; k < Order.Num(); ++k)
	{
		const FRacer& R = Racers[Order[k]];
		const ASkysterCar* C = R.Car.Get();
		TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
		O->SetStringField(TEXT("name"), R.Name);
		O->SetBoolField(TEXT("player"), R.bPlayer);
		O->SetBoolField(TEXT("ai"), R.bAI);
		O->SetNumberField(TEXT("skill"), R.Skill);
		O->SetStringField(TEXT("vehicle"), C ? C->GetVehicleName() : TEXT(""));
		O->SetStringField(TEXT("actor"), C ? C->GetName() : TEXT(""));
		O->SetNumberField(TEXT("place"), R.Place);
		O->SetNumberField(TEXT("lap"), R.Lap);
		O->SetBoolField(TEXT("finished"), R.bFinished);
		O->SetNumberField(TEXT("time"), R.bFinished ? R.FinishT : -1.0);
		O->SetNumberField(TEXT("best_lap"), R.BestLap);
		O->SetNumberField(TEXT("progress"), R.Progress);
		O->SetNumberField(TEXT("respawns"), R.Respawns);
		O->SetNumberField(TEXT("wrong_ways"), R.WrongWays);
		O->SetNumberField(TEXT("speed_mph"), C ? C->GetSpeedMph() : 0.0);
		O->SetNumberField(TEXT("seg"), R.Seg);
		O->SetNumberField(TEXT("lat"), R.Lat);
		TArray<TSharedPtr<FJsonValue>> Lt, Sp, Br;
		for (double V : R.LapTimes) Lt.Add(MakeShared<FJsonValueNumber>(V));
		for (double V : R.Splits) Sp.Add(MakeShared<FJsonValueNumber>(V));
		for (const FString& V : R.Branches) Br.Add(MakeShared<FJsonValueString>(V));
		O->SetArrayField(TEXT("lap_times"), Lt);
		O->SetArrayField(TEXT("splits"), Sp);
		O->SetArrayField(TEXT("branches"), Br);
		Cars.Add(MakeShared<FJsonValueObject>(O));
	}
	Root->SetArrayField(TEXT("cars"), Cars);
	TSharedRef<FJsonObject> Pb = MakeShared<FJsonObject>();
	Pb->SetStringField(TEXT("file"), TimesPath);
	Pb->SetNumberField(TEXT("best_lap"), PbLap);
	Pb->SetNumberField(TEXT("best_race"), PbRace);
	Pb->SetBoolField(TEXT("new_best_lap"), bNewPbLap);
	Pb->SetBoolField(TEXT("new_best_race"), bNewPbRace);
	Pb->SetBoolField(TEXT("saved"), bSaved);
	Root->SetObjectField(TEXT("personal_best"), Pb);
	TArray<TSharedPtr<FJsonValue>> Ev;
	for (const FString& E : Events) Ev.Add(MakeShared<FJsonValueString>(E));
	Root->SetArrayField(TEXT("events"), Ev);
	TArray<TSharedPtr<FJsonValue>> Tr;
	for (const FString& E : Traces) Tr.Add(MakeShared<FJsonValueString>(E));
	Root->SetArrayField(TEXT("traces"), Tr);
	FString Out;
	FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Out));
	return Out;
}

static TSharedPtr<FJsonObject> ReadJsonFile(const FString& Path)
{
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root)) return nullptr;
	return Root;
}

// The player's best times on this course, next to the course file. Times from before the course was changed (another
// length) don't count.
void FSkyCourseRaceImpl::LoadTimes()
{
	FString Name = SkyCourse::SafeName(Course.Name);
	if (Name.IsEmpty()) Name = TEXT("Untitled");
	TimesPath = FPaths::ConvertRelativePathToFull(SkyCourse::CoursesDir() / (Name + TEXT(".times.json")));
	PbLap = PbRace = -1;
	PbSplits.Reset();
	bNewPbLap = bNewPbRace = bSaved = false;
	const TSharedPtr<FJsonObject> Root = ReadJsonFile(TimesPath);
	if (!Root) return;
	double Len = 0;
	if (!Root->TryGetNumberField(TEXT("length"), Len) || FMath::Abs(Len - B.Length) > 1.0) return;
	Root->TryGetNumberField(TEXT("best_lap"), PbLap);
	const TSharedPtr<FJsonObject>* Sp = nullptr;
	if (Root->TryGetObjectField(TEXT("best_lap_splits"), Sp) && Sp)
	{
		for (const auto& KV : (*Sp)->Values) if (KV.Value.IsValid()) PbSplits.Add(FCString::Atoi(*KV.Key), KV.Value->AsNumber());
	}
	const TSharedPtr<FJsonObject>* Races = nullptr;
	if (Root->TryGetObjectField(TEXT("best_race"), Races) && Races) (*Races)->TryGetNumberField(FString::FromInt(Laps), PbRace);
}

void FSkyCourseRaceImpl::SaveTimes()
{
	const FRacer* P = Racers.IsValidIndex(PlayerIdx) ? &Racers[PlayerIdx] : nullptr;
	if (!P || TimesPath.IsEmpty()) return;
	TSharedPtr<FJsonObject> Root = ReadJsonFile(TimesPath);
	double Len = 0;
	if (!Root || !Root->TryGetNumberField(TEXT("length"), Len) || FMath::Abs(Len - B.Length) > 1.0) Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("format"), TEXT("skycity-course-times"));
	Root->SetNumberField(TEXT("version"), 1);
	Root->SetStringField(TEXT("course"), Course.Name);
	Root->SetNumberField(TEXT("length"), B.Length);
	if (PbLap > 0)
	{
		Root->SetNumberField(TEXT("best_lap"), PbLap);
		TSharedRef<FJsonObject> Sp = MakeShared<FJsonObject>();
		for (const auto& KV : PbSplits) Sp->SetNumberField(FString::FromInt(KV.Key), KV.Value);
		Root->SetObjectField(TEXT("best_lap_splits"), Sp);
	}
	TSharedPtr<FJsonObject> Races;
	const TSharedPtr<FJsonObject>* Old = nullptr;
	Races = (Root->TryGetObjectField(TEXT("best_race"), Old) && Old) ? *Old : MakeShared<FJsonObject>();
	if (PbRace > 0) Races->SetNumberField(FString::FromInt(Laps), PbRace);
	Root->SetObjectField(TEXT("best_race"), Races);
	int32 Count = 0;
	Root->TryGetNumberField(TEXT("races"), Count);
	if (P->bFinished)
	{
		Root->SetNumberField(TEXT("races"), Count + 1);
		TSharedRef<FJsonObject> Last = MakeShared<FJsonObject>();
		Last->SetStringField(TEXT("date"), FDateTime::Now().ToIso8601());
		Last->SetNumberField(TEXT("laps"), Laps);
		Last->SetNumberField(TEXT("time"), P->FinishT);
		Last->SetNumberField(TEXT("best_lap"), P->BestLap);
		Last->SetNumberField(TEXT("place"), P->Place);
		Last->SetNumberField(TEXT("cars"), Racers.Num());
		TArray<TSharedPtr<FJsonValue>> Lt;
		for (double V : P->LapTimes) Lt.Add(MakeShared<FJsonValueNumber>(V));
		Last->SetArrayField(TEXT("lap_times"), Lt);
		Root->SetObjectField(TEXT("last"), Last);
	}
	FString Out;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Out));
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(TimesPath), true);
	bSaved = FFileHelper::SaveStringToFile(Out, *TimesPath);
	Note(FString::Printf(TEXT("best times %s %s"), bSaved ? TEXT("saved to") : TEXT("could not be saved to"), *TimesPath));
}

// --- the HUD ----------------------------------------------------------------------------------------

UFont* FSkyCourseRaceImpl::GetFont()
{
	if (!Font.IsValid()) Font = LoadObject<UFont>(nullptr, TEXT("/Engine/EngineFonts/Roboto.Roboto"));
	return Font.Get();
}

void FSkyCourseRaceImpl::DrawHud(AHUD* Hud, UCanvas* Canvas, float S)
{
	UFont* Fnt = GetFont();
	if (!Canvas || !Fnt || Racers.Num() == 0) return;
	const float W = Canvas->ClipX, H = Canvas->ClipY;
	auto Width = [&](const FString& Str, float Size) { float Xl = 0, Yl = 0; Canvas->TextSize(Fnt, Str, Xl, Yl, Size, Size); return Xl; };
	// Align: 0 left, 1 centre, 2 right
	auto Text = [&](const FString& Str, float X, float Y, float Size, const FLinearColor& C, int32 Align = 0)
	{
		const float Tw = Align ? Width(Str, Size) : 0.f;
		FCanvasTextItem Item(FVector2D(Align == 1 ? X - Tw * 0.5f : Align == 2 ? X - Tw : X, Y), FText::FromString(Str), Fnt, C);
		Item.Scale = FVector2D(Size, Size);
		Canvas->DrawItem(Item);
	};
	auto Rect = [&](const FLinearColor& C, float X, float Y, float Rw, float Rh)
	{
		FCanvasTileItem Tile(FVector2D(X, Y), FVector2D(Rw, Rh), C);
		Tile.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Tile);
	};
	const FRacer* P = Racers.IsValidIndex(PlayerIdx) ? &Racers[PlayerIdx] : nullptr;
	APlayerController* PC = Hud ? Hud->GetOwningPlayerController() : (GEngine ? GEngine->GetFirstLocalPlayerController(Owner->GetWorld()) : nullptr);

	// opponents' name tags, over their cars
	if (PC && PC->PlayerCameraManager)
	{
		const FVector Cam = PC->PlayerCameraManager->GetCameraLocation();
		const FVector CamFwd = PC->PlayerCameraManager->GetCameraRotation().Vector();
		for (const FRacer& R : Racers)
		{
			const ASkysterCar* C = R.Car.Get();
			if (!C || R.bPlayer) continue;
			const FVector At = C->GetActorLocation() + FVector(0, 0, 280);
			const double Dist = FVector::Dist(At, Cam) / 100.0;
			if (Dist > 250 || FVector::DotProduct(At - Cam, CamFwd) < 0) continue;
			FVector2D Sc;
			if (!PC->ProjectWorldLocationToScreen(At, Sc, true)) continue;
			const float A = (float)FMath::Clamp((250 - Dist) / 60.0, 0.0, 1.0);
			const FString Tag = FString::Printf(TEXT("P%d  %s"), R.Place, *R.Name);
			const float Tw = Width(Tag, 0.75f * S);
			Rect(FLinearColor(0.02f, 0.03f, 0.05f, 0.55f * A), (float)Sc.X - Tw * 0.5f - 18.f * S, (float)Sc.Y - 4.f * S, Tw + 30.f * S, 28.f * S);
			Rect(FLinearColor(R.Color.R, R.Color.G, R.Color.B, A), (float)Sc.X - Tw * 0.5f - 12.f * S, (float)Sc.Y + 4.f * S, 8.f * S, 12.f * S);
			Text(Tag, (float)Sc.X + 6.f * S, (float)Sc.Y - 2.f * S, 0.75f * S, FLinearColor(1, 1, 1, 0.95f * A), 1);
		}
	}

	// top left: position, lap, time, last and best lap, this course's best
	const float X0 = 40.f * S, Y0 = 40.f * S;
	Rect(Back, X0 - 14.f * S, Y0 - 10.f * S, 400.f * S, 206.f * S);
	const int32 Cars = Racers.Num();
	const int32 Lap = P ? FMath::Min(P->Lap, Laps) : (Order.Num() ? Racers[Order[0]].Lap : 1);
	Text(TEXT("POSITION"), X0, Y0, 0.7f * S, Dim);
	Text(TEXT("LAP"), X0 + 200.f * S, Y0, 0.7f * S, Dim);
	Text(FString::FromInt(P ? P->Place : 1), X0, Y0 + 14.f * S, 2.4f * S, Ink);
	Text(FString::Printf(TEXT("/%d"), Cars), X0 + Width(FString::FromInt(P ? P->Place : 1), 2.4f * S) + 4.f * S, Y0 + 44.f * S, 1.1f * S, Dim);
	Text(FString::FromInt(Lap), X0 + 200.f * S, Y0 + 14.f * S, 2.4f * S, Ink);
	Text(FString::Printf(TEXT("/%d"), Laps), X0 + 200.f * S + Width(FString::FromInt(Lap), 2.4f * S) + 4.f * S, Y0 + 44.f * S, 1.1f * S, Dim);
	const double Now = P && P->bFinished ? P->FinishT : FMath::Max(0.0, Clock());
	Text(TimeStr(Now), X0, Y0 + 92.f * S, 1.5f * S, P && P->bFinished ? Green : Ink);
	if (P)
	{
		Text(FString::Printf(TEXT("LAST  %s"), *TimeStr(P->LastLap)), X0, Y0 + 144.f * S, 0.85f * S, Dim);
		Text(FString::Printf(TEXT("BEST  %s"), *TimeStr(P->BestLap)), X0 + 200.f * S, Y0 + 144.f * S, 0.85f * S, Gold);
		Text(PbLap > 0 ? FString::Printf(TEXT("COURSE BEST LAP  %s%s"), *TimeStr(PbLap), bNewPbLap ? TEXT("  NEW") : TEXT("")) : FString(TEXT("COURSE BEST LAP  none yet")),
			X0, Y0 + 170.f * S, 0.72f * S, bNewPbLap ? Gold : Faint);
	}

	// centre: the countdown
	if (Phase == EPhase::Countdown)
	{
		const int32 N = FMath::Clamp(FMath::CeilToInt(COUNTDOWN - T), 1, 3);
		const float K = (float)(1.0 - FMath::Frac(COUNTDOWN - T));
		Text(TEXT("GET READY"), W * 0.5f, H * 0.24f, 1.1f * S, Dim, 1);
		Text(FString::FromInt(N), W * 0.5f, H * 0.28f, (5.5f + K * 1.0f) * S, FLinearColor(1, 1, 1, 0.97f), 1);
		Text(FString::Printf(TEXT("%s  ·  %d lap%s  ·  %d car%s"), *Course.Name, Laps, Laps == 1 ? TEXT("") : TEXT("s"), Cars, Cars == 1 ? TEXT("") : TEXT("s")),
			W * 0.5f, H * 0.28f + 150.f * S, 0.9f * S, Dim, 1);
	}
	else if (Clock() < 1.0)
	{
		Text(TEXT("GO!"), W * 0.5f, H * 0.28f, 6.0f * S, Green, 1);
	}

	if (P && Phase != EPhase::Countdown)
	{
		float Y = H * 0.21f;
		// a lap just done
		if (T - P->LapT < 2.8 && !P->LapTimes.IsEmpty())
		{
			Text(FString::Printf(TEXT("LAP %d  %s"), P->LapTimes.Num(), *TimeStr(P->LastLap)), W * 0.5f, Y, 1.4f * S, P->bLapBest ? Gold : Ink, 1);
			Y += 44.f * S;
			if (!P->bFinished && P->Lap == Laps && Laps > 1) { Text(TEXT("FINAL LAP"), W * 0.5f, Y, 1.2f * S, Orange, 1); Y += 40.f * S; }
		}
		// a checkpoint's split
		if (T - P->SplitT < 3.0)
		{
			const FString Head = FString::Printf(TEXT("CHECKPOINT %d   %s"), P->SplitGate + 1, P->Splits.Num() ? *TimeStr(P->Splits.Last()) : TEXT(""));
			Text(Head, W * 0.5f, Y, 1.0f * S, Ink, 1);
			if (P->SplitRef > 0) Text(FString::Printf(TEXT("%+.2f"), P->SplitDelta), W * 0.5f, Y + 32.f * S, 1.5f * S, P->SplitDelta <= 0 ? Green : Red, 1);
			Y += 84.f * S;
		}
		// which way at the next split
		if (!P->bFinished && P->Ri != INDEX_NONE)
		{
			for (int32 Ri = P->Ri + 1; Ri < P->Route.Segs.Num(); ++Ri)
			{
				const double Ahead = P->Route.At[Ri] - P->S;
				if (Ahead > 220) break;
				const int32 Sp = X[P->Route.Segs[Ri]].Split;
				if (Sp == INDEX_NONE || Ahead < 0) continue;
				FString Msg;
				if (B.Splits[Sp].Gate == ESkyGate::None) Msg = TEXT("SPLIT AHEAD: ANY BRANCH");
				else
				{
					TArray<FString> Open;
					for (int32 b = 0; b < BranchDir[Sp].Num(); ++b) if (Shown.IsValidIndex(Sp) && Shown[Sp].IsValidIndex(b) && Shown[Sp][b]) Open.Add(BranchDir[Sp][b]);
					Msg = FString::Printf(TEXT("BRANCH OPEN: %s"), *FString::Join(Open, TEXT(" · ")));
				}
				Text(Msg, W * 0.5f, Y, 1.2f * S, Green, 1);
				Text(FString::Printf(TEXT("in %d m"), FMath::RoundToInt(Ahead / 10.0) * 10), W * 0.5f, Y + 40.f * S, 0.8f * S, Dim, 1);
				Y += 76.f * S;
				break;
			}
		}
		// wrong way: into a closed branch, or driving backward
		if (T - P->WrongShowT < 0.2 || P->ReverseT > 1.2)
		{
			const float Blink = 0.55f + 0.45f * FMath::Abs(FMath::Sin((float)T * 7.f));
			Rect(FLinearColor(0.35f, 0.02f, 0.01f, 0.5f * Blink), W * 0.5f - 300.f * S, H * 0.40f - 10.f * S, 600.f * S, 120.f * S);
			Text(TEXT("WRONG WAY"), W * 0.5f, H * 0.40f, 3.0f * S, FLinearColor(1.f, 0.3f, 0.2f, Blink), 1);
			if (P->WrongSplit != INDEX_NONE) Text(TEXT("that branch is closed this lap · back to the split"), W * 0.5f, H * 0.40f + 80.f * S, 0.85f * S, Ink, 1);
		}
		if (T - P->MissT < 2.5) Text(TEXT("MISSED A CHECKPOINT"), W * 0.5f, H * 0.52f, 1.3f * S, Orange, 1);
		if (T - P->RespawnT < 1.5) Text(TEXT("BACK ON TRACK"), W * 0.5f, H * 0.52f + 46.f * S, 1.0f * S, Dim, 1);
		// smart steering lit (like Mario Kart's antenna): a small tag low in the middle while it nudges
		if (T - P->NudgeT < 0.4) Text(TEXT("STEER ASSIST"), W * 0.5f, H * 0.86f, 0.7f * S, Dim, 1);
	}

	// the results, once the player is home (or the race is over)
	if ((P && P->bFinished) || Phase == EPhase::Done)
	{
		const float Pw = 820.f * S, Px = (W - Pw) * 0.5f;
		float Y = H * 0.30f;
		const float Ph = (150.f + 46.f * Cars + 40.f) * S;
		Rect(FLinearColor(0.02f, 0.03f, 0.05f, 0.78f), Px - 30.f * S, Y - 24.f * S, Pw + 60.f * S, Ph);
		Text(TEXT("RESULTS"), Px, Y, 1.6f * S, Ink);
		Text(FString::Printf(TEXT("%s · %d lap%s"), *Course.Name, Laps, Laps == 1 ? TEXT("") : TEXT("s")), Px + Pw, Y + 14.f * S, 0.85f * S, Dim, 2);
		Y += 62.f * S;
		Text(TEXT("POS"), Px, Y, 0.7f * S, Faint);
		Text(TEXT("DRIVER"), Px + 80.f * S, Y, 0.7f * S, Faint);
		Text(TEXT("TIME"), Px + 460.f * S, Y, 0.7f * S, Faint);
		Text(TEXT("BEST LAP"), Px + 660.f * S, Y, 0.7f * S, Faint);
		Y += 30.f * S;
		for (int32 k = 0; k < Order.Num(); ++k)
		{
			const FRacer& R = Racers[Order[k]];
			if (R.bPlayer) Rect(FLinearColor(0.2f, 0.55f, 1.f, 0.25f), Px - 10.f * S, Y - 4.f * S, Pw + 20.f * S, 42.f * S);
			Rect(FLinearColor(R.Color.R, R.Color.G, R.Color.B, 0.95f), Px + 56.f * S, Y + 6.f * S, 8.f * S, 22.f * S);
			Text(FString::FromInt(R.Place), Px, Y, 1.1f * S, Ink);
			Text(R.Name, Px + 80.f * S, Y, 1.1f * S, R.bPlayer ? Ink : Dim);
			Text(R.bFinished ? TimeStr(R.FinishT) : (Phase == EPhase::Done ? FString(TEXT("DNF")) : FString::Printf(TEXT("racing · lap %d/%d"), R.Lap, Laps)), Px + 460.f * S, Y, 1.0f * S, R.bFinished ? Ink : Faint);
			Text(TimeStr(R.BestLap), Px + 660.f * S, Y + 2.f * S, 0.95f * S, Gold);
			Y += 46.f * S;
		}
		Y += 10.f * S;
		if (P && P->bFinished)
		{
			const FString Pb = bNewPbRace ? FString::Printf(TEXT("New best on this course: %s"), *TimeStr(PbRace)) : PbRace > 0 ? FString::Printf(TEXT("Your best on this course: %s"), *TimeStr(PbRace)) : FString();
			Text(Pb, Px, Y, 0.9f * S, bNewPbRace ? Gold : Dim);
		}
		Text(TEXT("Y: back to building"), Px + Pw, Y, 0.85f * S, Dim, 2);
	}
}

// --- ASkyCourseRace ---------------------------------------------------------------------------------

ASkyCourseRace::ASkyCourseRace()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;   // before the cars, which wait on it while they race
}

void ASkyCourseRace::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bRunning || !Impl) return;
	const double T0 = FPlatformTime::Seconds();
	Impl->Tick(DeltaSeconds);
	const double Took = FPlatformTime::Seconds() - T0;
	Impl->TickSecs += Took;
	Impl->TickMax = FMath::Max(Impl->TickMax, Took);
	++Impl->Ticks;
}

void ASkyCourseRace::Begin(ASkyCourseTrack* Track, const FSkyCourse& Course, ASkysterCar* Player, int32 Opponents, double Skill)
{
	End();
	Best = -1;
	Impl = MakeShared<FSkyCourseRaceImpl>(this);
	bRunning = Impl->Begin(Track, Course, Player, Opponents, Skill);
	if (!bRunning) { Impl->End(); Impl.Reset(); }
}

void ASkyCourseRace::EndPlay(const EEndPlayReason::Type Reason)
{
	if (bRunning || Impl) End();
	Super::EndPlay(Reason);
}

void ASkyCourseRace::End()
{
	if (Impl) Impl->End();
	Impl.Reset();
	bRunning = false;
}

TArray<ASkyCourseRace::FResult> ASkyCourseRace::GetResults() const
{
	return Impl ? Impl->Results() : TArray<FResult>();
}

FString ASkyCourseRace::TestResultsJson() const
{
	return Impl ? Impl->ResultsJson() : FString(TEXT("{\"phase\":\"none\",\"cars\":[]}"));
}

void ASkyCourseRace::DrawHud(AHUD* Hud, UCanvas* Canvas, float S)
{
	if (bRunning && Impl) Impl->DrawHud(Hud, Canvas, S);
}

// --- test commands (editor Python or the console, in a game world) ----------------------------------

static ASkysterCar* FindPlayerCar(UWorld* World)
{
	if (APlayerController* PC = World->GetFirstPlayerController()) if (ASkysterCar* C = Cast<ASkysterCar>(PC->GetPawn())) return C;
	for (TActorIterator<ASkysterCar> It(World); It; ++It) if (!It->bAIDriver) return *It;
	return nullptr;
}

template <class T>
static T* FindOrSpawnTagged(UWorld* World, const FName& Tag)
{
	for (TActorIterator<T> It(World); It; ++It) if (It->ActorHasTag(Tag)) return *It;
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	T* A = World->SpawnActor<T>(T::StaticClass(), FTransform::Identity, P);
	if (A) A->Tags.Add(Tag);
	return A;
}

// SkyCourse.RaceTest [file=<course .json>] [opponents=3] [skill=0.8] [laps=3]: build the course (or SkyCourse::Example in
// front of the car) on a test track and race it, without the Course Builder director.
static void RaceTestCmd(const TArray<FString>& Args, UWorld* World)
{
	if (!World || !World->IsGameWorld()) { UE_LOG(LogSkyRace, Warning, TEXT("SkyCourse.RaceTest: run it in a game (PIE) world")); return; }
	TMap<FString, FString> Kv;
	for (const FString& A : Args) { FString K, V; if (A.Split(TEXT("="), &K, &V)) Kv.Add(K.ToLower(), V); }
	ASkysterCar* Car = FindPlayerCar(World);
	FSkyCourse Course;
	if (const FString* File = Kv.Find(TEXT("file")))
	{
		FString Text;
		TArray<FString> Errors;
		if (!FFileHelper::LoadFileToString(Text, **File) || !SkyCourse::Parse(Text, Course, Errors))
		{
			UE_LOG(LogSkyRace, Warning, TEXT("SkyCourse.RaceTest: can't read %s: %s"), **File, *FString::Join(Errors, TEXT("; ")));
			return;
		}
	}
	else
	{
		// at=x,y,z yaw=deg (course metres), else in front of the car
		FVector P = Car ? Car->Pos + Car->Fwd * 25.0 + FVector(0, 0, 0.5) : FVector::ZeroVector;
		double Yaw = Car ? FMath::RadiansToDegrees(FMath::Atan2(Car->Fwd.Y, Car->Fwd.X)) : 0.0;
		if (const FString* At = Kv.Find(TEXT("at")))
		{
			TArray<FString> Xyz;
			At->ParseIntoArray(Xyz, TEXT(","));
			if (Xyz.Num() == 3) P = FVector(FCString::Atod(*Xyz[0]), FCString::Atod(*Xyz[1]), FCString::Atod(*Xyz[2]));
		}
		if (const FString* Yw = Kv.Find(TEXT("yaw"))) Yaw = FCString::Atod(**Yw);
		Course = SkyCourse::Example(P, Yaw);
	}
	if (const FString* L = Kv.Find(TEXT("laps"))) Course.Laps = FCString::Atoi(**L);
	const int32 Opp = Kv.Contains(TEXT("opponents")) ? FCString::Atoi(*Kv[TEXT("opponents")]) : 3;
	const double Skill = Kv.Contains(TEXT("skill")) ? FCString::Atod(*Kv[TEXT("skill")]) : 0.8;
	ASkyCourseTrack* Track = FindOrSpawnTagged<ASkyCourseTrack>(World, TEXT("SkyRaceTest"));
	ASkyCourseRace* Race = FindOrSpawnTagged<ASkyCourseRace>(World, TEXT("SkyRaceTest"));
	if (!Track || !Race) return;
	Race->End();
	const FSkyBaked& Baked = Track->Build(Course, FBox(ForceInit));
	if (!Baked.bValid)
	{
		UE_LOG(LogSkyRace, Warning, TEXT("SkyCourse.RaceTest: the course has errors: %s"), *FString::Join(Baked.Errors, TEXT("; ")));
		return;
	}
	// the track's collision cooks over the next frames: line up once it's there
	TWeakObjectPtr<ASkyCourseRace> WR(Race);
	TWeakObjectPtr<ASkyCourseTrack> WT(Track);
	TWeakObjectPtr<ASkysterCar> WC(Car);
	FTimerHandle H;
	World->GetTimerManager().SetTimer(H, FTimerDelegate::CreateLambda([WR, WT, WC, Course, Opp, Skill]()
	{
		if (!WR.IsValid() || !WT.IsValid()) return;
		WR->Begin(WT.Get(), Course, WC.Get(), Opp, Skill);
		UE_LOG(LogSkyRace, Log, TEXT("SkyCourse.RaceTest: %s"), WR->IsRunning() ? TEXT("racing") : TEXT("failed to start"));
	}), 1.5f, false);
}

static void RaceEndCmd(const TArray<FString>& Args, UWorld* World)
{
	if (!World) return;
	for (TActorIterator<ASkyCourseRace> It(World); It; ++It) if (It->ActorHasTag(TEXT("SkyRaceTest"))) { It->End(); It->Destroy(); }
	for (TActorIterator<ASkyCourseTrack> It(World); It; ++It) if (It->ActorHasTag(TEXT("SkyRaceTest"))) It->Destroy();
}

// SkyCourse.RaceDump <file>: every race in the world's results JSON, into a file.
static void RaceDumpCmd(const TArray<FString>& Args, UWorld* World)
{
	if (!World || Args.Num() < 1) return;
	FString Out = TEXT("[");
	int32 N = 0;
	for (TActorIterator<ASkyCourseRace> It(World); It; ++It) { Out += (N++ ? TEXT(",") : TEXT("")) + It->TestResultsJson(); }
	Out += TEXT("]");
	FFileHelper::SaveStringToFile(Out, *Args[0]);
}

static FAutoConsoleCommandWithWorldAndArgs GRaceTestCmd(TEXT("SkyCourse.RaceTest"),
	TEXT("Test: race a course without the Course Builder: SkyCourse.RaceTest [file=<course.json> | at=x,y,z yaw=deg (the example course)] [opponents=3] [skill=0.8] [laps=3]"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RaceTestCmd));
static FAutoConsoleCommandWithWorldAndArgs GRaceEndCmd(TEXT("SkyCourse.RaceEnd"), TEXT("Test: end the SkyCourse.RaceTest race and remove its track."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RaceEndCmd));
static FAutoConsoleCommandWithWorldAndArgs GRaceDumpCmd(TEXT("SkyCourse.RaceDump"), TEXT("Test: write the races' results JSON to a file: SkyCourse.RaceDump <path>"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RaceDumpCmd));
