// ASkyCourseTrack (see SkyCourse.h): the course you see and drive on.
//
// One procedural mesh component per baked segment (deck, sides and underside, edge trim, then lane lines and booster
// arrows in their own sections without collision). The rings come from the baked frames: straight stretches keep a ring
// every few metres, curved ones get extra rings between frames so the deck's facets turn by at most ~0.35 degrees
// each (the car reads the curve of a loop from how fast the support normal turns under it, and complex collision gives
// one flat normal per triangle, so coarse facets would make the loop's grip flicker). Collision is the mesh itself
// (complex as simple), tagged SkyTrack (and SkyBoost on boosters). Gates, the gantries and lights at splits and the
// switching walls are props on a separate actor tagged NoWallRide, so the car never tries to ride up them.
#include "SkyCourse.h"
#include "SkyCourseGeom.h"
#include "ProceduralMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/ChildActorComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/CollisionProfile.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/Material.h"
#include "GameFramework/Pawn.h"
#include "EngineUtils.h"
#include "Misc/Crc.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace SkyTrackImpl
{
	using namespace SkyCourse;
	using namespace SkyGeom;

	const TCHAR* const MatDeck = TEXT("/Game/McGregor/Materials/MI_RampDeck.MI_RampDeck");
	const TCHAR* const MatLine = TEXT("/Game/McGregor/Materials/MI_RampLine.MI_RampLine");
	const TCHAR* const MatLed = TEXT("/Game/McGregor/Materials/MI_LEDRed.MI_LEDRed");
	const TCHAR* const MatLedNight = TEXT("/Game/McGregor/Materials/MI_Night_LEDRed.MI_Night_LEDRed");
	const TCHAR* const MatConcrete = TEXT("/Game/McGregor/Materials/MI_SiteConcrete.MI_SiteConcrete");
	const TCHAR* const MatSteel = TEXT("/Game/McGregor/Materials/MI_GantrySteel.MI_GantrySteel");
	const TCHAR* const MatWhite = TEXT("/Game/McGregor/Materials/MI_SiteWhite.MI_SiteWhite");
	const TCHAR* const MatBlack = TEXT("/Game/McGregor/Materials/MI_SiteBlack.MI_SiteBlack");
	const TCHAR* const MatProp = TEXT("/Game/City/Street/Materials/M_StreetProp.M_StreetProp");
	const TCHAR* const MatEmissive = TEXT("/Game/SkyCity/Pickups/Materials/M_SkyEmissive.M_SkyEmissive");
	const TCHAR* const MatGlass = TEXT("/Game/Vehicles/Shared/Materials/M_CarGlass.M_CarGlass");
	const TCHAR* const CubePath = TEXT("/Engine/BasicShapes/Cube.Cube");

	UMaterialInterface* Mat(const TCHAR* Path) { return LoadObject<UMaterialInterface>(nullptr, Path); }

	/** A tinted dynamic instance of the street kit's prop master (Tint, Roughness, Metallic, EmissiveColor/Strength). */
	UMaterialInstanceDynamic* Prop(UObject* Outer, const FLinearColor& Tint, float Rough, float Metal, const FLinearColor& Em = FLinearColor::Black, float EmStr = 0)
	{
		UMaterialInterface* P = Mat(MatProp);
		if (!P) return nullptr;
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(P, Outer);
		M->SetVectorParameterValue(TEXT("Tint"), Tint);
		M->SetScalarParameterValue(TEXT("Roughness"), Rough);
		M->SetScalarParameterValue(TEXT("Metallic"), Metal);
		M->SetVectorParameterValue(TEXT("EmissiveColor"), Em);
		M->SetScalarParameterValue(TEXT("EmissiveStrength"), EmStr);
		return M;
	}
	/** A glowing dynamic instance of the pickups' emissive master (Color, Strength). */
	UMaterialInstanceDynamic* Glow(UObject* Outer, const FLinearColor& C, float Str)
	{
		UMaterialInterface* P = Mat(MatEmissive);
		if (!P) return nullptr;
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(P, Outer);
		M->SetVectorParameterValue(TEXT("Color"), C);
		M->SetScalarParameterValue(TEXT("Strength"), Str);
		return M;
	}
	UMaterialInstanceDynamic* Ghost(UObject* Outer, const FLinearColor& C, float Opacity)
	{
		UMaterialInterface* P = Mat(MatGlass);
		if (!P) return nullptr;
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(P, Outer);
		M->SetVectorParameterValue(TEXT("Tint"), C);
		M->SetScalarParameterValue(TEXT("Opacity"), Opacity);
		M->SetScalarParameterValue(TEXT("EdgeOpacity"), FMath::Min(1.f, Opacity + 0.25f));
		return M;
	}

	/** What a skin looks like: the deck's materials, how tall the edge trim is and whether (and how) it glows. */
	struct FLook
	{
		UMaterialInterface* Deck = nullptr;
		UMaterialInterface* Body = nullptr;
		UMaterialInterface* Trim = nullptr;    // the parent each segment's own trim instance is made from
		UMaterialInterface* Line = nullptr;
		UMaterialInterface* Arrow = nullptr;
		double LipH = 0.3;
		FName GlowParam;                       // the trim's emissive scalar, None = no glow
		float GlowBase = 0;
	};

	FLook MakeLook(ASkyCourseTrack* T, ESkySkin Skin)
	{
		FLook L;
		const bool bNight = T->GetWorld() && T->GetWorld()->GetMapName().Contains(TEXT("Night"));
		switch (Skin)
		{
		case ESkySkin::Classic:
			L.Deck = Prop(T, FLinearColor(0.85f, 0.22f, 0.012f), 0.32f, 0.0f);
			L.Body = Prop(T, FLinearColor(0.62f, 0.15f, 0.01f), 0.4f, 0.0f);
			L.Trim = Prop(T, FLinearColor(0.95f, 0.32f, 0.02f), 0.28f, 0.0f);
			L.Line = Prop(T, FLinearColor(0.95f, 0.75f, 0.2f), 0.4f, 0.0f);
			L.Arrow = Glow(T, FLinearColor(1.0f, 0.85f, 0.2f), 6.f);
			L.LipH = 0.6;
			break;
		case ESkySkin::Neon:
			L.Deck = Prop(T, FLinearColor(0.01f, 0.012f, 0.018f), 0.08f, 0.6f);
			L.Body = Prop(T, FLinearColor(0.015f, 0.017f, 0.024f), 0.15f, 0.5f);
			L.Trim = Mat(MatEmissive);
			L.Line = Glow(T, FLinearColor(0.1f, 0.55f, 1.0f), 2.5f);
			L.Arrow = Glow(T, FLinearColor(0.2f, 1.0f, 0.9f), 8.f);
			L.LipH = 0.22;
			L.GlowParam = TEXT("Strength");
			L.GlowBase = 9.f;
			break;
		default:
			L.Deck = Mat(MatDeck);
			L.Body = Mat(MatConcrete) ? Mat(MatConcrete) : L.Deck;
			L.Trim = Mat(bNight ? MatLedNight : MatLed);
			L.Line = Mat(MatLine);
			L.Arrow = Glow(T, FLinearColor(1.0f, 0.55f, 0.08f), 7.f);
			L.LipH = 0.3;
			L.GlowParam = bNight ? FName(TEXT("Strength")) : FName(TEXT("EmissiveStrength"));
			L.GlowBase = bNight ? 14.f : 4.f;
			break;
		}
		if (!L.Body) L.Body = L.Deck;
		if (!L.Line) L.Line = L.Deck;
		return L;
	}

	/** The trim instance a segment owns (so it can glow on its own). */
	UMaterialInstanceDynamic* TrimFor(ASkyCourseTrack* T, const FLook& L, ESkySkin Skin)
	{
		if (!L.Trim) return nullptr;
		UMaterialInstanceDynamic* M = UMaterialInstanceDynamic::Create(L.Trim, T);
		if (Skin == ESkySkin::Neon) { M->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.08f, 0.85f, 1.0f)); M->SetScalarParameterValue(TEXT("Strength"), L.GlowBase); }
		else if (!L.GlowParam.IsNone()) M->SetScalarParameterValue(L.GlowParam, L.GlowBase);
		return M;
	}

	// --- mesh building ---

	struct FSec
	{
		TArray<FVector> V;
		TArray<int32> T;
		TArray<FVector> N;
		TArray<FVector2D> UV;
		TArray<FProcMeshTangent> Tg;
		int32 Vert(const FVector& P, const FVector& Nrm, const FVector2D& Uv, const FVector& Tan)
		{
			V.Add(P); N.Add(Nrm); UV.Add(Uv); Tg.Add(FProcMeshTangent(Tan, false));
			return V.Num() - 1;
		}
		/** A triangle facing Want. Unreal's front faces wind so that (B - A) x (C - A) points AWAY from the face's normal
		 *  (see UKismetProceduralMeshLibrary::GenerateBoxMesh), so the order is fixed up here from the wanted normal. */
		void Tri(int32 A, int32 B, int32 C, const FVector& Want)
		{
			const FVector X = FVector::CrossProduct(V[B] - V[A], V[C] - V[A]);
			if ((X | Want) > 0) Swap(B, C);
			T.Add(A); T.Add(B); T.Add(C);
		}
		void Quad(int32 A, int32 B, int32 C, int32 D, const FVector& Want) { Tri(A, B, C, Want); Tri(A, C, D, Want); }
	};

	/** A ring across the track (Unreal space, cm): from a baked frame or between two. */
	struct FRing
	{
		FVector P, F, L, U;      // Unreal cm / directions
		double W = 11;           // m
		double V = 0;            // m along (UVs)
		bool bDeck = true;
		double LipL = 1, LipR = 1;   // trim height scale on each side
	};

	double Ang(const FVector& A, const FVector& B) { return FMath::Acos(FMath::Clamp(A | B, -1.0, 1.0)); }

	FQuat FrameQuat(const FSkyFrame& F) { return FQuat(FMatrix(F.F, F.L, F.U, FVector::ZeroVector)); }

	FSkyFrame Lerp(const FSkyFrame& A, const FSkyFrame& B, double T)
	{
		FSkyFrame O;
		const double D = FVector::Dist(A.P, B.P);
		const double T2 = T * T, T3 = T2 * T;
		O.P = A.P * (2 * T3 - 3 * T2 + 1) + A.F * D * (T3 - 2 * T2 + T) + B.P * (-2 * T3 + 3 * T2) + B.F * D * (T3 - T2);
		const FQuat Q = FQuat::Slerp(FrameQuat(A), FrameQuat(B), T).GetNormalized();
		O.F = Q.GetAxisX(); O.L = Q.GetAxisY(); O.U = Q.GetAxisZ();
		O.Width = FMath::Lerp(A.Width, B.Width, T);
		O.S = FMath::Lerp(A.S, B.S, T);
		O.bDeck = A.bDeck && B.bDeck;
		return O;
	}

	/** The frames a segment's mesh uses: every frame where the track bends or twists (plus extra rings between them
	 *  where it bends fast), and one every few metres where it runs straight. */
	void MeshFrames(const TArray<FSkyFrame>& Fr, TArray<FSkyFrame>& Out)
	{
		Out.Reset();
		if (Fr.Num() == 0) return;
		TArray<int32> Keep = { 0 };
		for (int32 i = 1; i + 1 < Fr.Num(); ++i)
		{
			const FSkyFrame& K = Fr[Keep.Last()];
			const FSkyFrame& N = Fr[i + 1];
			if (Fr[i].bDeck != Fr[i + 1].bDeck || Fr[i].bDeck != Fr[i - 1].bDeck || Ang(K.F, N.F) > 0.004 || Ang(K.U, N.U) > 0.004
				|| FMath::Abs(K.Width - N.Width) > 0.02 || FVector::Dist(K.P, N.P) > 3.0)
				Keep.Add(i);
		}
		if (Fr.Num() > 1) Keep.Add(Fr.Num() - 1);
		Out.Add(Fr[0]);
		for (int32 k = 1; k < Keep.Num(); ++k)
		{
			const FSkyFrame& A = Fr[Keep[k - 1]];
			const FSkyFrame& B = Fr[Keep[k]];
			// the deck pitching (loops, ramps, crests: the normal turning about L) needs fine rings, because the car reads a
			// loop's grip from how fast its support normal turns along the way; a flat curve only turns F, and roll (banks,
			// corkscrews) is handled across the deck instead (SweepDeck's columns)
			const double Pitch = FMath::Abs(FVector::DotProduct(B.U - A.U, A.F));
			const double Bend = FMath::Max(Pitch / 0.01, Ang(A.F, B.F) / 0.03);
			const int32 Sub = (A.bDeck && B.bDeck) ? FMath::Clamp(FMath::CeilToInt(Bend), 1, 24) : 1;
			for (int32 s = 1; s < Sub; ++s) Out.Add(Lerp(A, B, (double)s / Sub));
			Out.Add(B);
		}
	}

	FRing ToRing(const FSkyFrame& F, double V)
	{
		FRing R;
		R.P = ToUE(F.P); R.F = DirToUE(F.F); R.L = DirToUE(F.L); R.U = DirToUE(F.U);
		R.W = F.Width; R.V = V; R.bDeck = F.bDeck;
		return R;
	}

	FVector At(const FRing& R, double Y, double Z) { return R.P + R.L * (Y * 100.0) + R.U * (Z * 100.0); }

	/** One face of the cross-section swept along the rings: from (Y0, Z0) to (Y1, Z1) in the ring's L/U (m). */
	struct FFace { double Y0, Z0, Y1, Z1; int32 NormalAxis; double NormalSign; bool bLipL, bLipR; };

	void Sweep(FSec& S, const TArray<FRing>& Rs, int32 A, int32 B, TFunctionRef<void(const FRing&, double&, double&, double&, double&)> Ends, int32 Axis, double Sign, bool bDeckUV)
	{
		int32 Prev0 = -1, Prev1 = -1;
		for (int32 k = A; k <= B; ++k)
		{
			const FRing& R = Rs[k];
			double Y0, Z0, Y1, Z1;
			Ends(R, Y0, Z0, Y1, Z1);
			const FVector Nrm = (Axis == 0 ? R.U : Axis == 1 ? R.L : R.F) * Sign;
			const int32 I0 = S.Vert(At(R, Y0, Z0), Nrm, bDeckUV ? FVector2D(Y0, R.V) : FVector2D(Z0, R.V), R.F);
			const int32 I1 = S.Vert(At(R, Y1, Z1), Nrm, bDeckUV ? FVector2D(Y1, R.V) : FVector2D(Z1, R.V), R.F);
			if (Prev0 >= 0) S.Quad(Prev0, Prev1, I1, I0, Nrm);
			Prev0 = I0; Prev1 = I1;
		}
	}

	/** The deck's top from ring A to ring B. Where the deck rolls (bank in and out, corkscrews, wallrides) a quad between
	 *  two rings isn't flat, and split on one diagonal across a whole lane its two triangles tilt fore and aft by about
	 *  half the width times the roll per metre: the car's support normal would flip as it crosses the diagonal and the
	 *  bump throws it off (its "airborne" test is 2.5 m/s off the surface per step). So the deck is cut into columns
	 *  narrow enough that each triangle tilts less than ~0.015 rad. */
	void SweepDeck(FSec& S, const TArray<FRing>& Rs, int32 A, int32 B, double Lw)
	{
		for (int32 k = A; k < B; ++k)
		{
			const FRing& R0 = Rs[k];
			const FRing& R1 = Rs[k + 1];
			const double Ds = FMath::Max(FVector::Dist(R0.P, R1.P) / 100.0, 1e-3);
			const double Roll = FMath::Abs(FVector::DotProduct(R1.U - R0.U, R0.L));
			const double Y0 = R0.W * 0.5 - Lw, Y1 = R1.W * 0.5 - Lw;
			const int32 N = FMath::Clamp(FMath::CeilToInt(2.0 * FMath::Max(Y0, Y1) * Roll / (0.03 * Ds)), 1, 128);
			const int32 Base = S.V.Num();
			for (int32 j = 0; j <= N; ++j)
			{
				const double T = (double)j / N;
				const double Ya = Y0 - 2.0 * Y0 * T, Yb = Y1 - 2.0 * Y1 * T;
				S.Vert(At(R0, Ya, 0), R0.U, FVector2D(Ya, R0.V), R0.F);
				S.Vert(At(R1, Yb, 0), R1.U, FVector2D(Yb, R1.V), R1.F);
			}
			for (int32 j = 0; j < N; ++j)
			{
				const int32 A0 = Base + j * 2, B0 = A0 + 1, A1 = A0 + 2, B1 = A0 + 3;
				S.Quad(A0, A1, B1, B0, (R0.U + R1.U).GetSafeNormal());
			}
		}
	}

	void Cap(FSec& S, const FRing& R, double Lip, double Thick, double Sign)
	{
		const double Yo = R.W * 0.5;
		const FVector Nrm = R.F * Sign;
		const int32 A = S.Vert(At(R, Yo, Lip), Nrm, FVector2D(Yo, Lip), R.L);
		const int32 B = S.Vert(At(R, -Yo, Lip), Nrm, FVector2D(-Yo, Lip), R.L);
		const int32 C = S.Vert(At(R, -Yo, -Thick), Nrm, FVector2D(-Yo, -Thick), R.L);
		const int32 D = S.Vert(At(R, Yo, -Thick), Nrm, FVector2D(Yo, -Thick), R.L);
		S.Quad(A, B, C, D, Nrm);
	}

	/** A flat strip painted on the deck along the rings (lane lines), Y0..Y1 across, a centimetre or two up. */
	void Paint(FSec& S, const TArray<FRing>& Rs, int32 A, int32 B, double Y0, double Y1)
	{
		Sweep(S, Rs, A, B, [Y0, Y1](const FRing&, double& a, double& b, double& c, double& d) { a = Y0; b = 0.015; c = Y1; d = 0.015; }, 0, 1.0, true);
	}

	/** A rectangle painted on the deck around a point (Unreal), with its own axes. */
	void PaintRect(FSec& S, const FVector& C, const FVector& F, const FVector& L, const FVector& U, double HalfF, double HalfL, double Line)
	{
		auto Bar = [&](const FVector& Ctr, const FVector& Ax, double HalfAlong, double HalfAcross, const FVector& Across)
		{
			const FVector Up = U * 1.5;
			const int32 A = S.Vert(Ctr + Up + Ax * HalfAlong + Across * HalfAcross, U, FVector2D(0, 0), Ax);
			const int32 B = S.Vert(Ctr + Up + Ax * HalfAlong - Across * HalfAcross, U, FVector2D(1, 0), Ax);
			const int32 D = S.Vert(Ctr + Up - Ax * HalfAlong - Across * HalfAcross, U, FVector2D(1, 1), Ax);
			const int32 E = S.Vert(Ctr + Up - Ax * HalfAlong + Across * HalfAcross, U, FVector2D(0, 1), Ax);
			S.Quad(A, B, D, E, U);
		};
		const double Hf = HalfF * 100, Hl = HalfL * 100, Ln = Line * 50;
		Bar(C + F * (Hf - Ln), L, Hl, Ln, F);
		Bar(C - F * (Hf - Ln), L, Hl, Ln, F);
		Bar(C + L * (Hl - Ln), F, Hf, Ln, L);
		Bar(C - L * (Hl - Ln), F, Hf, Ln, L);
	}

	/** A box (Unreal cm) into a mesh section: centre, axes, half sizes. */
	void Box(FSec& S, const FVector& C, const FVector& X, const FVector& Y, const FVector& Z, const FVector& H)
	{
		const FVector Ax[3] = { X, Y, Z };
		for (int32 a = 0; a < 3; ++a)
			for (const double Sg : { -1.0, 1.0 })
			{
				const FVector N = Ax[a] * Sg;
				const FVector U = Ax[(a + 1) % 3], W = Ax[(a + 2) % 3];
				const double Hu = H[(a + 1) % 3], Hw = H[(a + 2) % 3];
				const FVector Ctr = C + N * H[a];
				const int32 A0 = S.Vert(Ctr + U * Hu + W * Hw, N, FVector2D(0, 0), U);
				const int32 A1 = S.Vert(Ctr - U * Hu + W * Hw, N, FVector2D(1, 0), U);
				const int32 A2 = S.Vert(Ctr - U * Hu - W * Hw, N, FVector2D(1, 1), U);
				const int32 A3 = S.Vert(Ctr + U * Hu - W * Hw, N, FVector2D(0, 1), U);
				S.Quad(A0, A1, A2, A3, N);
			}
	}

	void Upload(UProceduralMeshComponent* C, int32 Index, const FSec& S, bool bCollide)
	{
		if (S.V.Num() == 0 || S.T.Num() == 0) { C->ClearMeshSection(Index); return; }
		C->CreateMeshSection(Index, S.V, S.T, S.N, S.UV, TArray<FColor>(), S.Tg, bCollide);
	}

	/** JSON paths for every sequence (for messages), as the bake names them. */
	TArray<FString> SeqPaths(const FSkyCourse& C)
	{
		TArray<FString> P;
		P.SetNum(C.Seqs.Num());
		if (P.Num()) P[0] = TEXT("pieces");
		TArray<int32> Stack = { 0 };
		TSet<int32> Seen;
		while (Stack.Num())
		{
			const int32 S = Stack.Pop();
			if (!C.Seqs.IsValidIndex(S) || Seen.Contains(S)) continue;
			Seen.Add(S);
			for (int32 i = 0; i < C.Seqs[S].Pieces.Num(); ++i)
			{
				const FSkyPiece& Pc = C.Seqs[S].Pieces[i];
				for (int32 b = 0; b < Pc.Branches.Num(); ++b)
					if (C.Seqs.IsValidIndex(Pc.Branches[b].Seq) && !Seen.Contains(Pc.Branches[b].Seq))
					{
						P[Pc.Branches[b].Seq] = FString::Printf(TEXT("%s[%d].branches[%d].pieces"), *P[S], i, b);
						Stack.Add(Pc.Branches[b].Seq);
					}
			}
		}
		return P;
	}

	FString SegLabel(const FSkyCourse& C, const TArray<FString>& Paths, const FSkySegment& S)
	{
		const FString Base = Paths.IsValidIndex(S.Seq) ? FString::Printf(TEXT("%s[%d]"), *Paths[S.Seq], S.Piece) : FString(TEXT("pieces[?]"));
		switch (S.Kind)
		{
		case ESkySeg::SplitLead: return FString::Printf(TEXT("%s.branches[%d] (lead-in)"), *Base, S.Branch);
		case ESkySeg::MergeLead: return FString::Printf(TEXT("%s.branches[%d] (merge connector)"), *Base, S.Branch);
		case ESkySeg::MergeTrunk: return Base + TEXT(" (split) merge");
		default: return FString::Printf(TEXT("%s (%s)"), *Base, PieceName(S.Type));
		}
	}

	FString Num1(double V) { return FString::Printf(TEXT("%.1f"), V); }

	/** The failed bake Build returns when the course has errors (the standing track keeps its own bake). */
	FSkyBaked GFailed;
}

