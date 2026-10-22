// The Course Builder's AI opponents (see SkyCourseRaceImpl.h): ASkysterCars flagged bAIDriver, driven only through
// their test-input hooks (TestThrottle, TestBrake, TestSteer, bTestBoost, bTestJump, TestPitch), so they have exactly
// the player's physics. Each follows its lap's route in its own lane:
//   steering   pure pursuit on the centre-line frames ahead (the look-ahead grows with speed, and stops short where the
//              track curls up into a loop, so the point stays in front of the car); in the air the same point sets the yaw
//   speed      the bends' limits (from curvature, bank and the tyre model's grip, worked out per frame when the race
//              begins), braked for in time; a loop's or a jump's entry speed, boosting if the motors can't get there;
//              not so fast a jump overshoots; boost on straights; a jump at the lip when a gap needs the extra climb
//   skill      0.3-1.2 scales how close to the limit it drives, its top speed, how hard it brakes, how quickly it
//              steers and how tidy its line is
//   traffic    it picks a side to pass a slower car ahead, or follows on a one-lane deck
// The race handles recovery (respawns) and contact for every car alike.
#include "SkyCourseRaceImpl.h"

using namespace SkyRaceK;

namespace
{
	const FSkyCaps& AICaps()
	{
		static const FSkyCaps C = [] { FSkyCaps K = Skyster::CapsFor(Skyster::NumLevels - 1); K.bFlight = false; return K; }();
		return C;
	}
}

