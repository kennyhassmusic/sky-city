// The Course Builder's AI opponents (see SkyCourseRaceImpl.h): ASkysterCars flagged bAIDriver, driven only through
// their test-input hooks (TestThrottle, TestBrake, TestSteer, TestPitch, TestRoll, bTestBoost, bTestJump), so they have
// exactly the player's physics. Each follows its lap's route in its own lane:
//   line       its lane (and a slow wander), the middle for loops, corkscrews, wall rides and the run-in to a jump, the
//              side its branch leaves from before a fork, room round a slower car ahead; it eases from one to the next
//   steering   on the ground, by the deck under the car: the way the track bends across the deck, plus a pull back onto
//              its line from how far off it is and how fast it's drifting (so a slide or gravity across a tilted deck
//              is caught as it starts, not once the car is near the edge), turned into a yaw rate and a steering angle;
//              with the tail out it steers into the slide and stays off the pedals
//   speed      the bends' limits (curvature, bank and the tyre model's grip, worked out per frame when the race begins),
//              braked for in time; a loop's entry speed, a corkscrew's speed (the same for every skill: too slow or too
//              fast and it comes off), a jump's take-off speed for a landing 6-10 m onto the pad, centred and
//              straight at the lip; slower where the bend changes sharply on a narrow deck, into a fork it can't get
//              across to in time, or into a wall ride or corkscrew off its middle; boost when the motors can't get
//              there, and on straights
//   in the air the stick and air roll set the car down wheels-first on the deck below, nose along the travel (turned a
//              few degrees toward the track); boost if it's falling short of the pad
//   skill      0.3-1.2 scales how close to the limits it drives, its top speed, how hard it brakes, how quickly it
//              steers and how tidy its line is. Not how well it holds on: a slow car is slow, not clumsy
//   traffic    it picks a side to pass a slower car ahead, or follows on a one-lane deck; keeps a car's width from a
//              car beside it; into a loop, corkscrew, wall ride or a one-lane branch one at a time (the car further
//              round goes first, the other drops in behind), and follows inside them rather than touching
// The race handles recovery (respawns) and contact for every car alike.
#include "SkyCourseRaceImpl.h"

#include "HAL/IConsoleManager.h"

using namespace SkyRaceK;

// Tuning knobs, read every tick (so a test race can be tuned without a rebuild). The defaults are the tuned values.
static TAutoConsoleVariable<float> CVarLatW(TEXT("SkyCourse.AI.LatW"), 2.4f,
	TEXT("AI: how briskly a car pulls back onto its line, rad/s (the lateral controller's natural frequency)."));
static TAutoConsoleVariable<float> CVarLatZeta(TEXT("SkyCourse.AI.LatZeta"), 1.0f,
	TEXT("AI: damping of that pull (1 = critical: no overshoot)."));
static TAutoConsoleVariable<float> CVarYawK(TEXT("SkyCourse.AI.YawK"), 0.3f,
	TEXT("AI: yaw-rate feedback in the steering (0 = the steering angle the bend asks for, alone)."));
static TAutoConsoleVariable<float> CVarAirK(TEXT("SkyCourse.AI.AirK"), 1.0f,
	TEXT("AI: strength of its air control (0 = none): pitch, roll and yaw to land wheels-down, nose along the travel."));
static TAutoConsoleVariable<float> CVarCurlW(TEXT("SkyCourse.AI.CurlW"), 1.0f,
	TEXT("AI: the pull back onto its line in loops, corkscrews and wall rides, times SkyCourse.AI.LatW."));
static TAutoConsoleVariable<int32> CVarTrace(TEXT("SkyCourse.AI.Trace"), 1,
	TEXT("AI: log the last 6 s of a car's driving when it's put back on the track (1), or not (0)."));

namespace
{
	const FSkyCaps& AICaps()
	{
		static const FSkyCaps C = [] { FSkyCaps K = Skyster::CapsFor(Skyster::NumLevels - 1); K.bFlight = false; return K; }();
		return C;
	}

	constexpr int32 TRACE_LEN = 360;   // ticks kept (6 s at 60 fps)
	constexpr double EDGE_ROOM = 2.5;   // m from the deck's edge to the furthest line it takes (half a car and 1.5 m)

	bool Curls(const FSkySegment& S)
	{
		return S.Kind == ESkySeg::Piece && (S.Type == ESkyPiece::Loop || S.Type == ESkyPiece::Corkscrew || S.Type == ESkyPiece::WallRide);
	}

	// The rotation (axis times angle, world frame) that turns the car's orientation Q onto the frame (F, L, U).
	FVector RotationTo(const FQuat& Q, const FVector& F, const FVector& U)
	{
		const FVector Fn = F.GetSafeNormal();
		const FVector L = FVector::CrossProduct(U, Fn).GetSafeNormal();
		const FVector Un = FVector::CrossProduct(Fn, L);
		const FQuat Qt(FMatrix(Fn, L, Un, FVector::ZeroVector));
		FQuat Qe = Qt * Q.Inverse();
		Qe.Normalize();
		if (Qe.W < 0) Qe = FQuat(-Qe.X, -Qe.Y, -Qe.Z, -Qe.W);   // the short way round
		FVector Axis;
		double Angle;
		Qe.ToAxisAndAngle(Axis, Angle);
		return Angle > 1e-6 ? Axis * Angle : FVector::ZeroVector;
	}
}