/** Builds and updates the track's components (a friend of ASkyCourseTrack). */
class FSkyCourseTrackImpl
{
public:
	static uint32 HashSeg(const ASkyCourseTrack* T, const FSkyCourse& C, const FSkyBaked& B, int32 i, ESkySkin Skin);
	static void BuildSeg(ASkyCourseTrack* T, UProceduralMeshComponent* M, const FSkyCourse& C, const FSkyBaked& B, int32 i, const SkyTrackImpl::FLook& L, ESkySkin Skin);
	static void BuildProps(ASkyCourseTrack* T, const FSkyCourse& C, const FSkyBaked& B, const SkyTrackImpl::FLook& L);
	static void GroundChecks(ASkyCourseTrack* T, const FSkyCourse& C, FSkyBaked& B);
	static AActor* Holder(ASkyCourseTrack* T, bool bCreate);
	static UProceduralMeshComponent* NewMesh(AActor* Owner, USceneComponent* Parent, const TCHAR* Tag);
};

ASkyCourseTrack::ASkyCourseTrack()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

UProceduralMeshComponent* FSkyCourseTrackImpl::NewMesh(AActor* Owner, USceneComponent* Parent, const TCHAR* Tag)
{
	using namespace SkyTrackImpl;
	UProceduralMeshComponent* M = NewObject<UProceduralMeshComponent>(Owner, NAME_None, RF_Transient);
	M->SetupAttachment(Parent);
	M->SetUsingAbsoluteLocation(true);
	M->SetUsingAbsoluteRotation(true);
	M->SetUsingAbsoluteScale(true);
	M->bUseAsyncCooking = true;
	M->bUseComplexAsSimpleCollision = true;
	M->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	if (Tag) M->ComponentTags.Add(Tag);
	M->RegisterComponent();
	M->SetWorldTransform(FTransform::Identity);
	return M;
}