void FSkyCourseRaceImpl::InitAI(FRacer& R, int32 Index)
{
	FAIDriver& A = R.AI;
	A.Rand.Initialize(1000 + Index * 77);
	A.K = FMath::Clamp((R.Skill - 0.3) / 0.9, 0.0, 1.0);
	A.Pace = FMath::Lerp(0.80, 1.0, A.K);          // share of a bend's limit it dares
	A.Cap = FMath::Lerp(58.0, MAX_SPEED, A.K);      // its top speed on a straight
	A.BrakeA = FMath::Lerp(15.0, 23.0, A.K);        // how hard it plans to brake (the brakes give 30)
	A.React = FMath::Lerp(0.22, 0.04, A.K);         // s of lag on its steering
	A.WanderAmp = FMath::Lerp(1.2, 0.15, A.K);      // m its line wanders
	A.WanderOff = A.WanderGoal = 0;
	A.WanderT = A.Rand.FRandRange(0.5, 3.0);
	A.Steer = 0;
	A.HopT = -1;
	A.JumpSeg = INDEX_NONE;
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
		if (FMath::Abs(Sk - R.Skill) > 1e-3 || A.Pace <= 0) { R.Skill = Sk; InitAI(R, 7); }
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
	const double V = Car.Speed;
	const double Vf = Car.bGrounded ? Car.Vf : FVector::DotProduct(Car.Vel, Car.Fwd);
	const FCursor C0 = CursorOf(R);
	const FSkyFrame& F0 = B.Segs[C0.Seg].Frames[C0.I];
	const double Room0 = FMath::Max(0.0, F0.Width * 0.5 - 1.3);
	const FSegX& Sx0 = X[C0.Seg];
	const ESkyPiece Type0 = B.Segs[C0.Seg].Type;
	// the track curls here (a loop, a corkscrew, a wall ride): steer by the deck itself and keep to its middle
	const bool bCurl = B.Segs[C0.Seg].Kind == ESkySeg::Piece && (Type0 == ESkyPiece::Loop || Type0 == ESkyPiece::Corkscrew || Type0 == ESkyPiece::WallRide);

	// --- a loop or a jump ahead: the speed it needs at its start, and at most what a jump allows ---------------------
	double NeedV = 0, NeedD = 0, CapV = 0, CapD = 0;
	bool bJumpAhead = false;
	int32 ForkLead = INDEX_NONE;   // the lead-in of the branch its route takes at the next split, if one is close
	double ForkD = 0;
	{
		int32 Ri = C0.Ri, Sg = C0.Seg;
		double SegAt = C0.S - X[Sg].Cum[C0.I];
		for (int32 n = 0; n < 64 && SegAt - C0.S < 300.0; ++n)
		{
			const FSegX& Sx = X[Sg];
			if (n > 0 && Sx.Split != INDEX_NONE && ForkLead == INDEX_NONE && SegAt - C0.S < 120.0) { ForkLead = Sg; ForkD = SegAt - C0.S; }
			(void)ForkD;
			if (Sx.NeedV > 0)
			{
				const double Dn = SegAt + Sx.Cum[FMath::Clamp(Sx.NeedAt, 0, Sx.Cum.Num() - 1)] - C0.S;
				if (Dn >= -0.5 && NeedV <= 0)
				{
					NeedV = Sx.NeedV;
					NeedD = FMath::Max(0.0, Dn);
					CapV = Sx.CapV;
					CapD = NeedD;
					bJumpAhead = Sx.bJump;
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
	// lined up for a jump: no lane changes or wandering in the last stretch before the lip (sideways speed at take-off
	// carries the car off the side of the pad)
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
	for (const FRacer& O : Racers)
	{
		const ASkysterCar* Oc = O.Car.Get();
		if (&O == &R || !Oc || !Oc->bAlive) continue;
		const FVector Rel = Oc->Pos - Car.Pos;
		const double Ahead = FVector::DotProduct(Rel, Car.Fwd);
		if (Ahead < 2.0 || Ahead > 18.0 || FMath::Abs(FVector::DotProduct(Rel, Car.Left)) > 2.8) continue;
		const double Closing = FVector::DotProduct(Car.Vel - Oc->Vel, Car.Fwd);
		if (Closing < 1.0) continue;
		const double L1 = O.Lat + 3.2, L2 = O.Lat - 3.2;
		const bool bOk1 = L1 <= Room0, bOk2 = L2 >= -Room0;
		if (bSteady || bCurl || (!bOk1 && !bOk2)) { BlockV = FMath::Min(BlockV, FVector::DotProduct(Oc->Vel, Car.Fwd) + 0.5); continue; }   // follow
		A.AvoidLat = (bOk1 && (!bOk2 || FMath::Abs(L1 - R.Lat) < FMath::Abs(L2 - R.Lat))) ? L1 : L2;
		A.AvoidT = 1.5;
	}
	if (bSteady || bCurl) A.AvoidT = 0;

	// --- steering --------------------------------------------------------------------------------------------------
	const bool bGrip = !Car.Handling.bArcade;
	const double MaxSteer = FMath::Max(0.02, (bGrip ? Car.Handling.SteerLock : 0.62) / (1.0 + FMath::Abs(Vf) / (bGrip ? Car.Handling.SteerFade : 16.0)));
	double Steer = 0, React = A.React;
	if (!Car.bGrounded)
	{
		// in the air the stick yaws the nose: line it up with the travel, so it lands straight
		const double Lr = -FVector::DotProduct(Car.Vel, Car.Left), Lf = FVector::DotProduct(Car.Vel, Car.Fwd);
		Steer = FMath::Abs(Lf) + FMath::Abs(Lr) > 3.0 ? FMath::Clamp(2.0 * FMath::Atan2(Lr, FMath::Max(Lf, 0.5)), -1.0, 1.0) : 0.0;
	}
	else if (bCurl)
	{
		// by the deck under the car: the way the track bends across its own deck (a loop's sideways shift), plus the
		// car's heading off it and its distance from the middle (a Stanley controller: it works upside down too)
		const double K = Sx0.KL.IsValidIndex(C0.I) ? Sx0.KL[C0.I] : 0.0;
		const double Psi = FMath::Atan2(FVector::DotProduct(Car.Fwd, F0.L), FVector::DotProduct(Car.Fwd, F0.F));   // + = pointing left of the track
		const double E = R.Lat;                                                                                        // + = left of the middle
		const double Delta = -FMath::Atan(WHEELBASE * K) + Psi + FMath::Atan(1.5 * E / (FMath::Abs(Vf) + 3.0));
		Steer = FMath::Clamp(Delta / MaxSteer, -1.0, 1.0);
		React = FMath::Min(React, 0.03);
	}
	else
	{
		// pure pursuit on the frames ahead: the look-ahead grows with speed, and stops short where the track turns hard
		const double Ld = FMath::Clamp(4.0 + 0.30 * V, 5.0, 36.0) * FMath::Lerp(1.15, 1.0, A.K);
		FCursor C = C0;
		for (int32 Guard = 0; C.S - C0.S < Ld && Guard < 200; ++Guard)
		{
			FCursor Nx = C;
			if (!Step(R, Nx)) break;
			if (Nx.S - C0.S > 3.0 && FVector::DotProduct(B.Segs[Nx.Seg].Frames[Nx.I].F, F0.F) < 0.8) break;
			C = Nx;
		}
		const FSkyFrame& Ft = B.Segs[C.Seg].Frames[C.I];
		const FSegX& Xt = X[C.Seg];
		const ESkyPiece Tt = B.Segs[C.Seg].Type;
		const double Room = FMath::Max(0.0, Ft.Width * 0.5 - 1.3);
		// into a loop, a corkscrew or a wall ride: line up on its middle
		const bool bCurlAhead = B.Segs[C.Seg].Kind == ESkySeg::Piece && (Tt == ESkyPiece::Loop || Tt == ESkyPiece::Corkscrew || Tt == ESkyPiece::WallRide);
		(void)Xt;
		// into a loop, a corkscrew or a wall ride: the middle of the deck; lined up for a jump: nearer the middle, no wander
		double Want = bCurlAhead ? 0.0 : bSteady ? R.Lane * Room * 0.4 : A.AvoidT > 0 ? A.AvoidLat : R.Lane * Room + A.WanderOff;
		if (ForkLead != INDEX_NONE && C.Seg != ForkLead)
		{
			// a split ahead: over to the side its branch leaves from, in time (the branches' decks part soon after the fork)
			const FSkyFrame& L0 = B.Segs[ForkLead].Frames[0];
			const double LeadRoom = FMath::Max(0.0, L0.Width * 0.5 - 1.3);
			Want = FVector::DotProduct(L0.P - Ft.P, Ft.L) + R.Lane * LeadRoom * 0.5;
			A.AvoidT = 0;
		}
		const FVector Target = Ft.P + Ft.L * FMath::Clamp(Want, -Room, Room);
		const FVector D = Target - Car.Pos;
		const double Lf = FVector::DotProduct(D, Car.Fwd), Lr = -FVector::DotProduct(D, Car.Left);   // + = to the right
		const double Alpha = FMath::Atan2(Lr, FMath::Max(Lf, 0.5));
		const double Dist = FMath::Max(3.0, FMath::Sqrt(Lf * Lf + Lr * Lr));
		// (a cross-track term on top doubled the gain at 50 m/s and set the car fishtailing into jumps: pure pursuit alone)
		Steer = FMath::Clamp(FMath::Atan(2.0 * WHEELBASE * FMath::Sin(Alpha) / Dist) / MaxSteer, -1.0, 1.0);
	}
	A.Steer += (Steer - A.Steer) * (1.0 - FMath::Exp(-Dt / FMath::Max(React, 0.01)));
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
		// of it downhill, where gravity pushes against the brakes (more uphill)
		FCursor P = C0;
		double Budget = 0, PrevS = C0.S;
		for (int32 Guard = 0; P.S - C0.S < Look && Guard < 600; ++Guard)
		{
			const FSkyFrame& Fp = B.Segs[P.Seg].Frames[P.I];
			if (Fp.bDeck) Budget += 2.0 * FMath::Max(4.0, Ab + G * Fp.F.Z) * (P.S - PrevS);
			PrevS = P.S;
			const double Vm = X[P.Seg].VMax[P.I] * A.Pace;
			Vt = FMath::Min(Vt, FMath::Sqrt(Vm * Vm + Budget));
			bool bOk = true;
			for (int32 k = 0; k < 4 && bOk; ++k) bOk = Step(R, P);
			if (!bOk) break;
		}
	}
	// a jump: at its speed 35 m before the lip (jumps sit after ramps: allow for a downhill run-in), then straight and
	// steady to the lip
	if (CapV > 0) Vt = FMath::Min(Vt, FMath::Sqrt(CapV * CapV + 2.0 * (Ab - 0.3 * G) * FMath::Max(0.0, CapD - 35.0)));
	bool bNeedBoost = false;
	if (NeedV > 0)
	{
		if (Vt < NeedV) Vt = NeedV + 1.0;   // the loop or jump wins over a bend before it
		const FSkyCaps& Cp = AICaps();
		const double Req = (NeedV * NeedV - Vf * Vf) / (2.0 * FMath::Max(NeedD, 1.0));
		const double Motors = FMath::Max(0.0, Cp.Accel * (1.0 - 0.9 * FMath::Clamp(Vf / Cp.Drive, 0.0, 1.0)));
		bNeedBoost = NeedD < 250.0 && (Req > Motors * 0.55 || Vf > Cp.Drive * 0.97);
	}
	A.TargetV = Vt;
	A.NeedV = NeedV;
	const double Err = Vt - Vf;
	float Thr = 0.f, Brk = 0.f;
	if (Err > 0.5) Thr = (float)FMath::Clamp(0.45 + 0.12 * Err, 0.0, 1.0);
	else if (Err < -1.0) Brk = (float)FMath::Clamp(-Err * 0.18, 0.1, 1.0);
	// hard braking while steering, or on the run-in to a jump's lip, swings the tail out: ease off
	if (FMath::Abs(A.Steer) > 0.35) Brk = FMath::Min(Brk, 0.5f);
	if (bJumpAhead && NeedD < 35.0) Brk = FMath::Min(Brk, 0.15f);
	else Thr = 0.3f;
	if (!Car.bGrounded) { Thr = 1.f; Brk = 0.f; }   // in the air LT is the air brake: never
	// in a loop, a corkscrew or a wall ride: no brakes (they'd spend the grip that holds the car on, and the speed that
	// presses it to the deck), and keep the motors pulling
	if (bCurl && Car.bGrounded) { Brk = 0.f; Thr = FMath::Max(Thr, Type0 == ESkyPiece::Loop ? 0.6f : 0.15f); }
	Car.TestThrottle = Thr;
	Car.TestBrake = Brk;

	// --- boost: to reach a loop's or a jump's speed, and on straights (keeping a share for what's ahead) ------------
	const bool bStraight = FMath::Abs(A.Steer) < 0.2 && Vt > Vf + 5.0 && !bCurl;
	const bool bKeep = NeedV > 0 && NeedD < 300.0;
	bool bBoost = Car.BoostTank > 1.0 && Car.bGrounded && Vf < AICaps().Top - 1.0 && Vf < Vt - 1.0
		&& (bNeedBoost || (A.K > 0.3 && bStraight && Vf < A.Cap - 2.0 && (!bKeep || Car.BoostTank > 40.0)));

	// --- jumps: a jump at the lip when the gap needs it; in the air, nose along the travel and boost if short -------
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
	if (!Car.bGrounded)
	{
		const double Sp = Car.Vel.Size();
		const double Tz = Sp > 3.0 ? FMath::Clamp(Car.Vel.Z / Sp * 0.6, -0.35, 0.3) : 0.0;
		Car.TestPitch = (float)FMath::Clamp(3.0 * (Car.Fwd.Z - Tz), -1.0, 1.0);   // + = nose down
		if (A.JumpSeg != INDEX_NONE && A.JumpSeg == R.Seg && X[A.JumpSeg].LandAt != INDEX_NONE && Car.BoostTank > 0.5)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[A.JumpSeg].Frames;
			const FSkyFrame& L = Fr[FMath::Min(X[A.JumpSeg].LandAt + 6, Fr.Num() - 1)];
			FVector H(L.F.X, L.F.Y, 0);
			if (H.Normalize())
			{
				const double Dh = FVector::DotProduct(L.P - Car.Pos, H);
				const double Vh = FVector::DotProduct(Car.Vel, H), Vz = Car.Vel.Z, Dz = Car.Pos.Z - L.P.Z;
				const double Disc = Vz * Vz + 2.0 * G * Dz;
				const double TLand = Disc > 0 ? (Vz + FMath::Sqrt(Disc)) / G : 0.0;
				if (Dh > 0 && Vh * TLand < Dh + 1.0) bBoost = true;
			}
		}
	}
	A.bBoost = bBoost;
	Car.bTestBoost = bBoost;
}