void FSkyCourseRaceImpl::InitAI(FRacer& R, int32 Index)
{
	FAIDriver& A = R.AI;
	A.Rand.Initialize(1000 + Index * 77);
	A.K = FMath::Clamp((R.Skill - 0.3) / 0.9, 0.0, 1.0);
	A.Pace = FMath::Lerp(0.78, 1.0, A.K);          // share of a bend's limit it dares (the limits keep 28% of the grip in hand)
	A.Cap = FMath::Lerp(58.0, MAX_SPEED, A.K);      // its top speed on a straight
	A.BrakeA = FMath::Lerp(15.0, 23.0, A.K);        // how hard it plans to brake (the brakes give 30)
	// s of lag on its steering. Kept short for every skill: at 50 m/s a fifth of a second of lag set the low-skill cars
	// weaving into jumps and spinning in banked bends (22 Oct)
	A.React = FMath::Lerp(0.07, 0.025, A.K);
	A.WanderAmp = FMath::Lerp(1.0, 0.15, A.K);      // m its line wanders
	A.WanderOff = A.WanderGoal = 0;
	A.WanderT = A.Rand.FRandRange(0.5, 3.0);
	A.Steer = 0;
	A.HopT = -1;
	A.JumpSeg = INDEX_NONE;
	A.bLineSet = false;
	A.bYawSet = false;
	A.YawRate = 0;
	A.SlideT = 0;
	A.Trace.SetNumZeroed(TRACE_LEN);
	A.TraceHead = A.TraceNum = 0;
}

FSkyCourseRaceImpl::FCursor FSkyCourseRaceImpl::CursorOf(const FRacer& R) const
{
	FCursor C;
	C.Ri = R.Ri;
	C.Seg = R.Seg;
	C.I = R.Frame;
	C.S = R.S;
	// at a fork the branches' decks overlap, so the tracker may put the car on another branch's lead-in than the one
	// its route takes: steer and plan along its own branch from the matching point on it
	const int32 Sp = X[R.Seg].Split;
	if (R.Ri == INDEX_NONE && Sp != INDEX_NONE && R.Route.Choice.IsValidIndex(Sp) && B.Splits[Sp].LeadSegs.IsValidIndex(R.Route.Choice[Sp]))
	{
		const int32 Lead = B.Splits[Sp].LeadSegs[R.Route.Choice[Sp]];
		const int32 Ri = R.Route.Segs.Find(Lead);
		const ASkysterCar* Car = R.Car.Get();
		if (Ri != INDEX_NONE && Car)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[Lead].Frames;
			int32 Best = 0;
			double BestD = TNumericLimits<double>::Max();
			for (int32 i = 0; i < Fr.Num() && i <= R.Frame + SEARCH; ++i) { const double D = FVector::DistSquared(Car->Pos, Fr[i].P); if (D < BestD) { BestD = D; Best = i; } }
			C.Ri = Ri;
			C.Seg = Lead;
			C.I = Best;
			C.S = R.Route.At[Ri] + X[Lead].Cum[Best];
		}
	}
	return C;
}

// One frame further along the car's route; onto the next lap's start round a lap course. False at the end.
bool FSkyCourseRaceImpl::Step(const FRacer& R, FCursor& C) const
{
	const int32 N = B.Segs[C.Seg].Frames.Num();
	if (C.I + 1 < N)
	{
		C.S += X[C.Seg].Cum[C.I + 1] - X[C.Seg].Cum[C.I];
		++C.I;
		return true;
	}
	int32 Nx = INDEX_NONE;
	if (C.Ri != INDEX_NONE)
	{
		if (C.Ri + 1 < R.Route.Segs.Num()) Nx = R.Route.Segs[++C.Ri];
		else if (B.bLapCourse && R.Route.Segs.Num()) { C.Ri = 0; Nx = R.Route.Segs[0]; }
	}
	else if (B.Segs[C.Seg].Next.Num()) Nx = B.Segs[C.Seg].Next[0];
	if (Nx == INDEX_NONE || B.Segs[Nx].Frames.Num() < 2) return false;
	C.Seg = Nx;
	C.I = 1;   // frame 0 is the same point as the last segment's end
	C.S += X[Nx].Cum[1];
	return true;
}