AActor* FSkyCourseTrackImpl::Holder(ASkyCourseTrack* T, bool bCreate)
{
	using namespace SkyTrackImpl;
	// the props live on a child actor (tagged NoWallRide, so the car never tries to ride up a gate post or a barrier);
	// a child actor component makes it go when the track goes
	UChildActorComponent* CA = T->FindComponentByClass<UChildActorComponent>();
	if (CA && CA->GetChildActor()) return CA->GetChildActor();
	if (!bCreate || !T->GetWorld()) return nullptr;
	if (!CA)
	{
		CA = NewObject<UChildActorComponent>(T, NAME_None, RF_Transient);
		CA->SetupAttachment(T->GetRootComponent());
		CA->SetUsingAbsoluteLocation(true);
		CA->SetUsingAbsoluteRotation(true);
		CA->SetChildActorClass(AActor::StaticClass());
		CA->RegisterComponent();
	}
	CA->CreateChildActor();
	AActor* H = CA->GetChildActor();
	if (!H) return nullptr;
	if (!H->GetRootComponent())
	{
		USceneComponent* R = NewObject<USceneComponent>(H, TEXT("Root"));
		H->SetRootComponent(R);
		R->RegisterComponent();
	}
	H->Tags.AddUnique(TEXT("NoWallRide"));
	H->Tags.AddUnique(TEXT("SkyTrackProps"));
	return H;
}

