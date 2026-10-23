// Course geometry internals shared by SkyCourseModel.cpp (the bake) and SkyCourseTrack.cpp (the meshes): the geometry
// agent's own header, not part of the contract (SkyCourse.h). Metres, the car sim's frame (z up, y left).
#pragma once

#include "SkyCourse.h"

namespace SkyGeom
{
	constexpr double Gravity = 25.4;           // m/s^2, the car's gravity (SkysterCar.cpp)
	constexpr double StartLength = 30.0;       // the start piece: the grid, then the gate at its end
	constexpr double GateLength = 6.0;         // finish and checkpoint pieces, the gate in the middle
	constexpr double Clearance = 3.0;          // m between parts of the track that aren't neighbours
	constexpr double NearPath = 50.0;          // m along the track: closer than this counts as neighbours
	constexpr double ConnMinRadius = 15.0;     // generated connectors (merge, close)
	constexpr double ConnMaxSlope = 35.0;      // deg
	constexpr double DeckThick = 0.5;          // m, the slab under the deck surface
	constexpr double LipWidth = 0.3;           // m, the edge trim / rail
	constexpr double JumpLipAngle = 15.0;      // deg
	constexpr double JumpLipRadius = 30.0;     // m

	/** Smoothstep 0..1 between A and B (clamped). */
	inline double Smooth(double A, double B, double X) { const double T = FMath::Clamp((X - A) / (B - A), 0.0, 1.0); return T * T * (3.0 - 2.0 * T); }

	/** The upright frame for a heading (rad) with a roll (rad, + raises the left side) about the forward axis. */
	FSkyFrame MakeFrame(const FVector& P, double Yaw, double Roll, double Width);
	/** Heading (rad) and roll (rad) of a frame. */
	void YawRoll(const FSkyFrame& F, double& Yaw, double& Roll);

	/** Frames for one piece laid from Start (the builder's ghost). A split shows its lead-ins only; Close needs CloseTo (the
	 *  start of the course). Returns false (and an error) if the piece can't be laid. One array per drawn stretch. */
	bool PieceFrames(const FSkyPiece& Piece, const FSkyFrame& Start, int32 Lanes, const FSkyFrame* CloseTo,
		TArray<TArray<FSkyFrame>>& Out, FString& Error);

	/** Lane lines across a frame for a segment: offsets from the centre line along L (m), given the lanes the segment
	 *  starts and ends with and how a lanes piece aligns (-1 left, 0 centre, +1 right). LaneWidth is the course's (only an
	 *  aligned lanes piece uses it: its lines count lanes from the fixed edge). */
	void LaneLines(double Width, int32 Lanes0, int32 Lanes1, int32 Align, double Along01, TArray<double>& Out, double LaneWidth = SkyCourse::DefaultLaneWidth);

	/** For the track: a split's lead-in or merge connector edges that face a neighbour (the inner edges), so the trim
	 *  there can start low. Bit 0 = left edge, bit 1 = right edge. */
	int32 InnerEdges(const FSkyBaked& Baked, int32 Seg);
}