void FSkyCourseRaceImpl::Drive(FRacer& R, ASkysterCar& Car, double Dt)
{
	FAIDriver& A = R.AI;
	if (R.bPlayer)
	{
		// the test autopilot drives the player's car at its own skill
		const double Sk = FMath::Clamp(AutopilotSkill(), 0.3, 1.2);
		if (FMath::Abs(Sk - R.Skill) > 1e-3 || A.Pace <= 0 || A.Trace.Num() == 0) { R.Skill = Sk; InitAI(R, 7); }
	}
	Car.bTestInput = true;
	Car.TestStop = 0.f;
	Car.TestPitch = Car.TestRoll = 0.f;
	Car.bTestSlide = Car.bTestFly = false;
	if (!Car.bAlive)
	{
		Car.TestThrottle = Car.TestBrake = Car.TestSteer = 0.f;
		Car.bTestBoost = Car.bTestJump = false;
		return;
	}
	Dt = FMath::Max(Dt, 1e-3);
	const double V = Car.Speed;
	const double Vf = Car.bGrounded ? Car.Vf : FVector::DotProduct(Car.Vel, Car.Fwd);
	const FCursor C0 = CursorOf(R);
	const FSkySegment& Sg0 = B.Segs[C0.Seg];
	const FSkyFrame& F0 = Sg0.Frames[C0.I];
	const FSegX& Sx0 = X[C0.Seg];
	const ESkyPiece Type0 = Sg0.Type;
	const double Half0 = F0.Width * 0.5;
	const double Room0 = FMath::Max(0.0, Half0 - EDGE_ROOM);
	// the track curls here (a loop, a corkscrew, a wall ride): keep to its middle, steady
	const bool bCurl = Curls(Sg0);

	// where it is on the deck under it (on its own branch at a fork), and how it's moving across it
	const FVector Rel0 = Car.Pos - F0.P;
	const double E = FVector::DotProduct(Rel0, F0.L);                // m, + = left of the middle
	const double VLat = FVector::DotProduct(Car.Vel, F0.L);          // m/s, + = drifting left
	const double Psi = FMath::Atan2(FVector::DotProduct(Car.Fwd, F0.L), FVector::DotProduct(Car.Fwd, F0.F));   // nose, + = left of the track
	const double Roll = FMath::Atan2(-F0.L.Z, F0.U.Z);              // the deck's roll, + = tipped to the right
	// the tail out: the travel's angle off the nose (+ = travelling to the left of where it points)
	const double Beta = (Car.bGrounded && V > 6.0) ? FMath::Atan2(FVector::DotProduct(Car.Vel, Car.Left), FMath::Max(FVector::DotProduct(Car.Vel, Car.Fwd), 1.0)) : 0.0;
	// the yaw rate across the deck (+ = left): the nose's turn against the track since last tick, plus the track's own
	// turn across its deck. (Not the nose's turn in the world: where the deck rolls, as in a corkscrew, a nose a little
	// off the track's line sweeps round with the roll, which isn't yaw at all)
	if (A.bYawSet && Car.bGrounded)
	{
		const double KL0 = Sx0.KL.IsValidIndex(C0.I) ? Sx0.KL[C0.I] : 0.0;
		const double Raw = FMath::FindDeltaAngleRadians(A.PrevPsi, Psi) / Dt + Vf * KL0;
		A.YawRate += (FMath::Clamp(Raw, -8.0, 8.0) - A.YawRate) * (1.0 - FMath::Exp(-Dt / 0.03));
	}
	else A.YawRate = Car.bGrounded ? Vf * (Sx0.KL.IsValidIndex(C0.I) ? Sx0.KL[C0.I] : 0.0) : 0.0;
	A.bYawSet = Car.bGrounded;
	A.PrevPsi = Psi;

	// --- what's ahead: a loop's, a corkscrew's or a jump's speed, a fork, a curl -------------------------------------
	double NeedV = 0, NeedD = 0, CapV = 0;
	bool bJumpAhead = false, bLoopAhead = false;
	int32 ForkLead = INDEX_NONE;   // the lead-in of the branch its route takes at the next split, if one is close
	double ForkD = 0;              // m to that fork
	double CurlD = -1;             // m to the next loop, corkscrew or wall ride (-1: none within 300 m)
	{
		int32 Ri = C0.Ri, Sg = C0.Seg;
		double SegAt = C0.S - X[Sg].Cum[C0.I];
		for (int32 n = 0; n < 64 && SegAt - C0.S < 300.0; ++n)
		{
			const FSegX& Sx = X[Sg];
			if (n > 0 && Sx.Split != INDEX_NONE && ForkLead == INDEX_NONE && SegAt - C0.S < 160.0) { ForkLead = Sg; ForkD = SegAt - C0.S; }
			if (n > 0 && CurlD < 0 && Curls(B.Segs[Sg])) CurlD = SegAt - C0.S;
			if (Sx.NeedV > 0)
			{
				const double Dn = SegAt + Sx.Cum[FMath::Clamp(Sx.NeedAt, 0, Sx.Cum.Num() - 1)] - C0.S;
				if (Dn >= -0.5 && NeedV <= 0)
				{
					NeedV = Sx.NeedV;
					NeedD = FMath::Max(0.0, Dn);
					CapV = Sx.CapV;
					bJumpAhead = Sx.bJump;
					bLoopAhead = Sx.bLoop;
				}
			}
			SegAt += Sx.Len;
			int32 Nx = INDEX_NONE;
			if (Ri != INDEX_NONE)
			{
				if (Ri + 1 < R.Route.Segs.Num()) Nx = R.Route.Segs[++Ri];
				else if (B.bLapCourse && R.Route.Segs.Num()) { Ri = 0; Nx = R.Route.Segs[0]; }
			}
			else if (B.Segs[Sg].Next.Num()) Nx = B.Segs[Sg].Next[0];
			if (Nx == INDEX_NONE) break;
			Sg = Nx;
		}
	}
	// lined up for a jump: in the middle, no lane changes, wandering or passing for the last stretch before the lip
	// (sideways speed at take-off carries the car off the side of the pad), and until it's down again
	const bool bSteady = (bJumpAhead && NeedD < 70.0) || (A.JumpSeg != INDEX_NONE);

	// --- its line: the lane, a slow wander (less with skill), and room round a slower car ahead ---------------------
	if ((A.WanderT -= Dt) <= 0)
	{
		A.WanderT = A.Rand.FRandRange(2.5, 6.0);
		A.WanderGoal = A.Rand.FRandRange(-1.f, 1.f) * A.WanderAmp;
	}
	A.WanderOff += (A.WanderGoal - A.WanderOff) * (1.0 - FMath::Exp(-0.6 * Dt));
	A.AvoidT -= Dt;
	double BlockV = TNumericLimits<double>::Max();
	double YieldV = TNumericLimits<double>::Max();
	const bool bCalm = bSteady || bCurl || (CurlD >= 0 && CurlD < 45.0);
	// into a loop, a corkscrew or a wall ride one at a time: they're driven in the middle, and two cars side by side
	// there shove each other off it (a corkscrew throws a car more than a metre or two off its middle off the deck)
	const int32 ForkSplit = ForkLead != INDEX_NONE ? X[ForkLead].Split : INDEX_NONE;
	const bool bNarrowFork = ForkLead != INDEX_NONE && ForkD < 90.0 && B.Segs[ForkLead].Frames[0].Width < 8.0;
	const bool bQueue = (CurlD >= 0 && CurlD < 90.0 && !bCurl) || bNarrowFork;
	// side by side: keep a car's width and a bit from it (its line is bounded on that side)
	double SideLo = -TNumericLimits<double>::Max(), SideHi = TNumericLimits<double>::Max();
	const double LapLen = R.Route.LapLen();
	for (const FRacer& O : Racers)
	{
		const ASkysterCar* Oc = O.Car.Get();
		if (&O == &R || !Oc || !Oc->bAlive) continue;
		const FVector Rel = Oc->Pos - Car.Pos;
		const double Ahead = FVector::DotProduct(Rel, Car.Fwd);
		const double Side = FVector::DotProduct(Rel, Car.Left);
		// who goes first: the one further round (one rule for both cars, so they never both give way)
		const double Lead = (O.Progress - R.Progress) * LapLen;
		const bool bOtherFirst = Lead > 0.5 || (FMath::Abs(Lead) <= 0.5 && &O < &R);
		const bool bSameWay = !bNarrowFork || (CurlD >= 0 && CurlD < 90.0) || !O.Route.Choice.IsValidIndex(ForkSplit) || !R.Route.Choice.IsValidIndex(ForkSplit)
			|| O.Route.Choice[ForkSplit] == R.Route.Choice[ForkSplit];
		if (bQueue && bSameWay && bOtherFirst && Ahead > -2.0 && Ahead < 9.0 && FMath::Abs(Side) < 3.8)
		{
			// level with it or just behind: drop in behind
			YieldV = FMath::Min(YieldV, FVector::DotProduct(Oc->Vel, Car.Fwd) - 3.0);
		}
		if (FMath::Abs(Ahead) < 5.0 && FMath::Abs(Side) < 4.0)
		{
			const double OLat = FVector::DotProduct(Oc->Pos - F0.P, F0.L);   // across this car's deck
			if (OLat > E) SideHi = FMath::Min(SideHi, OLat - 2.5);
			else SideLo = FMath::Max(SideLo, OLat + 2.5);
			// no room to be beside it: the one behind drops back
			if (SideLo > SideHi - 0.2 && bOtherFirst) YieldV = FMath::Min(YieldV, FVector::DotProduct(Oc->Vel, Car.Fwd) - 2.0);
		}
		if (Ahead < 2.0 || Ahead > 18.0 || FMath::Abs(Side) > 2.8) continue;
		const double Closing = FVector::DotProduct(Car.Vel - Oc->Vel, Car.Fwd);
		if (Closing < 1.0) continue;
		// passing: a car's width and a half from it, a little nearer the edge than its own line goes
		const double PassRoom = FMath::Max(0.0, Half0 - 1.8);
		const double L1 = O.Lat + 2.7, L2 = O.Lat - 2.7;
		const bool bOk1 = L1 <= PassRoom, bOk2 = L2 >= -PassRoom;
		if (bCalm || (!bOk1 && !bOk2)) { BlockV = FMath::Min(BlockV, FVector::DotProduct(Oc->Vel, Car.Fwd) + 0.5); continue; }   // follow
		A.AvoidLat = (bOk1 && (!bOk2 || FMath::Abs(L1 - R.Lat) < FMath::Abs(L2 - R.Lat))) ? L1 : L2;
		A.AvoidT = 1.5;
	}
	if (bCalm) A.AvoidT = 0;

	double Want = R.Lane * Room0 + A.WanderOff;
	// m/s across the deck it moves its line at (more for a fork, but not mid-bend, where it's using its grip to turn)
	const bool bBend = FMath::Abs(Sx0.KL.IsValidIndex(C0.I) ? Sx0.KL[C0.I] : 0.f) > 0.006;
	double LineRate = FMath::Clamp(0.06 * FMath::Abs(Vf), 1.5, 3.5);
	if (bCurl || (CurlD >= 0 && CurlD < 50.0)) Want = 0.0;   // the middle
	else if (bSteady) Want = R.Lane * Room0 * 0.35;   // near the middle, in its own lane (not side by side in the middle)
	else if (A.AvoidT > 0) Want = A.AvoidLat;
	if (ForkLead != INDEX_NONE && X[C0.Seg].Split == INDEX_NONE)
	{
		// a split ahead: over to the side its branch leaves from, in time (the branches' decks part soon after the fork)
		const FSkyFrame& L0 = B.Segs[ForkLead].Frames[0];
		Want = X[ForkLead].ForkOff + R.Lane * FMath::Max(0.0, L0.Width * 0.5 - 1.3) * 0.5;
		if (!bBend) LineRate *= 1.4;
		A.AvoidT = 0;
	}
	// and within the deck all along the next stretch of its route (a merge narrowing to fewer lanes, a fork's slot): the
	// room each frame ahead allows, measured from this frame's middle (where segments meet off-centre, their middles are
	// apart by the offset)
	const double Edge = (A.AvoidT > 0 && !bCalm) ? 1.8 : EDGE_ROOM;   // passing: a little nearer the edge
	double Lo = -FMath::Max(0.0, Half0 - Edge), Hi = FMath::Max(0.0, Half0 - Edge);
	{
		FCursor C = C0;
		double Shift = 0;
		const double Span = FMath::Clamp(1.2 * FMath::Abs(Vf), 15.0, 60.0);
		for (int32 Guard = 0; Guard < 40 && C.S - C0.S < Span; ++Guard)
		{
			bool bOk = true;
			for (int32 k = 0; k < 4 && bOk; ++k)
			{
				const int32 Was = C.Seg;
				bOk = Step(R, C);
				if (bOk && C.Seg != Was)
				{
					const FSkyFrame& Fa = B.Segs[Was].Frames.Last();
					Shift += FVector::DotProduct(B.Segs[C.Seg].Frames[0].P - Fa.P, Fa.L);
				}
			}
			if (!bOk) break;
			const FSkyFrame& Fk = B.Segs[C.Seg].Frames[C.I];
			const double Rk = FMath::Max(0.0, Fk.Width * 0.5 - Edge);
			Lo = FMath::Max(Lo, Shift - Rk);
			Hi = FMath::Min(Hi, Shift + Rk);
		}
	}
	if (Lo > Hi) Lo = Hi = 0.5 * (Lo + Hi);
	// a car beside it (only where the deck leaves room for both, and not where it must keep to the middle)
	if (!bCurl && !(CurlD >= 0 && CurlD < 50.0))
	{
		if (SideLo > Lo && SideLo < Hi) Lo = SideLo;
		if (SideHi < Hi && SideHi > Lo) Hi = SideHi;
	}
	const bool bSqueezed = Want < Lo - 0.3 || Want > Hi + 0.3 || A.Line < Lo - 0.3 || A.Line > Hi + 0.3;
	Want = FMath::Clamp(Want, Lo, Hi);
	if (bSqueezed) LineRate = FMath::Max(LineRate, 4.5);
	// the line is measured from the middle of the segment it's on: where two segments meet off-centre (a fork's
	// lead-ins, a merge), the same spot on the deck is a different offset, so carry the line across
	if (A.bLineSet && A.LineSeg != C0.Seg) A.Line += FVector::DotProduct(A.LineP - F0.P, F0.L);
	if (!A.bLineSet) { A.Line = FMath::Clamp(E, -Room0, Room0); A.LineV = 0; A.bLineSet = true; }
	A.LineSeg = C0.Seg;
	A.LineP = F0.P;
	// eased: the line's own sideways speed ramps up and down (4 m/s^2), so the car can follow it without overshooting
	{
		const double Goal = FMath::Clamp(1.6 * (Want - A.Line), -LineRate, LineRate);
		A.LineV += FMath::Clamp(Goal - A.LineV, -4.0 * Dt, 4.0 * Dt);
		A.Line = FMath::Clamp(A.Line + A.LineV * Dt, -Half0, Half0);
	}
	const double LineV = A.LineV;

	// --- steering ----------------------------------------------------------------------------------------------------
	const bool bGrip = !Car.Handling.bArcade;
	const double MaxSteer = FMath::Max(0.02, (bGrip ? Car.Handling.SteerLock : 0.62) / (1.0 + FMath::Abs(Vf) / (bGrip ? Car.Handling.SteerFade : 16.0)));
	double Steer = 0, React = A.React;
	bool bSlide = false;
	const float AirK = CVarAirK.GetValueOnGameThread();
	if (!Car.bGrounded)
	{
		// in the air: set it down wheels-first. Target: the deck it will land on (a jump's pad, else the track ahead),
		// the nose along the travel turned up to 4 degrees toward the track's heading (the tyres then pull the travel
		// round as they land, without a skid). Stick: pitch and yaw; air roll: roll. Each a PD on the attitude error.
		const FSkyFrame* Land = nullptr;
		if (A.JumpSeg != INDEX_NONE && X[A.JumpSeg].LandAt != INDEX_NONE)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[A.JumpSeg].Frames;
			Land = &Fr[FMath::Clamp(X[A.JumpSeg].AimAt != INDEX_NONE ? X[A.JumpSeg].AimAt : X[A.JumpSeg].LandAt + 6, 0, Fr.Num() - 1)];
		}
		else
		{
			FCursor C = C0;
			for (int32 k = 0; k < 16; ++k) if (!Step(R, C)) break;
			Land = &B.Segs[C.Seg].Frames[C.I];
		}
		FVector Tv = Car.Vel - Land->U * FVector::DotProduct(Car.Vel, Land->U);   // the travel along the deck below
		FVector Tf = Land->F;
		FVector Dir = Tv.SizeSquared() > 9.0 ? Tv.GetSafeNormal() : Tf;
		{
			// up to 4 degrees from the travel toward the track
			const double Off = FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(Dir, Tf), Land->U), FVector::DotProduct(Dir, Tf));
			const double Turn = FMath::Clamp(Off, -0.07, 0.07);
			Dir = FQuat(Land->U, Turn).RotateVector(Dir);
		}
		const FVector Err = Car.Q.Inverse().RotateVector(RotationTo(Car.Q, Dir, Land->U));   // car frame: x roll (+ right), y pitch (+ nose down), z yaw (+ left)
		const FVector Wl = Car.Q.Inverse().RotateVector(Car.W);
		const double Kk = FMath::Max(0.0f, AirK);
		Car.TestPitch = (float)FMath::Clamp(Kk * (3.0 * Err.Y - 0.75 * Wl.Y), -1.0, 1.0);
		Car.TestRoll = (float)FMath::Clamp(Kk * (1.0 * Err.X - 0.2 * Wl.X), -1.0, 1.0);
		Steer = FMath::Clamp(-Kk * (4.0 * Err.Z - 1.1 * Wl.Z), -1.0, 1.0);   // the stick's yaw: + turns right
		React = 0.0;
	}
	else
	{
		// on the deck: the bend across the deck just ahead (the steering takes ~0.1 s to answer), plus a pull back onto
		// the line from the offset and the drift (a PD in lateral acceleration), as a yaw rate, then a steering angle
		const double Vv = FMath::Max(FMath::Abs(Vf), 4.0);
		double Kff = 0;
		{
			// the bend 0.08-0.2 s ahead: about the steering's lag, so it turns in as the bend arrives, not after
			FCursor C = C0;
			const double From = FMath::Clamp(0.08 * Vv, 0.5, 6.0), To = FMath::Clamp(0.2 * Vv, 1.5, 14.0);
			double Sum = 0;
			int32 Num = 0;
			for (int32 Guard = 0; Guard < 60; ++Guard)
			{
				const FSegX& Xc = X[C.Seg];
				if (C.S - C0.S >= From && Xc.KL.IsValidIndex(C.I)) { Sum += Xc.KL[C.I]; ++Num; }
				if (C.S - C0.S >= To || !Step(R, C)) break;
			}
			Kff = Num ? Sum / Num : 0.0;
			// off the middle of a bend the line's radius differs (the inside is tighter)
			Kff /= FMath::Max(0.5, 1.0 - Kff * E);
		}
		const double W = FMath::Clamp((double)CVarLatW.GetValueOnGameThread() * (bCurl ? CVarCurlW.GetValueOnGameThread() : 1.f), 0.3, 8.0);
		const double Z = FMath::Clamp((double)CVarLatZeta.GetValueOnGameThread(), 0.2, 3.0);
		// near the edge and heading for it: pull back harder
		const bool bEdge = FMath::Abs(E) > Half0 - 1.6 && VLat * FMath::Sign(E) > 0.5;
		const double ACap = bEdge ? 40.0 : 20.0;
		const double ACorr = FMath::Clamp(W * W * (A.Line - E) + 2.0 * Z * W * (LineV - VLat), -ACap, ACap);
		// no more than the tyres can give (asking for more only swings the tail out: at the limit it spun cars in S-bends)
		const double Fans = F0.U.Z < 0.6 ? 1.0 : 0.15 + 0.45 * FMath::SmoothStep(15.0, 40.0, FMath::Abs(Vf));
		const double Grip = Car.Handling.Mu * FMath::Max(G * 0.25, G * F0.U.Z + G * SUCTION * Fans + G * AERO * FMath::Square(Vf / MAX_SPEED));
		// (gravity across a tilted deck helps one way and hinders the other: the tyres give the rest)
		const double GL = -G * F0.L.Z;
		const double ALo = GL - 0.85 * Grip, AHi = GL + 0.85 * Grip;
		const double RDes = FMath::Clamp(Vv * Vv * Kff + ACorr, ALo, AHi) / Vv;   // rad/s, + = left
		const double YawK = FMath::Clamp((double)CVarYawK.GetValueOnGameThread(), 0.0, 3.0);
		const double RCmd = FMath::Clamp(RDes + YawK * (RDes - A.YawRate), ALo / Vv, AHi / Vv);
		const double Delta = FMath::Atan(WHEELBASE * RCmd / Vv);   // + = left
		Steer = FMath::Clamp(-Delta / MaxSteer, -1.0, 1.0);
		if (FMath::Abs(Beta) > 0.15 && V > 8.0)
		{
			// the tail is out: steer into the slide (front wheels toward the travel) until the tyres grip again
			bSlide = true;
			Steer = FMath::Clamp(Steer - 0.9 * (Beta - FMath::Sign(Beta) * 0.08) / MaxSteer, -1.0, 1.0);
			React = FMath::Min(React, 0.03);
		}
		else if (FMath::Abs(Psi) > 0.7 && Vf < 12.0)
		{
			// turned across the track (after a spin): point it back along the track first
			Steer = FMath::Clamp(Psi * 1.5, -1.0, 1.0);
		}
		if (bCurl) React = FMath::Min(React, 0.03);
	}
	A.SlideT = bSlide ? A.SlideT + Dt : 0.0;
	A.Steer += (Steer - A.Steer) * (React > 1e-3 ? 1.0 - FMath::Exp(-Dt / React) : 1.0);
	Car.TestSteer = (float)A.Steer;

	if (R.bFinished)
	{
		// past the line: ease off and stop
		Car.TestThrottle = 0.f;
		Car.TestBrake = 0.f;
		Car.TestStop = V > 1.0 ? 0.35f : 1.f;
		Car.bTestBoost = Car.bTestJump = false;
		return;
	}

	// --- speed: the bends ahead, braked for in time --------------------------------------------------------------
	double Vt = FMath::Min(A.Cap, BlockV);
	const double Ab = A.BrakeA;
	const double Look = V * V / (2.0 * Ab) + 25.0;
	{
		// the speed it can shed before each point: braking only over deck (none in the air over a jump's gap), and less
		// of it downhill, where gravity pushes against the brakes (more uphill). Corkscrews are driven at their own
		// speed whatever the skill: their limit is a window, not a bend
		FCursor P = C0;
		double Budget = 0, PrevS = C0.S;
		for (int32 Guard = 0; P.S - C0.S < Look && Guard < 600; ++Guard)
		{
			const FSkyFrame& Fp = B.Segs[P.Seg].Frames[P.I];
			if (Fp.bDeck) Budget += 2.0 * FMath::Max(4.0, Ab + G * Fp.F.Z) * (P.S - PrevS);
			PrevS = P.S;
			const FSegX& Xp = X[P.Seg];
			const double Vm = Xp.VMax[P.I] * (Xp.bCork ? 1.0 : A.Pace);
			Vt = FMath::Min(Vt, FMath::Sqrt(Vm * Vm + Budget));
			bool bOk = true;
			for (int32 k = 0; k < 4 && bOk; ++k) bOk = Step(R, P);
			if (!bOk) break;
		}
	}
	// a jump: at its take-off speed 40 m before the lip (jumps sit after ramps: allow for a downhill run-in), then
	// straight and steady to the lip
	if (bJumpAhead && CapV > 0) Vt = FMath::Min(Vt, FMath::Sqrt(NeedV * NeedV + 2.0 * FMath::Max(2.0, Ab - 0.3 * G) * FMath::Max(0.0, NeedD - 40.0)));
	bool bNeedBoost = false;
	if (NeedV > 0)
	{
		// the loop, corkscrew or jump wins over a bend before it (a loop or a jump can't be taken slower; a corkscrew a
		// little, behind a slower car)
		if (Vt < NeedV) Vt = (bLoopAhead || bJumpAhead) ? NeedV + (bLoopAhead ? 1.0 : 0.0) : FMath::Max(FMath::Min(NeedV, BlockV), NeedV - 6.0);
		const FSkyCaps& Cp = AICaps();
		const double Req = (NeedV * NeedV - Vf * Vf) / (2.0 * FMath::Max(NeedD, 1.0));
		const double Motors = FMath::Max(0.0, Cp.Accel * (1.0 - 0.9 * FMath::Clamp(Vf / Cp.Drive, 0.0, 1.0)));
		bNeedBoost = NeedD < 250.0 && Vf < NeedV - 0.5 && (Req > Motors * 0.55 || Vf > Cp.Drive * 0.97);
	}
	// a fork its line can't get across to in time (the gates changed late, or it was put back near it): slow down
	if (ForkLead != INDEX_NONE && X[C0.Seg].Split == INDEX_NONE)
	{
		const double Shift = FMath::Abs(Want - A.Line);
		const double Rate = FMath::Clamp(0.06 * FMath::Abs(Vf), 1.5, 3.5) * 1.4;
		if (Shift > 0.5) Vt = FMath::Min(Vt, FMath::Max(14.0, (ForkD - 8.0) * Rate / Shift));
	}
	// queueing for a curl behind a car beside it: drop back, while there's room to fall in behind and still be up to the
	// curl's speed when it gets there
	if (YieldV < Vt && (NeedV <= 0 || NeedD > 15.0) && !bCurl) Vt = FMath::Max(YieldV, NeedV > 0 ? NeedV * 0.75 : 15.0);
	// in a corkscrew: its speed, or a little under behind a slower car (two cars touching there shove each other off
	// the middle, and a corkscrew throws a car a couple of metres off its middle off the deck)
	if (bCurl && Type0 == ESkyPiece::Corkscrew && Sx0.VMax.IsValidIndex(C0.I)) Vt = FMath::Min(Sx0.VMax[C0.I] - 1.5, FMath::Max(BlockV, Sx0.VMax[C0.I] - 8.0));
	// into a wall ride or a corkscrew off its middle: slower. The deck rolls about its middle (or an axis just above it),
	// so a car off to one side is lifted with the roll and thrown off where the roll eases (a car 4.5 m out on a wall
	// ride's rising side at 46 m/s flew off it); the throw grows with the speed squared
	if (((CurlD >= 0 && CurlD < 45.0) || (bCurl && Type0 != ESkyPiece::Loop && FMath::Abs(Roll) < 0.6)) && FMath::Abs(E) > 1.2 && Car.bGrounded)
	{
		const bool bLoopNext = !bCurl && bLoopAhead && NeedD < 50.0;
		if (!bLoopNext) Vt = FMath::Min(Vt, FMath::Max(24.0, 50.0 * FMath::Sqrt(1.2 / FMath::Abs(E))));
	}
	A.TargetV = Vt;
	A.NeedV = NeedV;
	const double Err = Vt - Vf;
	float Thr = 0.f, Brk = 0.f;
	{
		// the motors hold a speed with a touch of throttle (nothing drags but the coast on a lifted pedal); uphill (a
		// ramp, a jump's lip) they also need what the slope takes off
		const FSkyCaps& Cp = AICaps();
		const double Motors = FMath::Max(5.0, Cp.Accel * (1.0 - 0.9 * FMath::Clamp(Vf / Cp.Drive, 0.0, 1.0)));
		const double Hill = Car.bGrounded ? FMath::Clamp(G * F0.F.Z / Motors, 0.0, 0.8) : 0.0;
		if (Err > 0.3) Thr = (float)FMath::Clamp(0.08 + 0.2 * Err + Hill, 0.0, 1.0);
		else if (Err > -0.4) Thr = (float)(0.03 + Hill);
		else if (Err < -1.2) Brk = (float)FMath::Clamp(0.1 + 0.3 * (-Err - 1.2), 0.1, 1.0);
	}
	// hard braking while steering, or on the run-in to a jump's lip, swings the tail out: ease off
	if (FMath::Abs(A.Steer) > 0.35) Brk = FMath::Min(Brk, 0.5f);
	if (bJumpAhead && NeedD < 40.0) Brk = FMath::Min(Brk, 0.25f);
	// the tail out: off the pedals (all the grip for turning), just enough throttle not to coast
	if (bSlide) { Brk = 0.f; Thr = FMath::Min(Thr, 0.03f); }
	if (!Car.bGrounded) { Thr = 0.f; Brk = 0.f; }   // in the air LT is the air brake: never
	// in a loop, a corkscrew or a wall ride: no brakes (they'd spend the grip that holds the car on, and the speed that
	// presses it to the deck), and keep the motors pulling. A corkscrew's level ends may brake a little
	if (bCurl && Car.bGrounded)
	{
		const bool bLevel = FMath::Abs(Roll) < 0.35;
		Brk = (Type0 == ESkyPiece::Corkscrew && bLevel && Err < -2.0) ? FMath::Min(Brk, 0.3f) : 0.f;
		if (Type0 == ESkyPiece::Loop) Thr = FMath::Max(Thr, 0.6f);
		else if (Brk <= 0.f && Err > -0.4) Thr = FMath::Max(Thr, 0.03f);   // hold the speed (coast when too close behind)
	}
	Car.TestThrottle = Thr;
	Car.TestBrake = Brk;

	// --- boost: to reach a loop's or a jump's speed, and on straights (keeping a share for what's ahead) ------------
	const bool bStraight = FMath::Abs(A.Steer) < 0.2 && Vt > Vf + 5.0 && !bCurl && !bSlide;
	const bool bKeep = NeedV > 0 && NeedD < 300.0;
	bool bBoost = Car.BoostTank > 1.0 && Car.bGrounded && !bSlide && Vf < AICaps().Top - 1.0 && Vf < Vt - 1.0
		&& (bNeedBoost || (A.K > 0.3 && bStraight && Vf < A.Cap - 2.0 && (!bKeep || Car.BoostTank > 40.0)));

	// --- jumps: a jump at the lip when the gap needs it; in the air boost if short of the pad ----------------------
	if (Sx0.bJump) A.JumpSeg = C0.Seg;
	else if (Car.bGrounded) A.JumpSeg = INDEX_NONE;
	bool bJumpBtn = false;
	if (A.HopT >= 0)
	{
		A.HopT += Dt;
		bJumpBtn = A.HopT < 0.25;   // held: the first 0.2 s keep pushing
		if (A.HopT > 0.8) A.HopT = -1;
	}
	else if (Car.bGrounded && Sx0.bJump && Sx0.bHop && C0.I <= Sx0.NeedAt && Sx0.Cum[Sx0.NeedAt] - Sx0.Cum[C0.I] < 1.5)
	{
		A.HopT = 0;
		bJumpBtn = true;
		Note(FString::Printf(TEXT("%s jumps at the lip (%.0f mph)"), *R.Name, V * 2.23694));
	}
	Car.bTestJump = bJumpBtn;
	if (!Car.bGrounded && A.JumpSeg != INDEX_NONE && A.JumpSeg == R.Seg && X[A.JumpSeg].LandAt != INDEX_NONE && Car.BoostTank > 0.5)
	{
		// coming down short of the pad's edge (+2 m): boost (along the nose, which is near level)
		const TArray<FSkyFrame>& Fr = B.Segs[A.JumpSeg].Frames;
		const FSkyFrame& L = Fr[FMath::Min(X[A.JumpSeg].LandAt + 4, Fr.Num() - 1)];
		FVector H(L.F.X, L.F.Y, 0);
		if (H.Normalize())
		{
			const double Dh = FVector::DotProduct(L.P - Car.Pos, H);
			const double Vh = FVector::DotProduct(Car.Vel, H), Vz = Car.Vel.Z, Dz = Car.Pos.Z - L.P.Z;
			const double Disc = Vz * Vz + 2.0 * G * Dz;
			const double TLand = Disc > 0 ? (Vz + FMath::Sqrt(Disc)) / G : 0.0;
			if (Dh > 0 && Vh * TLand < Dh) bBoost = true;
		}
	}
	A.bBoost = bBoost;
	Car.bTestBoost = bBoost;

	// --- the trace ---------------------------------------------------------------------------------------------------
	if (A.Trace.Num())
	{
		FAITrace& Tr = A.Trace[A.TraceHead];
		A.TraceHead = (A.TraceHead + 1) % A.Trace.Num();
		A.TraceNum = FMath::Min(A.TraceNum + 1, A.Trace.Num());
		Tr.T = (float)Clock(); Tr.S = (float)C0.S; Tr.Lat = (float)E; Tr.VLat = (float)VLat; Tr.Vf = (float)Vf; Tr.Psi = (float)Psi;
		Tr.Beta = (float)Beta; Tr.Roll = (float)Roll; Tr.Vert = (float)R.Vert; Tr.Steer = (float)A.Steer; Tr.Thr = Thr; Tr.Brk = Brk;
		Tr.Want = (float)A.Line; Tr.TargetV = (float)Vt; Tr.Pitch = Car.TestPitch; Tr.Yaw = (float)A.YawRate;
		Tr.Seg = (int16)C0.Seg; Tr.Frame = (int16)C0.I; Tr.bGround = Car.bGrounded; Tr.bBoost = bBoost; Tr.bSlide = bSlide;
		Tr.bBump = T - R.BumpT < 0.06; Tr.bYield = YieldV < 1e9;
	}
}