uint32 FSkyCourseTrackImpl::HashSeg(const ASkyCourseTrack* T, const FSkyCourse& C, const FSkyBaked& B, int32 i, ESkySkin Skin)
{
	using namespace SkyTrackImpl;
	const FSkySegment& S = B.Segs[i];
	TArray<int32> Q;
	Q.Reserve(S.Frames.Num() * 11 + 32);
	auto Mm = [](double V) { return (int32)FMath::RoundToDouble(V * 1000.0); };
	Q.Add((int32)S.Kind); Q.Add((int32)S.Type); Q.Add(S.Lanes); Q.Add((int32)Skin); Q.Add(InnerEdges(B, i));
	bool bPrev = false;
	for (const FSkySegment& O : B.Segs) if (O.Next.Contains(i)) { bPrev = true; break; }
	Q.Add(bPrev ? 1 : 0); Q.Add(S.Next.Num() ? 1 : 0);
	if (S.Kind == ESkySeg::Piece && C.Seqs.IsValidIndex(S.Seq) && C.Seqs[S.Seq].Pieces.IsValidIndex(S.Piece)) Q.Add(C.Seqs[S.Seq].Pieces[S.Piece].Align);
	for (const FSkyBaked::FGate& G : B.Gates) if (G.Seg == i) { Q.Add(1000 + (int32)G.Type); Q.Add(Mm(G.At.S)); }
	if (i == 0) for (const FTransform& G : B.Grid) { Q.Add(Mm(G.GetLocation().X)); Q.Add(Mm(G.GetLocation().Y)); }
	for (const FSkyFrame& F : S.Frames)
	{
		Q.Add(Mm(F.P.X)); Q.Add(Mm(F.P.Y)); Q.Add(Mm(F.P.Z));
		Q.Add(Mm(F.U.X)); Q.Add(Mm(F.U.Y)); Q.Add(Mm(F.U.Z));
		Q.Add(Mm(F.F.X)); Q.Add(Mm(F.F.Y));
		Q.Add(Mm(F.Width)); Q.Add(F.bDeck ? 1 : 0); Q.Add(Mm(F.S));
	}
	return FCrc::MemCrc32(Q.GetData(), Q.Num() * sizeof(int32));
}

void FSkyCourseTrackImpl::BuildSeg(ASkyCourseTrack* T, UProceduralMeshComponent* M, const FSkyCourse& C, const FSkyBaked& B, int32 i, const SkyTrackImpl::FLook& L, ESkySkin Skin)
{
	using namespace SkyTrackImpl;
	const FSkySegment& S = B.Segs[i];
	TArray<FSkyFrame> Fr;
	MeshFrames(S.Frames, Fr);
	TArray<FRing> Rs;
	Rs.Reserve(Fr.Num());
	double Along = 0;
	const double V0 = S.Frames.Num() ? S.Frames[0].S : 0;
	for (int32 k = 0; k < Fr.Num(); ++k)
	{
		if (k) Along += FVector::Dist(Fr[k].P, Fr[k - 1].P);
		Rs.Add(ToRing(Fr[k], V0 + Along));
	}
	const double Total = FMath::Max(Along, 1e-3);
	// the inner edges of a split's lead-ins (and a merge's connectors) start (end) low where the leads touch
	const int32 Inner = InnerEdges(B, i);
	if (Inner)
	{
		double D = 0;
		for (int32 k = 0; k < Rs.Num(); ++k)
		{
			if (k) D += FVector::Dist(Rs[k].P, Rs[k - 1].P) / 100.0;
			const double Away = S.Kind == ESkySeg::SplitLead ? D : Total - D;
			const double Kk = Smooth(0, 8.0, Away);
			if (Inner & 1) Rs[k].LipL = Kk;
			if (Inner & 2) Rs[k].LipR = Kk;
		}
	}
	// where a corkscrew or wallride has the deck on its side or upside down, the trim grows into 1 m rails (like toy
	// track's side walls): gravity pushes the car across a rolled deck, and off its middle a twisting deck gets steep,
	// so the rails bounce it back instead of letting it slide off (under 2.5 m they stay kerbs, not walls to ride)
	if ((S.Type == ESkyPiece::Corkscrew || S.Type == ESkyPiece::WallRide) && S.Kind == ESkySeg::Piece && L.LipH > 0)
		for (FRing& R : Rs)
		{
			const double Rail = 1.0 * Smooth(0.08, 0.35, 1.0 - R.U.Z) / L.LipH;
			R.LipL = FMath::Max(R.LipL, Rail);
			R.LipR = FMath::Max(R.LipR, Rail);
		}
	bool bPrev = false;
	for (const FSkySegment& O : B.Segs) if (O.Next.Contains(i)) { bPrev = true; break; }
	const bool bNext = S.Next.Num() > 0;

	FSec Deck, Body, Trim, Lines, Arrows;
	const double Lw = LipWidth, Th = DeckThick, LipH = L.LipH;
	// runs of deck (a jump's gap has none)
	int32 k = 0;
	while (k < Rs.Num())
	{
		if (!Rs[k].bDeck) { ++k; continue; }
		int32 E = k;
		while (E + 1 < Rs.Num() && Rs[E + 1].bDeck) ++E;
		if (E > k)
		{
			SweepDeck(Deck, Rs, k, E, Lw);
			if (LipH > 0)
			{
				Sweep(Trim, Rs, k, E, [Lw, LipH](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5 - Lw; b = 0; c = R.W * 0.5 - Lw; d = LipH * R.LipL; }, 1, -1.0, false);
				Sweep(Trim, Rs, k, E, [Lw, LipH](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5 - Lw; b = LipH * R.LipL; c = R.W * 0.5; d = LipH * R.LipL; }, 0, 1.0, true);
				Sweep(Trim, Rs, k, E, [Lw, LipH](const FRing& R, double& a, double& b, double& c, double& d) { a = -(R.W * 0.5 - Lw); b = 0; c = -(R.W * 0.5 - Lw); d = LipH * R.LipR; }, 1, 1.0, false);
				Sweep(Trim, Rs, k, E, [Lw, LipH](const FRing& R, double& a, double& b, double& c, double& d) { a = -(R.W * 0.5 - Lw); b = LipH * R.LipR; c = -R.W * 0.5; d = LipH * R.LipR; }, 0, 1.0, true);
			}
			Sweep(Body, Rs, k, E, [LipH, Th](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5; b = LipH * R.LipL; c = R.W * 0.5; d = -Th; }, 1, 1.0, false);
			Sweep(Body, Rs, k, E, [Th](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5; b = -Th; c = -R.W * 0.5; d = -Th; }, 0, -1.0, true);
			Sweep(Body, Rs, k, E, [LipH, Th](const FRing& R, double& a, double& b, double& c, double& d) { a = -R.W * 0.5; b = LipH * R.LipR; c = -R.W * 0.5; d = -Th; }, 1, -1.0, false);
			// end walls where the deck stops in the open (a jump's lip and pad, the ends of a course)
			if (k > 0 || !bPrev) Cap(Body, Rs[k], LipH, Th, -1.0);
			if (E < Rs.Num() - 1 || !bNext) Cap(Body, Rs[E], LipH, Th, 1.0);
			// lane lines
			int32 Lanes0 = S.Lanes, Lanes1 = S.Lanes, Align = 0;
			if (S.Kind == ESkySeg::Piece && S.Type == ESkyPiece::Lanes)
			{
				Lanes0 = FMath::Clamp(FMath::RoundToInt(S.Frames[0].Width / LaneWidth), MinLanes, MaxLanes);
				if (C.Seqs.IsValidIndex(S.Seq) && C.Seqs[S.Seq].Pieces.IsValidIndex(S.Piece)) Align = C.Seqs[S.Seq].Pieces[S.Piece].Align;
			}
			else if (S.Kind == ESkySeg::MergeTrunk) Lanes0 = FMath::Clamp(FMath::RoundToInt(S.Frames[0].Width / LaneWidth), MinLanes, MaxLanes);
			TArray<double> Ya, Yb;
			double D = 0;
			for (int32 r = k; r < E; ++r)
			{
				const double D1 = D + FVector::Dist(Rs[r].P, Rs[r + 1].P) / 100.0;
				LaneLines(Rs[r].W, Lanes0, Lanes1, Align, D / Total, Ya);
				LaneLines(Rs[r + 1].W, Lanes0, Lanes1, Align, D1 / Total, Yb);
				if (Ya.Num() == Yb.Num())
					for (int32 l = 0; l < Ya.Num(); ++l)
					{
						TArray<FRing> Two = { Rs[r], Rs[r + 1] };
						// the line follows its own offset, which can drift across a lanes piece
						const double A0 = Ya[l], B0 = Yb[l];
						Sweep(Lines, Two, 0, 1, [A0, B0, &Two](const FRing& R, double& a, double& b, double& c, double& d)
						{
							const double Y = (&R == &Two[0]) ? A0 : B0;
							a = Y - 0.075; b = 0.015; c = Y + 0.075; d = 0.015;
						}, 0, 1.0, true);
					}
				D = D1;
			}
		}
		k = E + 1;
	}
	// gate lines across the deck, the grid boxes on the start
	for (const FSkyBaked::FGate& G : B.Gates)
	{
		if (G.Seg != i) continue;
		const FRing R = ToRing(G.At, 0);
		const double Hw = G.At.Width * 0.5 - Lw;
		FSec& Dst = Lines;
		const double Depth = G.Type == ESkyPiece::Checkpoint ? 0.4 : 0.6;
		const int32 A = Dst.Vert(At(R, Hw, 0.016) + R.F * (Depth * 50), R.U, FVector2D(0, 0), R.F);
		const int32 Bv = Dst.Vert(At(R, -Hw, 0.016) + R.F * (Depth * 50), R.U, FVector2D(1, 0), R.F);
		const int32 Cv = Dst.Vert(At(R, -Hw, 0.016) - R.F * (Depth * 50), R.U, FVector2D(1, 1), R.F);
		const int32 Dv = Dst.Vert(At(R, Hw, 0.016) - R.F * (Depth * 50), R.U, FVector2D(0, 1), R.F);
		Dst.Quad(A, Bv, Cv, Dv, R.U);
	}
	if (i == 0)
		for (const FTransform& G : B.Grid)
		{
			const FQuat Q = G.GetRotation();
			PaintRect(Lines, G.GetLocation(), Q.GetAxisX(), Q.GetAxisY(), Q.GetAxisZ(), 2.6, 1.35, 0.12);
		}
	// booster arrows: chevrons every 2.5 m pointing along the track
	if (S.Type == ESkyPiece::Booster && S.Kind == ESkySeg::Piece && S.Frames.Num() > 1)
	{
		const double Len = S.Frames.Last().S - S.Frames[0].S;
		for (double D = 1.5; D < Len - 1.0; D += 2.5)
		{
			const double Fk = D / Len * (S.Frames.Num() - 1);
			const int32 a = FMath::Clamp(FMath::FloorToInt(Fk), 0, S.Frames.Num() - 2);
			const FRing R = ToRing(Lerp(S.Frames[a], S.Frames[a + 1], Fk - a), 0);
			const double Half = FMath::Min(R.W * 0.32, 4.5), Deep = 0.9, Bar = 0.45;
			for (const double Sg : { 1.0, -1.0 })
			{
				// one arm of the ">" from the centre tip out to the side and back
				const FVector Tip = At(R, 0, 0.03) + R.F * (Deep * 100);
				const FVector Out = At(R, Sg * Half, 0.03);
				const int32 A0 = Arrows.Vert(Tip, R.U, FVector2D(0, 0), R.F);
				const int32 A1 = Arrows.Vert(Out, R.U, FVector2D(1, 0), R.F);
				const int32 A2 = Arrows.Vert(Out - R.F * (Bar * 100), R.U, FVector2D(1, 1), R.F);
				const int32 A3 = Arrows.Vert(Tip - R.F * (Bar * 100), R.U, FVector2D(0, 1), R.F);
				Arrows.Quad(A0, A1, A2, A3, R.U);
			}
		}
	}
	Upload(M, 0, Deck, true);
	Upload(M, 1, Body, true);
	Upload(M, 2, Trim, true);
	Upload(M, 3, Lines, false);
	Upload(M, 4, Arrows, false);
	M->SetMaterial(0, L.Deck);
	M->SetMaterial(1, L.Body);
	M->SetMaterial(2, TrimFor(T, L, Skin));
	M->SetMaterial(3, L.Line);
	M->SetMaterial(4, L.Arrow ? L.Arrow : L.Line);
	M->ComponentTags.Remove(TEXT("SkyBoost"));
	if (S.Type == ESkyPiece::Booster && S.Kind == ESkySeg::Piece) M->ComponentTags.AddUnique(TEXT("SkyBoost"));
}