// The last 3 s before a respawn, every ~0.1 s, into the log and the results (tests: where and how it went wrong).
void FSkyCourseRaceImpl::DumpTrace(const FRacer& R, const TCHAR* Why)
{
	const FAIDriver& A = R.AI;
	if (CVarTrace.GetValueOnGameThread() == 0 || A.TraceNum == 0 || A.Trace.Num() == 0) return;
	auto Add = [this](const FString& Line)
	{
		UE_LOG(LogSkyRace, Log, TEXT("%s"), *Line);
		if (Traces.Num() < 3000) Traces.Add(Line);
	};
	Add(FString::Printf(TEXT("%7.2f  TRACE %s (%s): t seg/frame S | lat line vlat | vf vt | psi beta roll(deg) yawrate | steer thr brk pitch | G/A slide boost contact yield vert"),
		Clock(), *R.Name, Why));
	const int32 N = A.Trace.Num();
	double LastT = -1e9;
	for (int32 k = 0; k < A.TraceNum; ++k)
	{
		const FAITrace& Tr = A.Trace[(A.TraceHead - A.TraceNum + k + N) % N];
		const bool bLast = k == A.TraceNum - 1;
		if (!bLast && Tr.T - LastT < 0.095) continue;
		LastT = Tr.T;
		Add(FString::Printf(TEXT("    %6.2f %2d/%3d %6.1f | %+5.1f %+5.1f %+5.1f | %4.1f %4.1f | %+4.0f %+4.0f %+4.0f %+5.2f | %+5.2f %4.2f %4.2f %+5.2f | %s%s%s%s%s %+4.1f"),
			Tr.T, Tr.Seg, Tr.Frame, Tr.S, Tr.Lat, Tr.Want, Tr.VLat, Tr.Vf, Tr.TargetV,
			FMath::RadiansToDegrees(Tr.Psi), FMath::RadiansToDegrees(Tr.Beta), FMath::RadiansToDegrees(Tr.Roll), Tr.Yaw,
			Tr.Steer, Tr.Thr, Tr.Brk, Tr.Pitch, Tr.bGround ? TEXT("G") : TEXT("A"), Tr.bSlide ? TEXT(" S") : TEXT(""), Tr.bBoost ? TEXT(" B") : TEXT(""),
			Tr.bBump ? TEXT(" C") : TEXT(""), Tr.bYield ? TEXT(" Y") : TEXT(""), Tr.Vert));
	}
}