void FSkyCourseTrackImpl::BuildProps(ASkyCourseTrack* T, const FSkyCourse& C, const FSkyBaked& B, const SkyTrackImpl::FLook& L)
{
	using namespace SkyTrackImpl;
	// clear the old props (the holder actor stays)
	AActor* H = Holder(T, true);
	for (UPrimitiveComponent* P : T->Props) if (P) P->DestroyComponent();
	T->Props.Reset();
	if (!H) return;
	UProceduralMeshComponent* PM = NewMesh(H, H->GetRootComponent(), TEXT("SkyTrackProps"));
	PM->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	T->Props.Add(PM);
	FSec Steel, White, Black, Band, Glass;
	auto Axes = [](const FSkyFrame& F, FVector& X, FVector& Y, FVector& Z) { X = DirToUE(F.F); Y = DirToUE(F.L); Z = DirToUE(F.U); };
	// gate arches: posts outside the deck edges, a beam, and a chequered (start, finish) or glowing (checkpoint) band
	for (const FSkyBaked::FGate& G : B.Gates)
	{
		FVector X, Y, Z;
		Axes(G.At, X, Y, Z);
		const FVector P = ToUE(G.At.P);
		const double Hw = G.At.Width * 0.5 + 0.7;
		const double Ht = 7.0;
		for (const double Sg : { 1.0, -1.0 })
			Box(Steel, P + Y * (Sg * Hw * 100) + Z * (Ht * 50 - 50), X, Y, Z, FVector(30, 30, Ht * 50 + 50));
		Box(Steel, P + Z * (Ht * 100), X, Y, Z, FVector(35, Hw * 100 + 30, 30));
		const double BandH = 1.2, Sq = 0.6;
		const FVector BandC = P + Z * ((Ht - 0.3 - BandH * 0.5) * 100);
		if (G.Type == ESkyPiece::Checkpoint)
			Box(Band, BandC, X, Y, Z, FVector(15, Hw * 100 - 30, BandH * 50));
		else
		{
			const int32 N = FMath::Max(2, FMath::FloorToInt((Hw * 2 - 0.6) / Sq));
			const double W = (Hw * 2 - 0.6) / N;
			for (int32 c = 0; c < N; ++c)
				for (int32 r = 0; r < 2; ++r)
				{
					const FVector Ctr = BandC + Y * ((-(Hw - 0.3) + W * (c + 0.5)) * 100) + Z * ((r - 0.5) * BandH * 50);
					Box(((c + r) % 2) ? Black : White, Ctr, X, Y, Z, FVector(15, W * 50, BandH * 25));
				}
		}
	}
	// splits: a gantry with a signal light over each branch, and a barrier slab across each branch for wall gates
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, CubePath);
	for (int32 s = 0; s < B.Splits.Num(); ++s)
	{
		const FSkyBaked::FSplitInfo& Sp = B.Splits[s];
		if (Sp.Gate == ESkyGate::None) continue;
		FVector X, Y, Z;
		Axes(Sp.At, X, Y, Z);
		const FVector P = ToUE(Sp.At.P) + X * 300.0;
		const double Hw = Sp.At.Width * 0.5 + 0.7, Ht = 6.5;
		for (const double Sg : { 1.0, -1.0 })
			Box(Steel, P + Y * (Sg * Hw * 100) + Z * (Ht * 50 - 50), X, Y, Z, FVector(25, 25, Ht * 50 + 50));
		Box(Steel, P + Z * (Ht * 100), X, Y, Z, FVector(30, Hw * 100 + 25, 30));
		for (int32 b = 0; b < Sp.LeadSegs.Num(); ++b)
		{
			const FSkySegment& Ld = B.Segs[Sp.LeadSegs[b]];
			if (Ld.Frames.Num() == 0) continue;
			const double Across = FVector::DotProduct(Ld.Frames[0].P - Sp.At.P, Sp.At.L);
			const FVector LampAt = P + Y * (Across * 100) + Z * ((Ht - 0.75) * 100);
			Box(Steel, LampAt - X * 12, X, Y, Z, FVector(12, 70, 50));   // housing
			if (Cube)
			{
				UStaticMeshComponent* Lamp = NewObject<UStaticMeshComponent>(H, NAME_None, RF_Transient);
				Lamp->SetupAttachment(H->GetRootComponent());
				Lamp->SetStaticMesh(Cube);
				Lamp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				Lamp->SetCastShadow(false);
				Lamp->ComponentTags.Add(*FString::Printf(TEXT("SkyLight_%d_%d"), s, b));
				Lamp->RegisterComponent();
				Lamp->SetWorldTransform(FTransform(FRotationMatrix::MakeFromXZ(X, Z).Rotator(), LampAt + X * 2, FVector(0.1, 1.2, 0.8)));
				Lamp->SetMaterial(0, Glow(T, FLinearColor(0.1f, 1.f, 0.2f), 25.f));
				T->Props.Add(Lamp);
			}
			if (Sp.Gate == ESkyGate::Wall && Cube && Ld.Frames.Num() > 2)
			{
				// across the lead-in where the leads have drawn apart a little
				const int32 k = FMath::Clamp(FMath::RoundToInt(10.0 / SampleStep), 0, Ld.Frames.Num() - 1);
				const FSkyFrame& F = Ld.Frames[k];
				FVector WX, WY, WZ;
				Axes(F, WX, WY, WZ);
				UStaticMeshComponent* Wall = NewObject<UStaticMeshComponent>(H, NAME_None, RF_Transient);
				Wall->SetupAttachment(H->GetRootComponent());
				Wall->SetStaticMesh(Cube);
				Wall->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
				Wall->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
				Wall->ComponentTags.Add(*FString::Printf(TEXT("SkyWall_%d_%d"), s, b));
				Wall->RegisterComponent();
				const double Wd = F.Width - 2 * LipWidth - 0.1;
				Wall->SetWorldTransform(FTransform(FRotationMatrix::MakeFromXZ(WX, WZ).Rotator(), ToUE(F.P) + WZ * 80.0, FVector(0.5, Wd, 1.6)));
				Wall->SetMaterial(0, Mat(MatLed));
				T->Props.Add(Wall);
			}
		}
	}
	Upload(PM, 0, Steel, true);
	Upload(PM, 1, White, true);
	Upload(PM, 2, Black, true);
	Upload(PM, 3, Band, true);
	PM->SetMaterial(0, Mat(MatSteel) ? Mat(MatSteel) : L.Body);
	PM->SetMaterial(1, Mat(MatWhite) ? Mat(MatWhite) : L.Line);
	PM->SetMaterial(2, Mat(MatBlack) ? Mat(MatBlack) : L.Body);
	PM->SetMaterial(3, Glow(T, C.Skin == ESkySkin::Neon ? FLinearColor(1.f, 0.2f, 0.9f) : FLinearColor(0.1f, 0.75f, 1.f), 6.f));
	// lap 1's routing until the race says otherwise
	for (int32 s = 0; s < B.Splits.Num(); ++s)
		for (int32 b = 0; b < B.Splits[s].OpenLaps.Num(); ++b)
			T->SetBranchOpen(s, b, B.Splits[s].OpenLaps[b].Contains(1));
}

void FSkyCourseTrackImpl::GroundChecks(ASkyCourseTrack* T, const FSkyCourse& C, FSkyBaked& B)
{
	using namespace SkyTrackImpl;
	UWorld* W = T->GetWorld();
	if (!W) return;
	FCollisionQueryParams Q(SCENE_QUERY_STAT(SkyCourseGround), true, T);
	if (AActor* H = Holder(T, false)) Q.AddIgnoredActor(H);
	for (TActorIterator<APawn> It(W); It; ++It) Q.AddIgnoredActor(*It);
	for (TActorIterator<ASkyCourseTrack> It(W); It; ++It) Q.AddIgnoredActor(*It);
	const TArray<FString> Paths = SeqPaths(C);
	int32 Said = 0;
	for (int32 i = 0; i < B.Segs.Num(); ++i)
	{
		const FSkySegment& S = B.Segs[i];
		const bool bStart = i == 0 && S.Type == ESkyPiece::Start;
		double Sunk = 0, High = 0;
		const int32 Step = S.Frames.Num() > 400 ? 8 : 4;
		for (int32 k = 0; k < S.Frames.Num(); k += Step)
		{
			const FSkyFrame& F = S.Frames[k];
			if (!F.bDeck) continue;
			double Lowest = 1e9;
			for (const double Sd : { -1.0, 0.0, 1.0 })
			{
				const FVector Pm = F.P + F.L * (Sd * FMath::Max(0.0, F.Width * 0.5 - 0.6));
				FHitResult Hit;
				// from well above (the ground is one-sided: a trace starting under it wouldn't see it); an upward-facing
				// surface over the deck is ground the deck has sunk into (the tracks themselves are ignored)
				if (W->LineTraceSingleByChannel(Hit, ToUE(Pm + FVector(0, 0, 30.0)), ToUE(Pm - FVector(0, 0, 400.0)), ECC_Visibility, Q))
				{
					const double Gz = Hit.ImpactPoint.Z / 100.0;
					if (Gz > Pm.Z + 0.5 && Hit.ImpactNormal.Z > 0.7 && !bStart) Sunk = FMath::Max(Sunk, Gz - Pm.Z);
					Lowest = FMath::Min(Lowest, Pm.Z - Gz);
				}
			}
			if (Lowest < 1e8) High = FMath::Max(High, Lowest);
		}
		const FString Lb = SegLabel(C, Paths, S);
		if (Sunk > 0.5) B.Errors.Add(FString::Printf(TEXT("%s sinks %s m into the ground: raise the track there (or the start)"), *Lb, *Num1(Sunk)));
		const bool bTall = S.Type == ESkyPiece::Loop || S.Type == ESkyPiece::Corkscrew || S.Type == ESkyPiece::WallRide;
		if (High > 18.0 && Said < 6 && !bTall)
		{
			++Said;
			B.Warnings.Add(FString::Printf(TEXT("%s runs %s m above the ground with nothing under it: a fall from there is a long drop"), *Lb, *Num1(High)));
		}
	}
	B.bValid = B.Errors.Num() == 0;
}

// --- the actor ----------------------------------------------------------------------------------------------------------

const FSkyBaked& ASkyCourseTrack::Build(const FSkyCourse& Course, const FBox& BuildArea)
{
	using namespace SkyTrackImpl;
	FSkyBaked New;
	SkyCourse::Bake(Course, BuildArea, New);
	if (New.bValid) FSkyCourseTrackImpl::GroundChecks(this, Course, New);
	if (!New.bValid)
	{
		// the last good track stays standing; this bake carries the errors
		GFailed = MoveTemp(New);
		return GFailed;
	}
	Baked = MoveTemp(New);
	const FLook L = MakeLook(this, Course.Skin);
	// reuse the components whose segment didn't change (by hash, wherever they are in the list now)
	TMultiMap<uint32, int32> Old;
	for (int32 i = 0; i < SegMeshes.Num(); ++i) if (SegMeshes[i] && SegHashes.IsValidIndex(i)) Old.Add(SegHashes[i], i);
	TArray<TObjectPtr<UProceduralMeshComponent>> NewMeshes;
	TArray<uint32> NewHashes;
	TSet<int32> Taken;
	for (int32 i = 0; i < Baked.Segs.Num(); ++i)
	{
		const uint32 H = FSkyCourseTrackImpl::HashSeg(this, Course, Baked, i, Course.Skin);
		UProceduralMeshComponent* M = nullptr;
		TArray<int32> Same;
		Old.MultiFind(H, Same);
		for (const int32 o : Same) if (!Taken.Contains(o)) { Taken.Add(o); M = SegMeshes[o]; break; }
		if (!M)
		{
			M = FSkyCourseTrackImpl::NewMesh(this, RootComponent, TEXT("SkyTrack"));
			FSkyCourseTrackImpl::BuildSeg(this, M, Course, Baked, i, L, Course.Skin);
		}
		NewMeshes.Add(M);
		NewHashes.Add(H);
	}
	for (int32 i = 0; i < SegMeshes.Num(); ++i) if (SegMeshes[i] && !Taken.Contains(i)) SegMeshes[i]->DestroyComponent();
	SegMeshes = MoveTemp(NewMeshes);
	SegHashes = MoveTemp(NewHashes);
	BuiltSkin = Course.Skin;
	FSkyCourseTrackImpl::BuildProps(this, Course, Baked, L);
	return Baked;
}

void ASkyCourseTrack::SetBranchOpen(int32 SplitIndex, int32 Branch, bool bOpen)
{
	using namespace SkyTrackImpl;
	const FName LightTag(*FString::Printf(TEXT("SkyLight_%d_%d"), SplitIndex, Branch));
	const FName WallTag(*FString::Printf(TEXT("SkyWall_%d_%d"), SplitIndex, Branch));
	for (UPrimitiveComponent* P : Props)
	{
		if (!P) continue;
		if (P->ComponentHasTag(LightTag))
			if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(P->GetMaterial(0)))
				M->SetVectorParameterValue(TEXT("Color"), bOpen ? FLinearColor(0.1f, 1.f, 0.2f) : FLinearColor(1.f, 0.05f, 0.02f));
		if (P->ComponentHasTag(WallTag))
		{
			// closed: standing across the branch and solid; open: sunk out of sight with no collision
			P->SetVisibility(!bOpen);
			P->SetCollisionEnabled(bOpen ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryOnly);
		}
	}
}

void ASkyCourseTrack::ShowPreview(const FSkyPiece* Piece, const FSkyFrame& Start, int32 Lanes, bool bFits)
{
	using namespace SkyTrackImpl;
	if (!Piece)
	{
		if (Preview) Preview->SetVisibility(false);
		return;
	}
	if (!Preview)
	{
		Preview = NewObject<UProceduralMeshComponent>(this, NAME_None, RF_Transient);
		Preview->SetupAttachment(RootComponent);
		Preview->SetUsingAbsoluteLocation(true);
		Preview->SetUsingAbsoluteRotation(true);
		Preview->SetUsingAbsoluteScale(true);
		Preview->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Preview->SetCastShadow(false);
		Preview->RegisterComponent();
		Preview->SetWorldTransform(FTransform::Identity);
	}
	TArray<TArray<FSkyFrame>> Runs;
	FString Err;
	const FSkyFrame* CloseTo = Baked.Segs.Num() && Baked.Segs[0].Frames.Num() ? &Baked.Segs[0].Frames[0] : nullptr;
	SkyGeom::PieceFrames(*Piece, Start, Lanes, CloseTo, Runs, Err);
	FSec Deck;
	for (const TArray<FSkyFrame>& Fr : Runs)
	{
		TArray<FSkyFrame> MF;
		MeshFrames(Fr, MF);
		TArray<FRing> Rs;
		for (const FSkyFrame& F : MF) Rs.Add(ToRing(F, F.S));
		int32 k = 0;
		while (k < Rs.Num())
		{
			if (!Rs[k].bDeck) { ++k; continue; }
			int32 E = k;
			while (E + 1 < Rs.Num() && Rs[E + 1].bDeck) ++E;
			if (E > k)
			{
				Sweep(Deck, Rs, k, E, [](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5; b = 0.06; c = -R.W * 0.5; d = 0.06; }, 0, 1.0, true);
				Sweep(Deck, Rs, k, E, [](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5; b = -0.4; c = -R.W * 0.5; d = -0.4; }, 0, -1.0, true);
				Sweep(Deck, Rs, k, E, [](const FRing& R, double& a, double& b, double& c, double& d) { a = R.W * 0.5; b = 0.06; c = R.W * 0.5; d = -0.4; }, 1, 1.0, false);
				Sweep(Deck, Rs, k, E, [](const FRing& R, double& a, double& b, double& c, double& d) { a = -R.W * 0.5; b = 0.06; c = -R.W * 0.5; d = -0.4; }, 1, -1.0, false);
			}
			k = E + 1;
		}
	}
	Upload(Preview, 0, Deck, false);
	UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(Preview->GetMaterial(0));
	if (!M) { M = Ghost(this, FLinearColor::Green, 0.35f); Preview->SetMaterial(0, M); }
	if (M) M->SetVectorParameterValue(TEXT("Tint"), bFits ? FLinearColor(0.15f, 1.f, 0.3f) : FLinearColor(1.f, 0.12f, 0.08f));
	Preview->SetVisibility(true);
}

void ASkyCourseTrack::Highlight(int32 Seg)
{
	using namespace SkyTrackImpl;
	UMaterialInstanceDynamic* Over = nullptr;
	for (int32 i = 0; i < SegMeshes.Num(); ++i)
	{
		if (!SegMeshes[i]) continue;
		if (i == Seg)
		{
			if (!Over) Over = Ghost(this, FLinearColor(1.f, 0.8f, 0.15f), 0.3f);
			SegMeshes[i]->SetOverlayMaterial(Over);
		}
		else if (SegMeshes[i]->GetOverlayMaterial()) SegMeshes[i]->SetOverlayMaterial(nullptr);
	}
}

void ASkyCourseTrack::UpdateGlow(const TArray<FVector>& Cars, float Dt)
{
	using namespace SkyTrackImpl;
	if (BuiltSkin == ESkySkin::Classic) return;
	const FName Param = BuiltSkin == ESkySkin::Neon ? FName(TEXT("Strength"))
		: (GetWorld() && GetWorld()->GetMapName().Contains(TEXT("Night")) ? FName(TEXT("Strength")) : FName(TEXT("EmissiveStrength")));
	const float Base = BuiltSkin == ESkySkin::Neon ? 9.f : (Param == TEXT("Strength") ? 14.f : 4.f);
	const float K = 1.f - FMath::Exp(-6.f * FMath::Max(Dt, 0.f));
	for (UProceduralMeshComponent* M : SegMeshes)
	{
		if (!M) continue;
		UMaterialInstanceDynamic* Mi = Cast<UMaterialInstanceDynamic>(M->GetMaterial(2));
		if (!Mi) continue;
		const FBox Bx = M->Bounds.GetBox();
		double D2 = 1e18;
		for (const FVector& C : Cars) D2 = FMath::Min(D2, Bx.ComputeSquaredDistanceToPoint(C));
		const float D = (float)(FMath::Sqrt(D2) / 100.0);
		// like the unveil's LED bars: a car close by lights its stretch of trim up to five times as bright
		const float Want = Base * (1.f + 4.f * FMath::Exp(-D / 18.f));
		float Now = Base;
		Mi->GetScalarParameterValue(FHashedMaterialParameterInfo(Param), Now);
		const float Next = Now + (Want - Now) * K;
		if (FMath::Abs(Next - Now) > 0.01f * Base) Mi->SetScalarParameterValue(Param, Next);
	}
}

void ASkyCourseTrack::Clear()
{
	using namespace SkyTrackImpl;
	for (UProceduralMeshComponent* M : SegMeshes) if (M) M->DestroyComponent();
	SegMeshes.Reset();
	SegHashes.Reset();
	for (UPrimitiveComponent* P : Props) if (P) P->DestroyComponent();
	Props.Reset();
	if (UChildActorComponent* CA = FindComponentByClass<UChildActorComponent>()) CA->DestroyChildActor();
	if (Preview) { Preview->DestroyComponent(); Preview = nullptr; }
	Baked = FSkyBaked();
	BuiltSkin = ESkySkin::Count;
}

FString ASkyCourseTrack::TestBuildJson(const FString& Json)
{
	using namespace SkyTrackImpl;
	FSkyCourse Course;
	TArray<FString> Errors;
	TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
	auto Strs = [](const TArray<FString>& A) { TArray<TSharedPtr<FJsonValue>> V; for (const FString& S : A) V.Add(MakeShared<FJsonValueString>(S)); return V; };
	auto Vec = [](const FVector& P) { TArray<TSharedPtr<FJsonValue>> V; V.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(P.X * 100) / 100)); V.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(P.Y * 100) / 100)); V.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(P.Z * 100) / 100)); return V; };
	if (!SkyCourse::Parse(Json, Course, Errors))
	{
		O->SetBoolField(TEXT("valid"), false);
		O->SetBoolField(TEXT("parsed"), false);
		O->SetArrayField(TEXT("errors"), Strs(Errors));
	}
	else
	{
		const double T0 = FPlatformTime::Seconds();
		const int32 Before = SegMeshes.Num();
		TSet<UProceduralMeshComponent*> Had;
		for (UProceduralMeshComponent* M : SegMeshes) Had.Add(M);
		const FSkyBaked& R = Build(Course, FBox(ForceInit));
		const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
		int32 Reused = 0;
		for (UProceduralMeshComponent* M : SegMeshes) if (Had.Contains(M)) ++Reused;
		O->SetBoolField(TEXT("valid"), R.bValid);
		O->SetBoolField(TEXT("parsed"), true);
		O->SetArrayField(TEXT("errors"), Strs(R.Errors));
		O->SetArrayField(TEXT("warnings"), Strs(R.Warnings));
		O->SetNumberField(TEXT("length"), R.Length);
		O->SetNumberField(TEXT("pieces"), R.PieceCount);
		O->SetBoolField(TEXT("lap_course"), R.bLapCourse);
		O->SetNumberField(TEXT("min_z"), R.MinZ);
		O->SetNumberField(TEXT("max_z"), R.MaxZ);
		O->SetArrayField(TEXT("bounds_min"), Vec(R.Bounds.Min));
		O->SetArrayField(TEXT("bounds_max"), Vec(R.Bounds.Max));
		O->SetNumberField(TEXT("build_ms"), Ms);
		O->SetNumberField(TEXT("components_before"), Before);
		O->SetNumberField(TEXT("components"), SegMeshes.Num());
		O->SetNumberField(TEXT("reused"), Reused);
		O->SetNumberField(TEXT("props"), Props.Num());
		{
			double Yaw, Roll;
			SkyGeom::YawRoll(R.End, Yaw, Roll);
			TSharedPtr<FJsonObject> E = MakeShared<FJsonObject>();
			E->SetArrayField(TEXT("p"), Vec(R.End.P));
			E->SetNumberField(TEXT("yaw"), FMath::RadiansToDegrees(Yaw));
			E->SetNumberField(TEXT("roll"), FMath::RadiansToDegrees(Roll));
			O->SetObjectField(TEXT("end"), E);
		}
		TArray<TSharedPtr<FJsonValue>> Segs;
		int32 Tris = 0;
		for (int32 i = 0; i < R.Segs.Num(); ++i)
		{
			const FSkySegment& S = R.Segs[i];
			TSharedPtr<FJsonObject> J = MakeShared<FJsonObject>();
			static const TCHAR* Kinds[] = { TEXT("piece"), TEXT("split_lead"), TEXT("merge_lead"), TEXT("merge_trunk"), TEXT("close_link") };
			J->SetStringField(TEXT("kind"), Kinds[(int32)S.Kind]);
			J->SetStringField(TEXT("type"), SkyCourse::PieceName(S.Type));
			J->SetNumberField(TEXT("seq"), S.Seq);
			J->SetNumberField(TEXT("piece"), S.Piece);
			J->SetNumberField(TEXT("branch"), S.Branch);
			J->SetNumberField(TEXT("lanes"), S.Lanes);
			J->SetNumberField(TEXT("frames"), S.Frames.Num());
			if (S.Frames.Num()) { J->SetNumberField(TEXT("s0"), S.Frames[0].S); J->SetNumberField(TEXT("s1"), S.Frames.Last().S); }
			TArray<TSharedPtr<FJsonValue>> Nx;
			for (const int32 N : S.Next) Nx.Add(MakeShared<FJsonValueNumber>(N));
			J->SetArrayField(TEXT("next"), Nx);
			// the centre line every 2 m: x, y, z, up x, y, z, width, deck
			TArray<TSharedPtr<FJsonValue>> Path;
			for (int32 k = 0; k < S.Frames.Num(); ++k)
			{
				if ((k % 4) && k != S.Frames.Num() - 1) continue;
				const FSkyFrame& F = S.Frames[k];
				TArray<TSharedPtr<FJsonValue>> Pt = Vec(F.P);
				for (const double C : { F.U.X, F.U.Y, F.U.Z }) Pt.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(C * 1000) / 1000));
				Pt.Add(MakeShared<FJsonValueNumber>(F.Width));
				Pt.Add(MakeShared<FJsonValueNumber>(F.bDeck ? 1 : 0));
				Path.Add(MakeShared<FJsonValueArray>(Pt));
			}
			J->SetArrayField(TEXT("path"), Path);
			if (SegMeshes.IsValidIndex(i) && SegMeshes[i])
			{
				int32 N = 0;
				for (int32 sct = 0; sct < SegMeshes[i]->GetNumSections(); ++sct)
					if (const FProcMeshSection* Sec = SegMeshes[i]->GetProcMeshSection(sct)) N += Sec->ProcIndexBuffer.Num() / 3;
				J->SetNumberField(TEXT("tris"), N);
				Tris += N;
			}
			Segs.Add(MakeShared<FJsonValueObject>(J));
		}
		O->SetArrayField(TEXT("segs"), Segs);
		O->SetNumberField(TEXT("tris"), Tris);
		TArray<TSharedPtr<FJsonValue>> Gates;
		for (const FSkyBaked::FGate& G : R.Gates)
		{
			TSharedPtr<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("type"), SkyCourse::PieceName(G.Type));
			J->SetNumberField(TEXT("index"), G.Index);
			J->SetNumberField(TEXT("seg"), G.Seg);
			J->SetNumberField(TEXT("s"), G.At.S);
			J->SetArrayField(TEXT("p"), Vec(G.At.P));
			Gates.Add(MakeShared<FJsonValueObject>(J));
		}
		O->SetArrayField(TEXT("gates"), Gates);
		TArray<TSharedPtr<FJsonValue>> Splits;
		for (const FSkyBaked::FSplitInfo& Sp : R.Splits)
		{
			TSharedPtr<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetNumberField(TEXT("seq"), Sp.Seq);
			J->SetNumberField(TEXT("piece"), Sp.Piece);
			TArray<TSharedPtr<FJsonValue>> Ls, Op;
			for (const int32 L : Sp.LeadSegs) Ls.Add(MakeShared<FJsonValueNumber>(L));
			for (const TArray<int32>& OL : Sp.OpenLaps) { TArray<TSharedPtr<FJsonValue>> A; for (const int32 L : OL) A.Add(MakeShared<FJsonValueNumber>(L)); Op.Add(MakeShared<FJsonValueArray>(A)); }
			J->SetArrayField(TEXT("leads"), Ls);
			J->SetArrayField(TEXT("open_laps"), Op);
			Splits.Add(MakeShared<FJsonValueObject>(J));
		}
		O->SetArrayField(TEXT("splits"), Splits);
		TArray<TSharedPtr<FJsonValue>> Grid;
		for (const FTransform& G : R.Grid)
		{
			TArray<TSharedPtr<FJsonValue>> P = Vec(G.GetLocation());
			P.Add(MakeShared<FJsonValueNumber>(G.Rotator().Yaw));
			Grid.Add(MakeShared<FJsonValueArray>(P));
		}
		O->SetArrayField(TEXT("grid_ue"), Grid);
		TArray<TSharedPtr<FJsonValue>> Routes;
		for (int32 Lap = 1; Lap <= Course.Laps; ++Lap)
		{
			TArray<TSharedPtr<FJsonValue>> A;
			for (const int32 S : SkyCourse::Route(R, Lap)) A.Add(MakeShared<FJsonValueNumber>(S));
			Routes.Add(MakeShared<FJsonValueArray>(A));
		}
		O->SetArrayField(TEXT("routes"), Routes);
	}
	FString Out;
	const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
	FJsonSerializer::Serialize(O.ToSharedRef(), W);
	return Out;
}
