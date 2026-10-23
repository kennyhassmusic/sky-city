// The course file and the bake (see SkyCourse.h and Design/CourseBuilder.md).
//
// The file: format skycity-course v2 (v1 still loads; it has no lane_width, so its lanes are 5.5 m as it was built), read strictly (unknown pieces, unknown settings and anything past the hard limits
// are errors with a JSON path) so an LLM writing courses hears exactly what it got wrong.
//
// The bake: every piece is a shape in its own start frame (x forward, y left, z up), sampled densely, then resampled
// every SampleStep metres of path into frames (P on the deck at the centre, F/L/U right-handed). Each piece starts
// exactly where the last one ended: at every piece boundary the track is level (F horizontal) and the roll is whatever
// the corkscrews left (normally 0), so a boundary is just (position, heading, roll, lanes). Splits fan out into lead-ins,
// run their branches, and come back through generated Hermite connectors into a merge; a close piece is the same kind
// of connector back into the start piece. Then the checks that need the whole course: clearance between parts of the
// track that aren't neighbours (a spatial hash, neighbours by path distance), the build area, lap routing.
#include "SkyCourse.h"
#include "SkyCourseGeom.h"
#include "Engine/World.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

bool SkyCourse::IsBuildMode(const UWorld* World)
{
	if (!World) return false;
	for (const FString& Op : World->URL.Op) if (Op.Equals(TEXT("mode=build"), ESearchCase::IgnoreCase)) return true;
	return false;
}

FString SkyCourse::CoursesDir() { return FPaths::ProjectSavedDir() / TEXT("Courses"); }

FString SkyCourse::SafeName(const FString& Name)
{
	FString Out;
	for (const TCHAR C : Name.TrimStartAndEnd())
	{
		if (FChar::IsAlnum(C) || C == TEXT(' ') || C == TEXT('-') || C == TEXT('_')) Out.AppendChar(C);
		if (Out.Len() >= 48) break;
	}
	return Out.TrimStartAndEnd();
}

static const TCHAR* GSkyCoursePieceNames[] = { TEXT("start"), TEXT("finish"), TEXT("checkpoint"), TEXT("straight"), TEXT("curve"), TEXT("ramp"), TEXT("jump"),
	TEXT("loop"), TEXT("corkscrew"), TEXT("wallride"), TEXT("booster"), TEXT("lanes"), TEXT("split"), TEXT("close") };
static_assert(UE_ARRAY_COUNT(GSkyCoursePieceNames) == (int32)ESkyPiece::Count, "piece names");
const TCHAR* SkyCourse::PieceName(ESkyPiece T) { return (int32)T < (int32)ESkyPiece::Count ? GSkyCoursePieceNames[(int32)T] : TEXT("?"); }
ESkyPiece SkyCourse::PieceFromName(const FString& N)
{
	for (int32 i = 0; i < (int32)ESkyPiece::Count; ++i) if (N.Equals(GSkyCoursePieceNames[i], ESearchCase::IgnoreCase)) return (ESkyPiece)i;
	return ESkyPiece::Count;
}
const TCHAR* SkyCourse::SkinName(ESkySkin S) { return S == ESkySkin::Classic ? TEXT("classic") : S == ESkySkin::Neon ? TEXT("neon") : TEXT("unveil"); }

// --- small helpers ----------------------------------------------------------------------------------------------------

namespace SkyModel
{
	using namespace SkyCourse;
	using namespace SkyGeom;

	/** A number for people: 12, 12.5, 0.25 (not 12.000000). */
	FString Num(double V)
	{
		if (!FMath::IsFinite(V)) return TEXT("NaN");
		const double R = FMath::RoundToDouble(V);
		if (FMath::Abs(V - R) < 1e-6) return FString::Printf(TEXT("%lld"), (long long)R);
		FString S = FString::Printf(TEXT("%.3f"), V);
		while (S.EndsWith(TEXT("0"))) S.LeftChopInline(1);
		if (S.EndsWith(TEXT("."))) S.LeftChopInline(1);
		return S;
	}

	FString Quote(const FString& S)
	{
		FString O = TEXT("\"");
		for (const TCHAR C : S)
		{
			switch (C)
			{
			case TEXT('"'): O += TEXT("\\\""); break;
			case TEXT('\\'): O += TEXT("\\\\"); break;
			case TEXT('\n'): O += TEXT("\\n"); break;
			case TEXT('\r'): O += TEXT("\\r"); break;
			case TEXT('\t'): O += TEXT("\\t"); break;
			default:
				if (C < 0x20) O += FString::Printf(TEXT("\\u%04x"), (int32)C);
				else O.AppendChar(C);
			}
		}
		return O + TEXT("\"");
	}

	FString Label(const FString& Path, ESkyPiece T) { return FString::Printf(TEXT("%s (%s)"), *Path, PieceName(T)); }

	const TCHAR* GateName(ESkyGate G) { return G == ESkyGate::Wall ? TEXT("wall") : G == ESkyGate::None ? TEXT("none") : TEXT("lights"); }
	const TCHAR* AlignName(int32 A) { return A > 0 ? TEXT("right") : A < 0 ? TEXT("left") : TEXT("center"); }

	struct FLim { double Min, Max; };
	// the hard limits (Design/CourseBuilder.md)
	constexpr FLim LimStraight{ 2, 300 }, LimAngle{ -270, 270 }, LimRadius{ 8, 300 }, LimBank{ -45, 45 }, LimRampLen{ 4, 150 },
		LimRise{ -60, 60 }, LimGap{ 4, 80 }, LimDrop{ -30, 30 }, LimLoopR{ 6, 30 }, LimCorkLen{ 20, 260 }, LimTurns{ 0.5, 2 },
		LimWallLen{ 15, 150 }, LimBoost{ 4, 30 }, LimLanesLen{ 10, 80 }, LimSplitLen{ 15, 80 }, LimBranchAngle{ -45, 45 },
		LimMergeLen{ 15, 80 }, LimSkill{ 0.3, 1.2 };

	bool InRange(TArray<FString>& E, const FString& L, const TCHAR* Name, double V, FLim R)
	{
		if (!FMath::IsFinite(V)) { E.Add(FString::Printf(TEXT("%s: %s is not a number"), *L, Name)); return false; }
		if (V < R.Min - 1e-9) { E.Add(FString::Printf(TEXT("%s: %s %s is below the minimum %s"), *L, Name, *Num(V), *Num(R.Min))); return false; }
		if (V > R.Max + 1e-9) { E.Add(FString::Printf(TEXT("%s: %s %s is above the maximum %s"), *L, Name, *Num(V), *Num(R.Max))); return false; }
		return true;
	}
	double Clamp(double V, FLim R) { return FMath::IsFinite(V) ? FMath::Clamp(V, R.Min, R.Max) : R.Min; }

	/** A corkscrew's layout (see PlanCorkscrew below). */
	struct FCorkPlan { double Len = 60, Rh = 0.25, Lift = 0, Rise = 0, Roll = 60; };
	FCorkPlan PlanCorkscrew(double W, double Len, double Turns);

	/** The settings each piece type takes, in the order the file writes them. */
	TArray<const TCHAR*> Settings(ESkyPiece T)
	{
		switch (T)
		{
		case ESkyPiece::Straight: case ESkyPiece::Booster: return { TEXT("length") };
		case ESkyPiece::Curve: return { TEXT("angle"), TEXT("radius"), TEXT("bank") };
		case ESkyPiece::Ramp: return { TEXT("length"), TEXT("rise") };
		case ESkyPiece::Jump: return { TEXT("gap"), TEXT("drop") };
		case ESkyPiece::Loop: return { TEXT("radius"), TEXT("offset") };
		case ESkyPiece::Corkscrew: return { TEXT("length"), TEXT("turns") };
		case ESkyPiece::WallRide: return { TEXT("length"), TEXT("side") };
		case ESkyPiece::Lanes: return { TEXT("lanes"), TEXT("length"), TEXT("align") };
		case ESkyPiece::Split: return { TEXT("length"), TEXT("gate"), TEXT("merge_length"), TEXT("merge_lanes"), TEXT("branches") };
		default: return {};
		}
	}

	FString SettingsList(ESkyPiece T)
	{
		const TArray<const TCHAR*> S = Settings(T);
		if (S.Num() == 0) return TEXT("no settings");
		FString O;
		for (int32 i = 0; i < S.Num(); ++i) O += (i ? TEXT(", ") : TEXT("")) + FString(S[i]);
		return O;
	}
}

// --- defaults ---------------------------------------------------------------------------------------------------------

FSkyPiece SkyCourse::DefaultPiece(ESkyPiece Type, int32 LanesHere)
{
	using namespace SkyModel;
	const int32 Ln = FMath::Clamp(LanesHere, MinLanes, MaxLanes);
	// no course here, so the default lane width; the loop, corkscrew and wallride lengths below are only starting points
	// (the builder and the file reader recompute the "auto" ones against the course's own width)
	FSkyPiece P;
	P.Type = Type;
	switch (Type)
	{
	case ESkyPiece::Straight: P.Length = 30; break;
	case ESkyPiece::Booster: P.Length = 10; break;
	case ESkyPiece::Curve: P.Angle = 90; P.Radius = 40; P.Bank = 0; break;
	case ESkyPiece::Ramp: P.Length = 30; P.Rise = 8; break;
	case ESkyPiece::Jump: P.Gap = 20; P.Drop = 0; break;
	case ESkyPiece::Loop: P.Radius = 12; P.Offset = Ln * DefaultLaneWidth + 1.0; break;
	case ESkyPiece::Corkscrew: P.Turns = 1; P.Length = SkyModel::PlanCorkscrew(Ln * DefaultLaneWidth, -1, 1).Len; break;
	case ESkyPiece::WallRide: P.Length = FMath::Max(40.0, FMath::CeilToDouble((4.0 * Ln * DefaultLaneWidth + 6.0) / 5.0) * 5.0); P.Side = 1; break;
	case ESkyPiece::Lanes: P.Lanes = Ln >= MaxLanes ? Ln - 1 : Ln + 1; P.Length = 25; P.Align = 0; break;
	case ESkyPiece::Split:
	{
		P.Length = 30; P.Gate = ESkyGate::Lights; P.MergeLength = 30; P.MergeLanes = 0;
		FSkyBranch A, B;
		A.Lanes = B.Lanes = Ln;
		A.Angle = 20; B.Angle = -20;
		P.Branches = { A, B };   // Seq = INDEX_NONE: the caller adds the branches' sequences (see ParsePiece)
		break;
	}
	default: break;
	}
	return P;
}

// --- reading ----------------------------------------------------------------------------------------------------------

namespace SkyModel
{
	using namespace SkyCourse;
	using namespace SkyGeom;
	struct FReader
	{
		TArray<FString>& Errors;

		bool Number(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, const FString& Where, double& Out)
		{
			const TSharedPtr<FJsonValue>* V = O->Values.Find(Key);
			if (!V || !V->IsValid() || (*V)->IsNull()) return false;
			if ((*V)->Type != EJson::Number) { Errors.Add(FString::Printf(TEXT("%s: %s must be a number"), *Where, Key)); return false; }
			Out = (*V)->AsNumber();
			return true;
		}
		bool Int(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, const FString& Where, int32& Out)
		{
			double D = 0;
			if (!Number(O, Key, Where, D)) return false;
			if (FMath::Abs(D - FMath::RoundToDouble(D)) > 1e-9 || FMath::Abs(D) > 1e6) { Errors.Add(FString::Printf(TEXT("%s: %s must be a whole number (got %s)"), *Where, Key, *Num(D))); return false; }
			Out = (int32)FMath::RoundToDouble(D);
			return true;
		}
		bool Str(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, const FString& Where, FString& Out)
		{
			const TSharedPtr<FJsonValue>* V = O->Values.Find(Key);
			if (!V || !V->IsValid() || (*V)->IsNull()) return false;
			if ((*V)->Type != EJson::String) { Errors.Add(FString::Printf(TEXT("%s: %s must be a string"), *Where, Key)); return false; }
			Out = (*V)->AsString();
			return true;
		}
		void Unknown(const TSharedPtr<FJsonObject>& O, const TArray<const TCHAR*>& Known, const FString& Where, const FString& Takes)
		{
			for (const auto& KV : O->Values)
			{
				bool bOk = false;
				for (const TCHAR* K : Known) if (KV.Key == K) { bOk = true; break; }
				if (!bOk) Errors.Add(FString::Printf(TEXT("%s: unknown setting \"%s\" (%s)"), *Where, *KV.Key, *Takes));
			}
		}
	};

	bool ParsePieceImpl(FReader& R, const TSharedPtr<FJsonObject>& O, FSkyCourse& Course, FSkyPiece& Out, const FString& Path, int32 Depth);

	bool ParseList(FReader& R, const TSharedPtr<FJsonValue>& V, FSkyCourse& Course, TArray<FSkyPiece>& Out, const FString& Path, int32 Depth)
	{
		if (!V.IsValid() || V->Type != EJson::Array) { R.Errors.Add(FString::Printf(TEXT("%s must be a list of pieces"), *Path)); return false; }
		bool bOk = true;
		const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
		for (int32 i = 0; i < A.Num(); ++i)
		{
			const FString P = FString::Printf(TEXT("%s[%d]"), *Path, i);
			if (!A[i].IsValid() || A[i]->Type != EJson::Object) { R.Errors.Add(P + TEXT(" must be an object like { \"type\": \"straight\", \"length\": 30 }")); bOk = false; continue; }
			FSkyPiece Piece;
			if (ParsePieceImpl(R, A[i]->AsObject(), Course, Piece, P, Depth)) Out.Add(MoveTemp(Piece));
			else bOk = false;
		}
		return bOk;
	}

	bool ParsePieceImpl(FReader& R, const TSharedPtr<FJsonObject>& O, FSkyCourse& Course, FSkyPiece& Out, const FString& Path, int32 Depth)
	{
		const int32 E0 = R.Errors.Num();
		if (!O.IsValid()) { R.Errors.Add(Path + TEXT(" must be an object")); return false; }
		FString TypeName;
		if (!R.Str(O, TEXT("type"), Path, TypeName)) { if (R.Errors.Num() == E0) R.Errors.Add(Path + TEXT(": type is missing (start, finish, checkpoint, straight, curve, ramp, jump, loop, corkscrew, wallride, booster, lanes, split or close)")); return false; }
		const ESkyPiece T = PieceFromName(TypeName);
		if (T == ESkyPiece::Count)
		{
			R.Errors.Add(FString::Printf(TEXT("%s: unknown piece type \"%s\" (use start, finish, checkpoint, straight, curve, ramp, jump, loop, corkscrew, wallride, booster, lanes, split or close)"), *Path, *TypeName));
			return false;
		}
		const FString L = Label(Path, T);
		Out = DefaultPiece(T, DefaultLanes);
		if (T == ESkyPiece::Loop) Out.Offset = -1;     // auto: the track width + 1 m where the loop is
		if (T == ESkyPiece::WallRide) Out.Length = -1; // auto: as long as the lanes there need
		if (T == ESkyPiece::Corkscrew) Out.Length = -1; // auto: the shortest that works for the lanes and turns
		if (T == ESkyPiece::Split) Out.Branches.Reset();
		TArray<const TCHAR*> Known = Settings(T);
		Known.Insert(TEXT("type"), 0);
		R.Unknown(O, Known, L, FString::Printf(TEXT("%s takes %s"), PieceName(T), *SettingsList(T)));

		double D = 0;
		int32 I = 0;
		FString S;
		switch (T)
		{
		case ESkyPiece::Straight: if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimStraight); Out.Length = D; } break;
		case ESkyPiece::Booster: if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimBoost); Out.Length = D; } break;
		case ESkyPiece::Curve:
			if (R.Number(O, TEXT("angle"), L, D)) { InRange(R.Errors, L, TEXT("angle"), D, LimAngle); Out.Angle = D; if (FMath::Abs(D) < 1) R.Errors.Add(L + TEXT(": angle must be at least 1 degree either way (+ turns left, - right)")); }
			if (R.Number(O, TEXT("radius"), L, D)) { InRange(R.Errors, L, TEXT("radius"), D, LimRadius); Out.Radius = D; }
			if (R.Number(O, TEXT("bank"), L, D)) { InRange(R.Errors, L, TEXT("bank"), D, LimBank); Out.Bank = D; }
			break;
		case ESkyPiece::Ramp:
			if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimRampLen); Out.Length = D; }
			if (R.Number(O, TEXT("rise"), L, D)) { InRange(R.Errors, L, TEXT("rise"), D, LimRise); Out.Rise = D; }
			break;
		case ESkyPiece::Jump:
			if (R.Number(O, TEXT("gap"), L, D)) { InRange(R.Errors, L, TEXT("gap"), D, LimGap); Out.Gap = D; }
			if (R.Number(O, TEXT("drop"), L, D)) { InRange(R.Errors, L, TEXT("drop"), D, LimDrop); Out.Drop = D; }
			break;
		case ESkyPiece::Loop:
			if (R.Number(O, TEXT("radius"), L, D)) { InRange(R.Errors, L, TEXT("radius"), D, LimLoopR); Out.Radius = D; }
			if (R.Number(O, TEXT("offset"), L, D)) { InRange(R.Errors, L, TEXT("offset"), D, FLim{ 0, MaxLanes * Course.LaneWidth + 1.0 }); Out.Offset = D; }
			break;
		case ESkyPiece::Corkscrew:
			if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimCorkLen); Out.Length = D; }
			if (R.Number(O, TEXT("turns"), L, D)) { InRange(R.Errors, L, TEXT("turns"), D, LimTurns); Out.Turns = D; }
			break;
		case ESkyPiece::WallRide:
			if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimWallLen); Out.Length = D; }
			if (R.Str(O, TEXT("side"), L, S))
			{
				if (S.Equals(TEXT("left"), ESearchCase::IgnoreCase)) Out.Side = 1;
				else if (S.Equals(TEXT("right"), ESearchCase::IgnoreCase)) Out.Side = -1;
				else R.Errors.Add(FString::Printf(TEXT("%s: side \"%s\" must be \"left\" or \"right\""), *L, *S));
			}
			break;
		case ESkyPiece::Lanes:
			if (R.Int(O, TEXT("lanes"), L, I)) { InRange(R.Errors, L, TEXT("lanes"), I, FLim{ (double)MinLanes, (double)MaxLanes }); Out.Lanes = I; }
			else if (!O->Values.Contains(TEXT("lanes"))) R.Errors.Add(L + TEXT(": lanes is missing (the new lane count, 1 to 4)"));
			if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimLanesLen); Out.Length = D; }
			if (R.Str(O, TEXT("align"), L, S))
			{
				if (S.Equals(TEXT("center"), ESearchCase::IgnoreCase) || S.Equals(TEXT("centre"), ESearchCase::IgnoreCase)) Out.Align = 0;
				else if (S.Equals(TEXT("left"), ESearchCase::IgnoreCase)) Out.Align = -1;
				else if (S.Equals(TEXT("right"), ESearchCase::IgnoreCase)) Out.Align = 1;
				else R.Errors.Add(FString::Printf(TEXT("%s: align \"%s\" must be \"center\", \"left\" or \"right\""), *L, *S));
			}
			break;
		case ESkyPiece::Split:
		{
			if (R.Number(O, TEXT("length"), L, D)) { InRange(R.Errors, L, TEXT("length"), D, LimSplitLen); Out.Length = D; }
			if (R.Number(O, TEXT("merge_length"), L, D)) { InRange(R.Errors, L, TEXT("merge_length"), D, LimMergeLen); Out.MergeLength = D; }
			if (R.Int(O, TEXT("merge_lanes"), L, I)) { InRange(R.Errors, L, TEXT("merge_lanes"), I, FLim{ 0, (double)MaxLanes }); Out.MergeLanes = I; }
			if (R.Str(O, TEXT("gate"), L, S))
			{
				if (S.Equals(TEXT("lights"), ESearchCase::IgnoreCase)) Out.Gate = ESkyGate::Lights;
				else if (S.Equals(TEXT("wall"), ESearchCase::IgnoreCase)) Out.Gate = ESkyGate::Wall;
				else if (S.Equals(TEXT("none"), ESearchCase::IgnoreCase)) Out.Gate = ESkyGate::None;
				else R.Errors.Add(FString::Printf(TEXT("%s: gate \"%s\" must be \"lights\", \"wall\" or \"none\""), *L, *S));
			}
			const TSharedPtr<FJsonValue>* BV = O->Values.Find(TEXT("branches"));
			if (!BV || !BV->IsValid() || (*BV)->Type != EJson::Array)
			{
				R.Errors.Add(L + TEXT(": branches is missing (a list of 2 to 4 objects like { \"lanes\": 2, \"angle\": 15, \"laps\": [1, 3], \"pieces\": [...] })"));
				break;
			}
			const TArray<TSharedPtr<FJsonValue>>& BA = (*BV)->AsArray();
			if (BA.Num() < 2 || BA.Num() > MaxBranches) R.Errors.Add(FString::Printf(TEXT("%s: %d branches (a split has 2 to %d)"), *L, BA.Num(), MaxBranches));
			for (int32 b = 0; b < BA.Num() && b < MaxBranches; ++b)
			{
				const FString BP = FString::Printf(TEXT("%s.branches[%d]"), *Path, b);
				if (!BA[b].IsValid() || BA[b]->Type != EJson::Object) { R.Errors.Add(BP + TEXT(" must be an object like { \"lanes\": 2, \"angle\": 15, \"pieces\": [...] }")); continue; }
				const TSharedPtr<FJsonObject> BO = BA[b]->AsObject();
				R.Unknown(BO, { TEXT("lanes"), TEXT("angle"), TEXT("laps"), TEXT("pieces") }, BP, TEXT("a branch takes lanes, angle, laps and pieces"));
				FSkyBranch Br;
				Br.Lanes = 0;   // 0 = the lanes the track has at the split
				if (R.Int(BO, TEXT("lanes"), BP, I)) { InRange(R.Errors, BP, TEXT("lanes"), I, FLim{ (double)MinLanes, (double)MaxLanes }); Br.Lanes = I; }
				if (R.Number(BO, TEXT("angle"), BP, D)) { InRange(R.Errors, BP, TEXT("angle"), D, LimBranchAngle); Br.Angle = D; }
				else Br.Angle = BA.Num() > 1 ? 20.0 - 40.0 * b / (BA.Num() - 1) : 0.0;
				if (const TSharedPtr<FJsonValue>* LV = BO->Values.Find(TEXT("laps")))
				{
					if (LV->IsValid() && (*LV)->Type == EJson::Array)
					{
						for (const TSharedPtr<FJsonValue>& X : (*LV)->AsArray())
						{
							const double N = X.IsValid() && X->Type == EJson::Number ? X->AsNumber() : -1;
							if (N < 1 || N > MaxLaps || FMath::Abs(N - FMath::RoundToDouble(N)) > 1e-9) { R.Errors.Add(FString::Printf(TEXT("%s: laps must be lap numbers 1 to %d, like [1, 3]"), *BP, MaxLaps)); break; }
							Br.Laps.AddUnique((int32)N);
						}
						Br.Laps.Sort();
					}
					else if (LV->IsValid() && !(*LV)->IsNull()) R.Errors.Add(BP + TEXT(": laps must be a list of lap numbers, like [1, 3]"));
				}
				const int32 SeqIndex = Course.Seqs.AddDefaulted();
				Br.Seq = SeqIndex;
				TArray<FSkyPiece> Pieces;
				if (const TSharedPtr<FJsonValue>* PV = BO->Values.Find(TEXT("pieces")))
					ParseList(R, *PV, Course, Pieces, BP + TEXT(".pieces"), Depth + 1);
				Course.Seqs[SeqIndex].Pieces = MoveTemp(Pieces);
				Out.Branches.Add(MoveTemp(Br));
			}
			break;
		}
		default: break;
		}
		return R.Errors.Num() == E0;
	}
}

bool SkyCourse::ParsePiece(const TSharedPtr<FJsonObject>& Obj, FSkyCourse& Course, FSkyPiece& Out, const FString& Path, TArray<FString>& Errors)
{
	using namespace SkyModel;
	FReader R{ Errors };
	return ParsePieceImpl(R, Obj, Course, Out, Path, 0);
}

bool SkyCourse::Parse(const FString& Json, FSkyCourse& Out, TArray<FString>& Errors)
{
	using namespace SkyModel;
	const int32 E0 = Errors.Num();
	Out = FSkyCourse();
	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		Errors.Add(FString::Printf(TEXT("not valid JSON: %s"), *Reader->GetErrorMessage()));
		return false;
	}
	FReader R{ Errors };
	R.Unknown(Root, { TEXT("format"), TEXT("version"), TEXT("name"), TEXT("author"), TEXT("start"), TEXT("lanes"), TEXT("skin"), TEXT("laps"),
		TEXT("opponents"), TEXT("skill"), TEXT("lane_width"), TEXT("catch_up"), TEXT("pieces") }, TEXT("course"),
		TEXT("a course has format, version, name, author, start, lanes, lane_width, skin, laps, opponents, skill, catch_up and pieces"));
	FString S;
	if (R.Str(Root, TEXT("format"), TEXT("course"), S) && S != TEXT("skycity-course"))
		Errors.Add(FString::Printf(TEXT("course: format \"%s\" is not \"skycity-course\""), *S));
	int32 I = 0;
	double D = 0;
	int32 Version = FormatVersion;
	if (R.Int(Root, TEXT("version"), TEXT("course"), I))
	{
		if (I < 1 || I > FormatVersion) Errors.Add(FString::Printf(TEXT("course: version %d is not one this game reads (1 or %d)"), I, FormatVersion));
		else Version = I;
	}
	// a version 1 file was built on 5.5 m lanes: without lane_width it loads exactly as it was, so it still fits
	Out.LaneWidth = Version < 2 ? StandardLaneWidth : DefaultLaneWidth;
	if (R.Number(Root, TEXT("lane_width"), TEXT("course"), D)) { InRange(Errors, TEXT("course"), TEXT("lane_width"), D, FLim{ MinLaneWidth, MaxLaneWidth }); Out.LaneWidth = Clamp(D, FLim{ MinLaneWidth, MaxLaneWidth }); }
	{
		const TSharedPtr<FJsonValue>* CV = Root->Values.Find(TEXT("catch_up"));
		if (CV && CV->IsValid() && !(*CV)->IsNull())
		{
			if ((*CV)->Type == EJson::Boolean) Out.bCatchUp = (*CV)->AsBool();
			else Errors.Add(TEXT("course: catch_up must be true or false"));
		}
	}
	if (R.Str(Root, TEXT("name"), TEXT("course"), S)) { S.TrimStartAndEndInline(); if (!S.IsEmpty()) Out.Name = S.Left(64); }
	if (R.Str(Root, TEXT("author"), TEXT("course"), S)) Out.Author = S.TrimStartAndEnd().Left(64);
	const TSharedPtr<FJsonValue>* SV = Root->Values.Find(TEXT("start"));
	if (!SV || !SV->IsValid() || (*SV)->Type != EJson::Object)
		Errors.Add(TEXT("start: missing (where the start piece begins: { \"x\": 0, \"y\": 0, \"z\": 0.3, \"yaw\": 0 }, metres and degrees)"));
	else
	{
		const TSharedPtr<FJsonObject> SO = (*SV)->AsObject();
		R.Unknown(SO, { TEXT("x"), TEXT("y"), TEXT("z"), TEXT("yaw") }, TEXT("start"), TEXT("start takes x, y, z and yaw"));
		for (const TCHAR* K : { TEXT("x"), TEXT("y"), TEXT("z") })
		{
			if (!R.Number(SO, K, TEXT("start"), D)) { if (!SO->Values.Contains(K)) Errors.Add(FString::Printf(TEXT("start: %s is missing"), K)); continue; }
			if (!FMath::IsFinite(D) || FMath::Abs(D) > 1e6) { Errors.Add(FString::Printf(TEXT("start: %s is out of range"), K)); continue; }
			(K[0] == TEXT('x') ? Out.Start.X : K[0] == TEXT('y') ? Out.Start.Y : Out.Start.Z) = D;
		}
		if (R.Number(SO, TEXT("yaw"), TEXT("start"), D)) Out.Yaw = FMath::IsFinite(D) ? FMath::Fmod(D, 360.0) : 0.0;
	}
	if (R.Int(Root, TEXT("lanes"), TEXT("course"), I)) { InRange(Errors, TEXT("course"), TEXT("lanes"), I, FLim{ (double)MinLanes, (double)MaxLanes }); Out.Lanes = FMath::Clamp(I, MinLanes, MaxLanes); }
	if (R.Str(Root, TEXT("skin"), TEXT("course"), S))
	{
		if (S.Equals(TEXT("unveil"), ESearchCase::IgnoreCase)) Out.Skin = ESkySkin::Unveil;
		else if (S.Equals(TEXT("classic"), ESearchCase::IgnoreCase)) Out.Skin = ESkySkin::Classic;
		else if (S.Equals(TEXT("neon"), ESearchCase::IgnoreCase)) Out.Skin = ESkySkin::Neon;
		else Errors.Add(FString::Printf(TEXT("course: skin \"%s\" must be \"unveil\", \"classic\" or \"neon\""), *S));
	}
	if (R.Int(Root, TEXT("laps"), TEXT("course"), I)) { InRange(Errors, TEXT("course"), TEXT("laps"), I, FLim{ 1, (double)MaxLaps }); Out.Laps = FMath::Clamp(I, 1, MaxLaps); }
	if (R.Int(Root, TEXT("opponents"), TEXT("course"), I)) { InRange(Errors, TEXT("course"), TEXT("opponents"), I, FLim{ 0, (double)MaxOpponents }); Out.Opponents = FMath::Clamp(I, 0, MaxOpponents); }
	if (R.Number(Root, TEXT("skill"), TEXT("course"), D)) { InRange(Errors, TEXT("course"), TEXT("skill"), D, LimSkill); Out.Skill = Clamp(D, LimSkill); }
	const TSharedPtr<FJsonValue>* PV = Root->Values.Find(TEXT("pieces"));
	if (!PV) Errors.Add(TEXT("pieces: missing (the list of pieces, starting with { \"type\": \"start\" })"));
	else
	{
		TArray<FSkyPiece> Main;
		ParseList(R, *PV, Out, Main, TEXT("pieces"), 0);
		Out.Seqs[0].Pieces = MoveTemp(Main);
	}
	return Errors.Num() == E0;
}

// --- writing ----------------------------------------------------------------------------------------------------------

TSharedPtr<FJsonObject> SkyCourse::PieceToJson(const FSkyCourse& Course, const FSkyPiece& P)
{
	using namespace SkyModel;
	TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
	O->SetStringField(TEXT("type"), PieceName(P.Type));
	switch (P.Type)
	{
	case ESkyPiece::Straight: case ESkyPiece::Booster: O->SetNumberField(TEXT("length"), P.Length); break;
	case ESkyPiece::Curve: O->SetNumberField(TEXT("angle"), P.Angle); O->SetNumberField(TEXT("radius"), P.Radius); O->SetNumberField(TEXT("bank"), P.Bank); break;
	case ESkyPiece::Ramp: O->SetNumberField(TEXT("length"), P.Length); O->SetNumberField(TEXT("rise"), P.Rise); break;
	case ESkyPiece::Jump: O->SetNumberField(TEXT("gap"), P.Gap); O->SetNumberField(TEXT("drop"), P.Drop); break;
	case ESkyPiece::Loop: O->SetNumberField(TEXT("radius"), P.Radius); if (P.Offset >= 0) O->SetNumberField(TEXT("offset"), P.Offset); break;
	case ESkyPiece::Corkscrew: if (P.Length > 0) O->SetNumberField(TEXT("length"), P.Length); O->SetNumberField(TEXT("turns"), P.Turns); break;
	case ESkyPiece::WallRide: if (P.Length > 0) O->SetNumberField(TEXT("length"), P.Length); O->SetStringField(TEXT("side"), P.Side < 0 ? TEXT("right") : TEXT("left")); break;
	case ESkyPiece::Lanes: O->SetNumberField(TEXT("lanes"), P.Lanes); O->SetNumberField(TEXT("length"), P.Length); O->SetStringField(TEXT("align"), AlignName(P.Align)); break;
	case ESkyPiece::Split:
	{
		O->SetNumberField(TEXT("length"), P.Length);
		O->SetStringField(TEXT("gate"), GateName(P.Gate));
		O->SetNumberField(TEXT("merge_length"), P.MergeLength);
		if (P.MergeLanes > 0) O->SetNumberField(TEXT("merge_lanes"), P.MergeLanes);
		TArray<TSharedPtr<FJsonValue>> Bs;
		for (const FSkyBranch& B : P.Branches)
		{
			TSharedPtr<FJsonObject> BO = MakeShared<FJsonObject>();
			if (B.Lanes > 0) BO->SetNumberField(TEXT("lanes"), B.Lanes);
			BO->SetNumberField(TEXT("angle"), B.Angle);
			if (B.Laps.Num() > 0)
			{
				TArray<TSharedPtr<FJsonValue>> Laps;
				for (const int32 L : B.Laps) Laps.Add(MakeShared<FJsonValueNumber>(L));
				BO->SetArrayField(TEXT("laps"), Laps);
			}
			TArray<TSharedPtr<FJsonValue>> Ps;
			if (Course.Seqs.IsValidIndex(B.Seq))
				for (const FSkyPiece& C : Course.Seqs[B.Seq].Pieces) Ps.Add(MakeShared<FJsonValueObject>(PieceToJson(Course, C)));
			BO->SetArrayField(TEXT("pieces"), Ps);
			Bs.Add(MakeShared<FJsonValueObject>(BO));
		}
		O->SetArrayField(TEXT("branches"), Bs);
		break;
	}
	default: break;
	}
	return O;
}

namespace SkyModel
{
	using namespace SkyCourse;
	using namespace SkyGeom;
	/** JSON text with one piece per line (splits and branches spread over lines), numbers without float noise. */
	FString JsonText(const TSharedPtr<FJsonValue>& V, const FString& Indent, bool bInline);

	FString ObjText(const TSharedPtr<FJsonObject>& O, const FString& Indent, bool bInline)
	{
		if (!O.IsValid() || O->Values.Num() == 0) return TEXT("{}");
		const bool bSpread = !bInline && O->Values.Contains(TEXT("branches"));   // splits and branches spread out
		FString S = TEXT("{");
		int32 i = 0;
		for (const auto& KV : O->Values)
		{
			const bool bList = KV.Value.IsValid() && KV.Value->Type == EJson::Array && (KV.Key == TEXT("pieces") || KV.Key == TEXT("branches"));
			S += i++ ? TEXT(",") : TEXT("");
			S += bSpread ? TEXT("\n") + Indent + TEXT("  ") : TEXT(" ");
			S += Quote(FString(*KV.Key)) + TEXT(": ") + JsonText(KV.Value, Indent + TEXT("  "), bInline || !bList);
		}
		S += bSpread ? TEXT("\n") + Indent + TEXT("}") : TEXT(" }");
		return S;
	}

	FString JsonText(const TSharedPtr<FJsonValue>& V, const FString& Indent, bool bInline)
	{
		if (!V.IsValid() || V->IsNull()) return TEXT("null");
		switch (V->Type)
		{
		case EJson::Number: return Num(V->AsNumber());
		case EJson::String: return Quote(V->AsString());
		case EJson::Boolean: return V->AsBool() ? TEXT("true") : TEXT("false");
		case EJson::Object:
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			// a piece or branch that holds pieces spreads out; anything else stays on one line
			const bool bHolds = O.IsValid() && (O->Values.Contains(TEXT("branches")) || O->Values.Contains(TEXT("pieces")));
			if (!bHolds || bInline) return ObjText(O, Indent, true);
			FString S = TEXT("{");
			int32 i = 0;
			for (const auto& KV : O->Values)
			{
				const bool bList = KV.Value.IsValid() && KV.Value->Type == EJson::Array && (KV.Key == TEXT("pieces") || KV.Key == TEXT("branches"));
				S += i++ ? TEXT(",") : TEXT("");
				S += TEXT("\n") + Indent + TEXT("  ") + Quote(FString(*KV.Key)) + TEXT(": ") + JsonText(KV.Value, Indent + TEXT("  "), !bList);
			}
			return S + TEXT("\n") + Indent + TEXT("}");
		}
		case EJson::Array:
		{
			const TArray<TSharedPtr<FJsonValue>>& A = V->AsArray();
			if (A.Num() == 0) return TEXT("[]");
			if (bInline)
			{
				FString S = TEXT("[");
				for (int32 i = 0; i < A.Num(); ++i) S += (i ? TEXT(", ") : TEXT("")) + JsonText(A[i], Indent, true);
				return S + TEXT("]");
			}
			FString S = TEXT("[");
			for (int32 i = 0; i < A.Num(); ++i) S += (i ? TEXT(",\n") : TEXT("\n")) + Indent + TEXT("  ") + JsonText(A[i], Indent + TEXT("  "), false);
			return S + TEXT("\n") + Indent + TEXT("]");
		}
		default: return TEXT("null");
		}
	}
}

FString SkyCourse::Write(const FSkyCourse& C)
{
	using namespace SkyModel;
	FString S = TEXT("{\n");
	S += TEXT("  \"format\": \"skycity-course\", \"version\": ") + Num(FormatVersion) + TEXT(",\n");
	S += TEXT("  \"name\": ") + Quote(C.Name) + TEXT(", \"author\": ") + Quote(C.Author) + TEXT(",\n");
	S += FString::Printf(TEXT("  \"start\": { \"x\": %s, \"y\": %s, \"z\": %s, \"yaw\": %s },\n"), *Num(C.Start.X), *Num(C.Start.Y), *Num(C.Start.Z), *Num(C.Yaw));
	S += FString::Printf(TEXT("  \"lanes\": %d, \"lane_width\": %s, \"skin\": \"%s\", \"laps\": %d, \"opponents\": %d, \"skill\": %s, \"catch_up\": %s,\n"), C.Lanes, *Num(C.LaneWidth), SkinName(C.Skin), C.Laps, C.Opponents, *Num(C.Skill), C.bCatchUp ? TEXT("true") : TEXT("false"));
	S += TEXT("  \"pieces\": [");
	const TArray<FSkyPiece>& Main = C.Seqs.Num() > 0 ? C.Seqs[0].Pieces : TArray<FSkyPiece>();
	for (int32 i = 0; i < Main.Num(); ++i)
		S += (i ? TEXT(",\n    ") : TEXT("\n    ")) + JsonText(MakeShared<FJsonValueObject>(PieceToJson(C, Main[i])), TEXT("    "), false);
	S += Main.Num() ? TEXT("\n  ]\n}\n") : TEXT("]\n}\n");
	return S;
}

// --- frames -----------------------------------------------------------------------------------------------------------

FSkyFrame SkyGeom::MakeFrame(const FVector& P, double Yaw, double Roll, double Width)
{
	FSkyFrame Fr;
	Fr.P = P;
	Fr.F = FVector(FMath::Cos(Yaw), FMath::Sin(Yaw), 0);
	const FVector L0(-FMath::Sin(Yaw), FMath::Cos(Yaw), 0), U0(0, 0, 1);
	const double C = FMath::Cos(Roll), S = FMath::Sin(Roll);
	Fr.L = L0 * C + U0 * S;
	Fr.U = U0 * C - L0 * S;
	Fr.Width = Width;
	return Fr;
}

void SkyGeom::YawRoll(const FSkyFrame& F, double& Yaw, double& Roll)
{
	Yaw = FMath::Atan2(F.F.Y, F.F.X);
	const FVector L0(-FMath::Sin(Yaw), FMath::Cos(Yaw), 0);
	Roll = FMath::Atan2(-FVector::DotProduct(F.U, L0), F.U.Z);
}

namespace SkyModel
{
	using namespace SkyCourse;
	using namespace SkyGeom;

	/** Where a piece boundary is: the track there is level (F horizontal), so position, heading, roll and lanes say it all. */
	struct FState
	{
		FVector P = FVector::ZeroVector;
		double Yaw = 0, Roll = 0;   // rad
		double W = DefaultLaneWidth * DefaultLanes, S = 0;
		double LaneW = DefaultLaneWidth;   // m per lane: the course's, carried through every state so no helper needs the course
		int32 Lanes = DefaultLanes;
		FSkyFrame Frame() const { FSkyFrame F = MakeFrame(P, Yaw, Roll, W); F.S = S; return F; }
	};

	struct FSample
	{
		FVector P = FVector::ZeroVector;   // in the piece's start frame: x forward, y left, z up
		FVector Up = FVector(0, 0, 1);     // which way the deck faces (before Roll)
		double Roll = 0;                   // extra roll about the path (rad, + raises the left side)
		double W = 11;
		bool bDeck = true;
	};

	/** A piece's shape: Fn(u) for u in [0, 1] (and a little past, for tangents), the u values where frames must land. */
	struct FShape
	{
		TFunction<FSample(double)> Fn;
		TArray<double> Breaks;
		double EstLen = 10;
		bool bTwist = false;      // a corkscrew or wallride: the roll the track already has turns the whole shape
		bool bWorld = false;      // Fn gives world positions (the generated connectors)
	};

	FVector RotX(const FVector& V, double A)
	{
		const double C = FMath::Cos(A), S = FMath::Sin(A);
		return FVector(V.X, V.Y * C - V.Z * S, V.Y * S + V.Z * C);
	}

	/** Sample a shape laid from (P0, Yaw0, Roll0) into frames every <= SampleStep m of path; S counts on from S0.
	 *  The first and last frames are then set exactly to SnapStart / SnapEnd (when given) so joins match bit for bit.
	 *  Returns the path length. */
	double SampleShape(const FShape& Sh, const FVector& P0, double Yaw0, double Roll0, double S0,
		const FSkyFrame* SnapStart, const FSkyFrame* SnapEnd, TArray<FSkyFrame>& Out)
	{
		Out.Reset();
		const FVector Fb = Sh.bWorld ? FVector(1, 0, 0) : FVector(FMath::Cos(Yaw0), FMath::Sin(Yaw0), 0);
		const FVector Lb = Sh.bWorld ? FVector(0, 1, 0) : FVector(-FMath::Sin(Yaw0), FMath::Cos(Yaw0), 0);
		const FVector Ub(0, 0, 1);
		const FVector Org = Sh.bWorld ? FVector::ZeroVector : P0;
		auto ToWorld = [&](FVector V) { if (Sh.bTwist && Roll0 != 0) V = RotX(V, Roll0); return Fb * V.X + Lb * V.Y + Ub * V.Z; };
		const double H = FMath::Clamp(0.004 / FMath::Max(Sh.EstLen, 1.0), 1e-7, 1e-3);
		FVector LastL = ToWorld(FVector(0, 1, 0));
		auto Eval = [&](double U) -> FSkyFrame
		{
			const FSample Sm = Sh.Fn(U);
			FSkyFrame Fr;
			Fr.P = Org + ToWorld(Sm.P);
			FVector F = ToWorld(Sh.Fn(U + H).P - Sh.Fn(U - H).P).GetSafeNormal();
			if (F.IsNearlyZero()) F = Out.Num() ? Out.Last().F : Fb;
			const FVector Up = ToWorld(Sm.Up);
			FVector L = FVector::CrossProduct(Up, F);
			L = L.SizeSquared() > 1e-10 ? L.GetSafeNormal() : LastL;
			LastL = L;
			FVector Uu = FVector::CrossProduct(F, L);
			const double R = (Sh.bTwist ? 0.0 : Roll0) + Sm.Roll;
			if (R != 0)
			{
				const double C = FMath::Cos(R), S = FMath::Sin(R);
				const FVector L2 = L * C + Uu * S;
				Uu = Uu * C - L * S;
				L = L2;
			}
			Fr.F = F; Fr.L = L; Fr.U = Uu;
			Fr.Width = Sm.W;
			Fr.bDeck = Sm.bDeck;
			return Fr;
		};
		TArray<double> Cuts = { 0.0 };
		for (const double B : Sh.Breaks) if (B > Cuts.Last() + 1e-6 && B < 1.0 - 1e-6) Cuts.Add(B);
		Cuts.Add(1.0);
		double Done = 0;
		TArray<double> Cum;
		TArray<FVector> Pts;
		for (int32 c = 0; c + 1 < Cuts.Num(); ++c)
		{
			const double Ua = Cuts[c], Ub2 = Cuts[c + 1];
			const int32 N = FMath::Clamp(FMath::CeilToInt(Sh.EstLen * (Ub2 - Ua) / 0.1), 8, 30000);
			Cum.SetNumUninitialized(N + 1);
			Pts.SetNumUninitialized(N + 1);
			for (int32 k = 0; k <= N; ++k) Pts[k] = ToWorld(Sh.Fn(Ua + (Ub2 - Ua) * k / N).P);
			Cum[0] = 0;
			for (int32 k = 1; k <= N; ++k) Cum[k] = Cum[k - 1] + FVector::Dist(Pts[k], Pts[k - 1]);
			const double Len = Cum[N];
			const int32 Steps = FMath::Max(1, FMath::CeilToInt(Len / SampleStep - 1e-6));
			int32 k = 0;
			for (int32 j = (c == 0 ? 0 : 1); j <= Steps; ++j)
			{
				const double T = Len * j / Steps;
				while (k < N - 1 && Cum[k + 1] < T) ++k;
				const double Seg = Cum[k + 1] - Cum[k];
				const double A = Seg > 1e-12 ? FMath::Clamp((T - Cum[k]) / Seg, 0.0, 1.0) : 0.0;
				const double U = j == Steps ? Ub2 : Ua + (Ub2 - Ua) * (k + A) / N;
				FSkyFrame Fr = Eval(U);
				Fr.S = S0 + Done + T;
				Out.Add(Fr);
			}
			Done += Len;
		}
		auto Snap = [](FSkyFrame& To, const FSkyFrame& From) { To.P = From.P; To.F = From.F; To.L = From.L; To.U = From.U; };
		if (SnapStart && Out.Num()) Snap(Out[0], *SnapStart);
		if (SnapEnd && Out.Num()) Snap(Out.Last(), *SnapEnd);
		return Done;
	}

	/** A cubic Hermite from A to B (both frames level, F horizontal), tangent lengths K * chord. */
	struct FHermite
	{
		FVector A, B, TA, TB;
		FVector P(double T) const
		{
			const double T2 = T * T, T3 = T2 * T;
			return A * (2 * T3 - 3 * T2 + 1) + TA * (T3 - 2 * T2 + T) + B * (-2 * T3 + 3 * T2) + TB * (T3 - T2);
		}
		FVector D1(double T) const
		{
			const double T2 = T * T;
			return A * (6 * T2 - 6 * T) + TA * (3 * T2 - 4 * T + 1) + B * (-6 * T2 + 6 * T) + TB * (3 * T2 - 2 * T);
		}
		FVector D2(double T) const { return A * (12 * T - 6) + TA * (6 * T - 4) + B * (-12 * T + 6) + TB * (6 * T - 2); }
		/** Tightest radius (3D) and steepest slope (deg) along it. */
		void Measure(double& MinR, double& MaxSlope) const
		{
			MinR = 1e9; MaxSlope = 0;
			FVector Prev = FVector::ZeroVector;
			for (int32 i = 0; i <= 64; ++i)
			{
				const double T = i / 64.0;
				const FVector V = D1(T), Acc = D2(T);
				const double Sp = V.Size();
				if (Sp < 1e-6) { MinR = 0; continue; }
				// a cusp (the curve doubling back on itself, e.g. to a point behind it on the same line) has no
				// curvature on the line itself, so catch it by the direction flipping between samples
				if (!Prev.IsZero() && FVector::DotProduct(Prev, V / Sp) < 0.8) MinR = 0;
				Prev = V / Sp;
				const double K = FVector::CrossProduct(V, Acc).Size() / (Sp * Sp * Sp);
				if (K > 1e-9) MinR = FMath::Min(MinR, 1.0 / K);
				MaxSlope = FMath::Max(MaxSlope, FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(V.Z), FVector2D(V.X, V.Y).Size())));
			}
		}
	};

	/** The smoothest Hermite between two frames: the tangent length with the gentlest tightest bend. */
	FHermite BestHermite(const FSkyFrame& A, const FSkyFrame& B, double& MinR, double& MaxSlope)
	{
		const double D = FVector::Dist(A.P, B.P);
		FHermite Best{ A.P, B.P, A.F * D * 0.5, B.F * D * 0.5 };
		double BestR = -1, BestS = 90;
		for (const double K : { 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5 })
		{
			const FHermite H{ A.P, B.P, A.F * D * K, B.F * D * K };
			double R, S;
			H.Measure(R, S);
			if (R > BestR + 1e-6 || (FMath::Abs(R - BestR) < 1e-6 && S < BestS)) { BestR = R; BestS = S; Best = H; }
		}
		MinR = BestR; MaxSlope = BestS;
		return Best;
	}

	/** Frames along a connector from A to B, widths WA -> WB (bEarly: the width changes in the first 40%). */
	double ConnectorFrames(const FHermite& H, const FSkyFrame& A, const FSkyFrame& B, double WA, double WB, int32 WidthMode, double S0, TArray<FSkyFrame>& Out)
	{
		FShape Sh;
		Sh.bWorld = true;
		Sh.EstLen = FMath::Max(1.0, FVector::Dist(A.P, B.P) * 1.3);
		Sh.Fn = [H, WA, WB, WidthMode](double T)
		{
			FSample S;
			S.P = T < 0 ? H.A + H.TA.GetSafeNormal() * (T * H.TA.Size()) : T > 1 ? H.B + H.TB.GetSafeNormal() * ((T - 1) * H.TB.Size()) : H.P(T);
			const double K = WidthMode == 0 ? Smooth(0.0, 0.4, T) : WidthMode == 1 ? Smooth(0.6, 1.0, T) : Smooth(0.2, 0.8, T);
			S.W = WA + (WB - WA) * K;
			return S;
		};
		FSkyFrame SA = A, SB = B;
		const double Len = SampleShape(Sh, FVector::ZeroVector, 0, 0, S0, &SA, &SB, Out);
		if (Out.Num() < 2) { Out = { A, B }; Out[0].S = S0; Out[1].S = S0 + FVector::Dist(A.P, B.P); }
		Out[0].Width = WA; Out.Last().Width = WB;
		return Len;
	}

	/** A piece laid from a boundary: its shape, the boundary it ends at, and any problems with it. The settings are
	 *  clamped to the limits so there's always something to draw (the errors make the course invalid). */
	struct FPieceBuild
	{
		FShape Shape;
		FState End;
		double EndYaw = 0, EndRoll = 0;   // change over the piece (rad)
	};

	/** A corkscrew's layout for a deck width: the climb (and descent) length and height that keep the rolling deck's lower
	 *  edge above where it started, the helix radius, and the length left for the roll. Len < 0: the shortest that
	 *  works (one turn per 20 m), rounded up to 5 m. */
	/** A corkscrew's roll over its rolling stretch, t 0..1 -> 0..1: the roll rate ramps up over the first quarter, holds,
	 *  and ramps down over the last (C1), so the fastest twist is only 4/3 of the average. */
	double CorkRoll(double T)
	{
		constexpr double A = 0.25;
		T = FMath::Clamp(T, 0.0, 1.0);
		if (T < A) return T * T / (2 * A * (1 - A));
		if (T > 1 - A) return 1 - (1 - T) * (1 - T) / (2 * A * (1 - A));
		return (T - A * 0.5) / (1 - A);
	}
	constexpr double CorkMaxTwist = 0.12;   // rad per metre at the fastest: a deck x m off its centre line slopes x * twist
	constexpr double CorkWideDeck = 11.0;   // m: a deck wider than this twists slower (CorkTwist), so wide lanes stay as easy as 2 standard lanes
	/** The fastest twist (rad/m) for a deck W wide. The AI tuning showed a wider deck throws an off-centre car out harder
	 *  (slope = distance from the middle x twist, and the car can be further out), so past 11 m the rate falls as
	 *  sqrt(11 / W): the edge slope at the extreme stays what it is on 2 standard lanes. Never faster than before. */
	double CorkTwist(double W) { return CorkMaxTwist * FMath::Min(1.0, FMath::Sqrt(CorkWideDeck / FMath::Max(W, 1.0))); }
	constexpr double CorkRh = 1.0;          // helix radius: v^2 / r presses the car in upside down from ~40 m/s

	FCorkPlan PlanCorkscrew(double W, double Len, double Turns)
	{
		// climb while level, roll, come back down. The roll can't be fast: a wide deck twisting at tau rad/m slopes
		// x * tau a distance x off its centre line, so at 0.47 rad/m a car 3.5 m off centre met a 58 degree slope and
		// was thrown off (PIE, 22 Oct). At 0.12 rad/m that's 13 degrees 2 m off centre.
		const double Tot = 2 * UE_DOUBLE_PI * FMath::Max(Turns, 0.01);
		FCorkPlan C;
		C.Rh = CorkRh;
		double Dip = 0;
		for (int32 i = 0; i <= 200; ++i)
		{
			const double Ph = Tot * i / 200.0;
			Dip = FMath::Max(Dip, 0.5 * W * FMath::Abs(FMath::Sin(Ph)) - C.Rh * (1 - FMath::Cos(Ph)));
		}
		C.Lift = Dip * 1.05;
		// a gentle climb: no steeper than ~20 degrees and a crest the car stays on at race speed
		C.Rise = C.Lift > 0 ? FMath::Max(4.1 * C.Lift, FMath::Sqrt(100.0 * C.Lift)) : 0.0;
		const double MinRoll = Tot * (4.0 / 3.0) / CorkTwist(W);
		C.Len = Len > 0 ? Len : FMath::Max(LimCorkLen.Min, FMath::CeilToDouble((2 * C.Rise + MinRoll) / 5.0) * 5.0);
		C.Roll = FMath::Max(C.Len - 2 * C.Rise, 1.0);
		return C;
	}

	bool MakePieceShape(const FSkyPiece& P, const FState& St, const FString& Lb, FPieceBuild& Out, TArray<FString>& Errors, TArray<FString>& Warnings)
	{
		const double W0 = St.W;
		FShape& Sh = Out.Shape;
		Out.End = St;
		Out.EndYaw = 0; Out.EndRoll = 0;
		auto StraightShape = [&Sh, W0](double Len)
		{
			Sh.EstLen = Len;
			Sh.Fn = [Len, W0](double U) { FSample S; S.P = FVector(Len * U, 0, 0); S.W = W0; return S; };
		};
		switch (P.Type)
		{
		case ESkyPiece::Start: StraightShape(StartLength); break;
		case ESkyPiece::Finish: case ESkyPiece::Checkpoint: StraightShape(GateLength); break;
		case ESkyPiece::Straight: InRange(Errors, Lb, TEXT("length"), P.Length, LimStraight); StraightShape(Clamp(P.Length, LimStraight)); break;
		case ESkyPiece::Booster: InRange(Errors, Lb, TEXT("length"), P.Length, LimBoost); StraightShape(Clamp(P.Length, LimBoost)); break;
		case ESkyPiece::Curve:
		{
			InRange(Errors, Lb, TEXT("angle"), P.Angle, LimAngle);
			InRange(Errors, Lb, TEXT("radius"), P.Radius, LimRadius);
			InRange(Errors, Lb, TEXT("bank"), P.Bank, LimBank);
			double A = Clamp(P.Angle, LimAngle);
			if (FMath::Abs(A) < 1) { Errors.Add(Lb + TEXT(": angle must be at least 1 degree either way (+ turns left, - right)")); A = A < 0 ? -1 : 1; }
			const double R = Clamp(P.Radius, LimRadius);
			if (R < W0 * 0.5 + 2.0 - 1e-9)
				Errors.Add(FString::Printf(TEXT("%s: radius %s is too tight for %d lanes (the inside edge would fold over): at least %s"), *Lb, *Num(R), St.Lanes, *Num(FMath::CeilToDouble(W0 * 0.5 + 2.0))));
			const double Sg = A < 0 ? -1.0 : 1.0, Ang = FMath::DegreesToRadians(FMath::Abs(A));
			const double Bank = FMath::DegreesToRadians(Clamp(P.Bank, LimBank));
			const double Len = R * Ang;
			const double T = FMath::Clamp(12.0 / FMath::Max(Len, 1.0), 0.15, 0.5);   // bank in and out over ~12 m
			Sh.EstLen = Len;
			Sh.Fn = [R, Sg, Ang, Bank, T, W0](double U)
			{
				FSample S;
				const double Th = Ang * U;
				const double Bk = Bank * Smooth(0, T, U) * Smooth(0, T, 1 - U);
				// banked into the turn: a left turn drops the left side; the low edge stays where it was (the centre rises)
				S.Roll = -Sg * Bk;
				S.P = FVector(R * FMath::Sin(Th), Sg * R * (1 - FMath::Cos(Th)), 0.5 * W0 * FMath::Sin(FMath::Abs(Bk)));
				S.W = W0;
				return S;
			};
			Out.EndYaw = Sg * Ang;
			break;
		}
		case ESkyPiece::Ramp:
		{
			InRange(Errors, Lb, TEXT("length"), P.Length, LimRampLen);
			InRange(Errors, Lb, TEXT("rise"), P.Rise, LimRise);
			const double Len = Clamp(P.Length, LimRampLen), Rise = Clamp(P.Rise, LimRise);
			if (1.5 * FMath::Abs(Rise) > Len + 1e-6)   // smoothstep's steepest slope is 1.5 * rise / length
				Errors.Add(FString::Printf(TEXT("%s: rise %s over %s m is steeper than 45 degrees (at most %s m for this length, or make it at least %s m long)"),
					*Lb, *Num(Rise), *Num(Len), *Num(FMath::FloorToDouble(Len / 1.5 * 10) / 10), *Num(FMath::CeilToDouble(1.5 * FMath::Abs(Rise)))));
			Sh.EstLen = FMath::Sqrt(Len * Len + Rise * Rise) * 1.05;
			Sh.Fn = [Len, Rise, W0](double U) { FSample S; S.P = FVector(Len * U, 0, Rise * Smooth(0, 1, U)); S.W = W0; return S; };
			break;
		}
		case ESkyPiece::Jump:
		{
			InRange(Errors, Lb, TEXT("gap"), P.Gap, LimGap);
			InRange(Errors, Lb, TEXT("drop"), P.Drop, LimDrop);
			const double Gap = Clamp(P.Gap, LimGap), Drop = Clamp(P.Drop, LimDrop);
			const double La = FMath::DegreesToRadians(JumpLipAngle), Rl = JumpLipRadius;
			const double Tn = FMath::Tan(La), Cs = FMath::Cos(La);
			const double XL = Rl * FMath::Sin(La), ZL = Rl * (1 - FMath::Cos(La)), LipLen = Rl * La;
			// the take-off speed that lands on the pad: the pad starts on the ballistic path with its slope and bends
			// back to level (a parabola) at Drop; lengthen the pad until the landing is no steeper than 42 degrees
			double Pad = 16, K = 0, M = 0;
			for (int32 It = 0; It < 20; ++It)
			{
				K = (ZL + Tn * (Gap + Pad * 0.5) - Drop) / (Gap * (Gap + Pad));
				M = 2 * K * Gap - Tn;
				if (K <= 0 || M <= 0.9) break;
				Pad += 4;
			}
			double V = 0;
			if (K <= 1e-6)
			{
				Errors.Add(FString::Printf(TEXT("%s: the landing (drop %s) is too high to reach from a %s degree lip over a %s m gap: lower the drop or shorten the gap"),
					*Lb, *Num(Drop), *Num(JumpLipAngle), *Num(Gap)));
				K = 0.005; M = 2 * K * Gap - Tn;
			}
			V = FMath::Sqrt(Gravity / (2 * K * Cs * Cs));
			if (V > 95) Errors.Add(FString::Printf(TEXT("%s: clearing a %s m gap to drop %s needs %s mph: shorten the gap or land lower"), *Lb, *Num(Gap), *Num(Drop), *Num(FMath::RoundToDouble(V * 2.23694))));
			else if (V < 20) Warnings.Add(FString::Printf(TEXT("%s: the landing pad is reached at only %s mph, so cars at race speed land well past it (make the gap longer or the drop higher)"), *Lb, *Num(FMath::RoundToDouble(V * 2.23694))));
			else if (V > 75) Warnings.Add(FString::Printf(TEXT("%s: needs at least %s mph at the lip to reach the landing pad"), *Lb, *Num(FMath::RoundToDouble(V * 2.23694))));
			const double ZLand = ZL + Gap * Tn - K * Gap * Gap;
			const double GapLen = [&]() { double L = 0; FVector Q(0, 0, 0); for (int32 i = 1; i <= 64; ++i) { const double X = Gap * i / 64; const FVector N(X, 0, Tn * X - K * X * X); L += (N - Q).Size(); Q = N; } return L; }();
			const double PadLen = FMath::Sqrt(Pad * Pad + FMath::Square(ZLand - Drop)) * 1.02;
			const double Tot = LipLen + GapLen + PadLen;
			const double U1 = LipLen / Tot, U2 = (LipLen + GapLen) / Tot;
			Sh.EstLen = Tot;
			Sh.Breaks = { U1, U2 };
			Sh.Fn = [=](double U)
			{
				FSample S;
				S.W = W0;
				if (U <= U1)
				{
					const double Ph = La * U / U1;   // past the start (U < 0) the lip runs back flat
					S.P = U < 0 ? FVector(Rl * La * U / U1, 0, 0) : FVector(Rl * FMath::Sin(Ph), 0, Rl * (1 - FMath::Cos(Ph)));
				}
				else if (U < U2)
				{
					const double X = Gap * (U - U1) / (U2 - U1);
					S.P = FVector(XL + X, 0, ZL + Tn * X - K * X * X);
					S.bDeck = false;
				}
				else
				{
					// the pad: z(t) runs from the landing height with the path's slope to Drop, level (a parabola)
					const double T = FMath::Clamp((U - U2) / (1 - U2), 0.0, 1.0);
					const double Ex = U > 1 ? (U - 1) / (1 - U2) * Pad : 0.0;
					const double Zh = ZLand + (-M * Pad) * T + (M * Pad * 0.5) * T * T;
					const double Zp = (FMath::Abs(ZLand - Drop - M * Pad * 0.5) < 1e-6) ? Zh
						: (ZLand * (2 * T * T * T - 3 * T * T + 1) + (-M * Pad) * (T * T * T - 2 * T * T + T) + Drop * (-2 * T * T * T + 3 * T * T));
					S.P = FVector(XL + Gap + Pad * T + Ex, 0, Zp);
				}
				return S;
			};
			Out.End.P = St.P + FVector(FMath::Cos(St.Yaw), FMath::Sin(St.Yaw), 0) * (XL + Gap + Pad) + FVector(0, 0, Drop);
			break;
		}
		case ESkyPiece::Loop:
		{
			InRange(Errors, Lb, TEXT("radius"), P.Radius, LimLoopR);
			const double R = Clamp(P.Radius, LimLoopR);
			const double MaxOff = FMath::Max(12.0, W0 + 1.0);
			double Off = P.Offset < 0 ? W0 + 1.0 : P.Offset;
			if (P.Offset >= 0) InRange(Errors, Lb, TEXT("offset"), P.Offset, FLim{ 0, MaxOff });
			Off = FMath::Clamp(Off, 0.0, MaxOff);
			if (Off < W0 - 1e-6) Warnings.Add(FString::Printf(TEXT("%s: offset %s is less than the track width (%s m), so the exit overlaps the entry"), *Lb, *Num(Off), *Num(W0)));
			Sh.EstLen = 2 * UE_DOUBLE_PI * R * 1.05 + Off;
			Sh.Fn = [R, Off, W0](double U)
			{
				// a vertical circle, shifted sideways (+ = left) with zero slope at both ends so the exit clears the entry
				const double Th = 2 * UE_DOUBLE_PI * U;
				FSample S;
				S.P = FVector(R * FMath::Sin(Th), Off * (Th - FMath::Sin(Th)) / (2 * UE_DOUBLE_PI), R * (1 - FMath::Cos(Th)));
				S.Up = FVector(-FMath::Sin(Th), 0, FMath::Cos(Th));   // toward the loop's centre
				S.W = W0;
				return S;
			};
			Out.End.P = St.P + FVector(-FMath::Sin(St.Yaw), FMath::Cos(St.Yaw), 0) * Off;
			break;
		}
		case ESkyPiece::Corkscrew:
		{
			InRange(Errors, Lb, TEXT("turns"), P.Turns, LimTurns);
			const double Turns = Clamp(P.Turns, LimTurns);
			const double Tot0 = 2 * UE_DOUBLE_PI * Turns;
			const FCorkPlan Auto = PlanCorkscrew(W0, -1, Turns);
			if (P.Length > 0) InRange(Errors, Lb, TEXT("length"), P.Length, LimCorkLen);
			const double Len = P.Length > 0 ? Clamp(P.Length, LimCorkLen) : Auto.Len;
			const FCorkPlan Cp = PlanCorkscrew(W0, Len, Turns);
			if (Cp.Roll < Tot0 * (4.0 / 3.0) / CorkTwist(W0) - 1e-6)
				Errors.Add(FString::Printf(TEXT("%s: %s turn%s on %d lane%s need%s at least %s m (it climbs %s m while level so its edges stay above the ground, then twists slowly enough to drive: about 70 m a turn, more on a deck wider than 11 m)%s"),
					*Lb, *Num(Turns), Turns > 1 ? TEXT("s") : TEXT(""), St.Lanes, St.Lanes > 1 ? TEXT("s") : TEXT(""), Turns > 1 ? TEXT("") : TEXT("s"), *Num(Auto.Len),
					*Num(FMath::RoundToDouble(Cp.Lift * 10) / 10), Auto.Len > LimCorkLen.Max ? TEXT(": too long for one piece, so narrow the track first (a lanes piece)") : TEXT("")));
			const double Frac = FMath::Fmod(Turns, 1.0);
			if (FMath::Abs(Frac - 0.5) < 1e-6) Warnings.Add(Lb + TEXT(": a half turn leaves the track upside down; it stays that way until another half-turn corkscrew (only cars with wall fans hold on)"));
			else if (Frac > 1e-6 && Frac < 1 - 1e-6) Warnings.Add(FString::Printf(TEXT("%s: %s turns leave the track tilted; use whole turns (1 or 2) to end level"), *Lb, *Num(Turns)));
			// climb while the deck is level, roll on a tight helix round an axis just above the deck (the deck faces the
			// axis, so speed presses the car in upside down, and the helix is narrow enough that the path hardly swerves:
			// the car can follow it at speed), then come back down level. Rolling about the middle of the deck would put
			// its lower edge half a width below where it started; the climb keeps it above that.
			const double Tot = 2 * UE_DOUBLE_PI * Turns, Rh = Cp.Rh, H = Cp.Lift, Up1 = Cp.Rise, Rl0 = Cp.Rise, Rl1 = Len - Cp.Rise;
			Sh.EstLen = Len * 1.1 + 2 * H;
			Sh.bTwist = true;
			Sh.Fn = [Len, Rh, Tot, W0, H, Up1, Rl0, Rl1](double U)
			{
				const double X = Len * U;
				const double Ph = Tot * CorkRoll((X - Rl0) / FMath::Max(Rl1 - Rl0, 1e-3));
				const double Lift = H > 0 ? H * Smooth(0, Up1, X) * (1.0 - Smooth(Len - Up1, Len, X)) : 0.0;
				FSample S;
				S.P = FVector(X, Rh * FMath::Sin(Ph), Rh * (1 - FMath::Cos(Ph)) + Lift);
				S.Up = FVector(0, -FMath::Sin(Ph), FMath::Cos(Ph));
				S.W = W0;
				return S;
			};
			Out.EndRoll = Tot;
			{
				const FVector Loc = RotX(FVector(Len, Rh * FMath::Sin(Tot), Rh * (1 - FMath::Cos(Tot))), St.Roll);
				Out.End.P = St.P + FVector(FMath::Cos(St.Yaw), FMath::Sin(St.Yaw), 0) * Loc.X + FVector(-FMath::Sin(St.Yaw), FMath::Cos(St.Yaw), 0) * Loc.Y + FVector(0, 0, Loc.Z);
			}
			break;
		}
		case ESkyPiece::WallRide:
		{
			const double Need = 4.0 * W0 + 6.0;
			if (P.Length > 0) InRange(Errors, Lb, TEXT("length"), P.Length, LimWallLen);
			const double Len = P.Length > 0 ? Clamp(P.Length, LimWallLen) : FMath::Clamp(FMath::Max(40.0, FMath::CeilToDouble(Need / 5.0) * 5.0), LimWallLen.Min, LimWallLen.Max);
			if (Len < Need - 1e-6)
				Errors.Add(FString::Printf(TEXT("%s: %d lanes need at least %s m to twist up to the wall and back (length %s)"), *Lb, St.Lanes, *Num(FMath::CeilToDouble(Need)), *Num(Len)));
			const double Sd = P.Side < 0 ? -1.0 : 1.0;
			Sh.EstLen = Len * 1.15;
			Sh.bTwist = true;
			Sh.Fn = [Len, Sd, W0](double U)
			{
				// up to vertical over the first 42%, along the wall, and back; the low edge stays on the line it started on
				// (the centre rises by half the width), so the deck never dips into the ground
				const double Ph = 0.5 * UE_DOUBLE_PI * Smooth(0, 0.42, U) * Smooth(0, 0.42, 1 - U);
				const double Rho = Sd * Ph;
				FSample S;
				S.P = FVector(Len * U, 0, 0.5 * W0 * FMath::Sin(Ph));
				S.Up = FVector(0, -FMath::Sin(Rho), FMath::Cos(Rho));
				S.W = W0;
				return S;
			};
			break;
		}
		case ESkyPiece::Lanes:
		{
			InRange(Errors, Lb, TEXT("length"), P.Length, LimLanesLen);
			if (!InRange(Errors, Lb, TEXT("lanes"), P.Lanes, FLim{ (double)MinLanes, (double)MaxLanes })) {}
			const int32 N = FMath::Clamp(P.Lanes, MinLanes, MaxLanes);
			const double Len = Clamp(P.Length, LimLanesLen);
			const double W1 = N * St.LaneW;
			// align: the left (-1) or right (+1) edge stays put; the centre line moves sideways by half the change
			const double Al = P.Align < 0 ? 1.0 : P.Align > 0 ? -1.0 : 0.0;
			Sh.EstLen = Len * 1.02;
			Sh.Fn = [Len, W0, W1, Al](double U)
			{
				FSample S;
				S.W = W0 + (W1 - W0) * Smooth(0, 1, U);
				S.P = FVector(Len * U, Al * (W0 - S.W) * 0.5, 0);
				return S;
			};
			Out.End.P = St.P + FVector(FMath::Cos(St.Yaw), FMath::Sin(St.Yaw), 0) * Len + FVector(-FMath::Sin(St.Yaw), FMath::Cos(St.Yaw), 0) * (Al * (W0 - W1) * 0.5);
			Out.End.W = W1;
			Out.End.Lanes = N;
			break;
		}
		default:
			StraightShape(10);
			break;
		}
		Out.End.Yaw = St.Yaw + Out.EndYaw;
		Out.End.Roll = FMath::Fmod(St.Roll + Out.EndRoll, 2 * UE_DOUBLE_PI);
		if (Out.End.Roll > UE_DOUBLE_PI) Out.End.Roll -= 2 * UE_DOUBLE_PI;
		if (Out.End.Roll < -UE_DOUBLE_PI) Out.End.Roll += 2 * UE_DOUBLE_PI;
		// exact end position for the shapes that don't set it above
		if (P.Type != ESkyPiece::Jump && P.Type != ESkyPiece::Loop && P.Type != ESkyPiece::Corkscrew && P.Type != ESkyPiece::Lanes)
		{
			const FVector Loc = Sh.Fn(1.0).P;
			const FVector L2 = Sh.bTwist ? RotX(Loc, St.Roll) : Loc;
			Out.End.P = St.P + FVector(FMath::Cos(St.Yaw), FMath::Sin(St.Yaw), 0) * L2.X + FVector(-FMath::Sin(St.Yaw), FMath::Cos(St.Yaw), 0) * L2.Y + FVector(0, 0, L2.Z);
		}
		return true;
	}

	/** Lay a piece's frames: sampled, then the ends snapped to the exact boundaries. Returns the length. */
	double LayPiece(const FPieceBuild& PB, const FState& St, TArray<FSkyFrame>& Out)
	{
		const FSkyFrame A = St.Frame();
		FSkyFrame B = PB.End.Frame();
		return SampleShape(PB.Shape, St.P, St.Yaw, St.Roll, St.S, &A, &B, Out);
	}

	/** A split's lead-in for one branch: from its slot across the parent's deck, curving off by the branch angle and
	 *  widening late (once the leads have drawn apart) to the branch's width. */
	struct FLead { FState From; double Len = 30, Angle = 0, WEnd = 11; };
	FPieceBuild LeadShape(const FLead& Ld)
	{
		FPieceBuild PB;
		const double Len = Ld.Len, A = FMath::DegreesToRadians(Ld.Angle), W0 = Ld.From.W, W1 = Ld.WEnd;
		PB.Shape.EstLen = Len;
		PB.Shape.Fn = [Len, A, W0, W1](double U)
		{
			FSample S;
			if (FMath::Abs(A) < 1e-6) S.P = FVector(Len * U, 0, 0);
			else
			{
				const double R = Len / FMath::Abs(A), Sg = A < 0 ? -1.0 : 1.0, Th = FMath::Abs(A) * U;
				S.P = FVector(R * FMath::Sin(Th), Sg * R * (1 - FMath::Cos(Th)), 0);
			}
			S.W = W0 + (W1 - W0) * Smooth(0.6, 1.0, U);
			return S;
		};
		PB.EndYaw = A;
		PB.End = Ld.From;
		PB.End.Yaw = Ld.From.Yaw + A;
		const FVector Loc = PB.Shape.Fn(1.0).P;
		PB.End.P = Ld.From.P + FVector(FMath::Cos(Ld.From.Yaw), FMath::Sin(Ld.From.Yaw), 0) * Loc.X + FVector(-FMath::Sin(Ld.From.Yaw), FMath::Cos(Ld.From.Yaw), 0) * Loc.Y;
		PB.End.W = W1;
		return PB;
	}

	/** Where each branch's lead starts across the parent deck (slot centre offsets along L, + = left) and its width:
	 *  slots in order of angle (the leftmost branch on the left), sized by lanes. */
	void Slots(const TArray<int32>& Lanes, const TArray<double>& Key, double W, TArray<double>& Off, TArray<double>& Wid)
	{
		const int32 K = Lanes.Num();
		TArray<int32> Order;
		for (int32 b = 0; b < K; ++b) Order.Add(b);
		Order.Sort([&Key](int32 A, int32 B) { return Key[A] > Key[B] || (Key[A] == Key[B] && A < B); });
		int32 Sum = 0;
		for (const int32 N : Lanes) Sum += N;
		Off.SetNumZeroed(K); Wid.SetNumZeroed(K);
		double Edge = W * 0.5;
		for (const int32 b : Order)
		{
			const double Wb = W * Lanes[b] / FMath::Max(Sum, 1);
			Wid[b] = Wb;
			Off[b] = Edge - Wb * 0.5;
			Edge -= Wb;
		}
	}
}

// --- the bake ---------------------------------------------------------------------------------------------------------

namespace SkyModel
{
	using namespace SkyCourse;
	using namespace SkyGeom;
	class FBaker
	{
	public:
		FBaker(const FSkyCourse& InC, const FBox& InArea, FSkyBaked& InB) : C(InC), Area(InArea), B(InB) {}

		const FSkyCourse& C;
		FBox Area;
		FSkyBaked& B;
		TArray<FString> SeqPath;     // "pieces", "pieces[6].branches[1].pieces", ...
		TArray<FString> SegLabel;    // for messages
		TArray<double> SegLoopR;     // loop radius for loop segments (clearance exemption), else 0
		TSet<int32> Used;            // sequences already laid (a branch can't reuse one)
		int32 Checkpoints = 0;
		FSkyFrame MainEnd;
		bool bMainEndSet = false;
		double S0 = 0;

		int32 AddSeg(ESkySeg Kind, ESkyPiece Type, int32 Seq, int32 Piece, int32 Branch, int32 Lanes, TArray<FSkyFrame>&& Frames, const FString& Lbl, const TArray<int32>& From)
		{
			FSkySegment S;
			S.Kind = Kind; S.Type = Type; S.Seq = Seq; S.Piece = Piece; S.Branch = Branch; S.Lanes = Lanes;
			S.Frames = MoveTemp(Frames);
			const int32 I = B.Segs.Add(MoveTemp(S));
			SegLabel.Add(Lbl);
			SegLoopR.Add(0);
			for (const int32 F : From) if (B.Segs.IsValidIndex(F)) B.Segs[F].Next.AddUnique(I);
			return I;
		}

		void Gate(ESkyPiece Type, int32 Seg, int32 FrameIndex)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[Seg].Frames;
			FSkyBaked::FGate G{ Type, Seg, Fr[FMath::Clamp(FrameIndex, 0, Fr.Num() - 1)], B.Gates.Num() };
			B.Gates.Add(G);
		}

		FState BakeSeq(int32 Seq, FState St, int32 Depth, TArray<int32>& Tail)
		{
			const TArray<FSkyPiece>& Ps = C.Seqs[Seq].Pieces;
			for (int32 i = 0; i < Ps.Num(); ++i)
			{
				const FSkyPiece& P = Ps[i];
				const FString Path = FString::Printf(TEXT("%s[%d]"), *SeqPath[Seq], i);
				const FString Lb = Label(Path, P.Type);
				if ((int32)P.Type >= (int32)ESkyPiece::Count) { B.Errors.Add(Path + TEXT(": unknown piece type")); continue; }
				// where pieces may go
				if (P.Type == ESkyPiece::Start && (Seq != 0 || i != 0)) B.Errors.Add(Lb + TEXT(": the start must be the first piece of the main line (and there's only one)"));
				if (P.Type == ESkyPiece::Finish && (Seq != 0 || i != Ps.Num() - 1)) B.Errors.Add(Lb + TEXT(": the finish must be the last piece of the main line"));
				if (P.Type == ESkyPiece::Close && (Seq != 0 || i != Ps.Num() - 1)) { B.Errors.Add(Lb + TEXT(": close must be the last piece of the main line")); continue; }
				if (P.Type == ESkyPiece::Checkpoint && ++Checkpoints == MaxCheckpoints + 1) B.Errors.Add(FString::Printf(TEXT("%s: more than %d checkpoints"), *Lb, MaxCheckpoints));
				if (FMath::Abs(St.Roll) > 0.05 && P.Type != ESkyPiece::Corkscrew && P.Type != ESkyPiece::Straight && P.Type != ESkyPiece::Booster
					&& P.Type != ESkyPiece::Checkpoint && P.Type != ESkyPiece::Lanes && P.Type != ESkyPiece::WallRide)
					B.Warnings.Add(Lb + TEXT(": the track is upside down or tilted here (after a part-turn corkscrew)"));

				if (P.Type == ESkyPiece::Split) { St = BakeSplit(Seq, i, P, St, Depth, Tail, Path); continue; }
				if (P.Type == ESkyPiece::Close)
				{
					MainEnd = St.Frame(); bMainEndSet = true;
					MainEnd.Width = St.W;
					BakeClose(i, St, Tail, Lb);
					continue;
				}
				FPieceBuild PB;
				MakePieceShape(P, St, Lb, PB, B.Errors, B.Warnings);
				TArray<FSkyFrame> Fr;
				LayPiece(PB, St, Fr);
				const int32 Seg = AddSeg(ESkySeg::Piece, P.Type, Seq, i, INDEX_NONE, PB.End.Lanes, MoveTemp(Fr), Lb, Tail);
				if (P.Type == ESkyPiece::Loop) SegLoopR[Seg] = Clamp(P.Radius, LimLoopR);
				if (P.Type == ESkyPiece::Start) Gate(ESkyPiece::Start, Seg, B.Segs[Seg].Frames.Num() - 1);
				if (P.Type == ESkyPiece::Finish || P.Type == ESkyPiece::Checkpoint) Gate(P.Type, Seg, B.Segs[Seg].Frames.Num() / 2);
				Tail = { Seg };
				St = PB.End;
				St.S = B.Segs[Seg].Frames.Last().S;
			}
			return St;
		}

		FState BakeSplit(int32 Seq, int32 Pi, const FSkyPiece& P, FState St, int32 Depth, TArray<int32>& Tail, const FString& Path)
		{
			const FString Lb = Label(Path, ESkyPiece::Split);
			if (Depth >= MaxSplitDepth) B.Errors.Add(FString::Printf(TEXT("%s: splits nest %d deep at most (a split in a branch in a branch)"), *Lb, MaxSplitDepth));
			InRange(B.Errors, Lb, TEXT("length"), P.Length, LimSplitLen);
			InRange(B.Errors, Lb, TEXT("merge_length"), P.MergeLength, LimMergeLen);
			if (P.MergeLanes != 0) InRange(B.Errors, Lb, TEXT("merge_lanes"), P.MergeLanes, FLim{ (double)MinLanes, (double)MaxLanes });
			if (FMath::Abs(St.Roll) > 0.05) B.Errors.Add(Lb + TEXT(": a split needs the track the right way up"));
			const int32 K = FMath::Min(P.Branches.Num(), MaxBranches);
			if (P.Branches.Num() < 2 || P.Branches.Num() > MaxBranches) B.Errors.Add(FString::Printf(TEXT("%s: %d branches (a split has 2 to %d)"), *Lb, P.Branches.Num(), MaxBranches));
			if (K < 1)
			{
				// nothing to lay: carry on as if it were a short straight
				return St;
			}
			const double Len = Clamp(P.Length, LimSplitLen), MLen = Clamp(P.MergeLength, LimMergeLen);
			TArray<int32> Ln;
			TArray<double> Ang;
			for (int32 b = 0; b < K; ++b)
			{
				const FSkyBranch& Br = P.Branches[b];
				const FString BL = FString::Printf(TEXT("%s.branches[%d]"), *Path, b);
				int32 N = Br.Lanes <= 0 ? St.Lanes : Br.Lanes;
				if (N > MaxLanes) { InRange(B.Errors, BL, TEXT("lanes"), N, FLim{ (double)MinLanes, (double)MaxLanes }); }
				Ln.Add(FMath::Clamp(N, MinLanes, MaxLanes));
				InRange(B.Errors, BL, TEXT("angle"), Br.Angle, LimBranchAngle);
				Ang.Add(Clamp(Br.Angle, LimBranchAngle));
			}
			// which laps each branch is open on
			FSkyBaked::FSplitInfo Info;
			Info.Seq = Seq; Info.Piece = Pi; Info.Gate = P.Gate; Info.At = St.Frame();
			for (int32 b = 0; b < K; ++b)
			{
				TArray<int32> Open;
				const TArray<int32>& Want = P.Branches[b].Laps;
				for (int32 L = 1; L <= C.Laps; ++L) if (P.Gate == ESkyGate::None || Want.Num() == 0 || Want.Contains(L)) Open.Add(L);
				for (const int32 L : Want)
					if (L > C.Laps) B.Warnings.Add(FString::Printf(TEXT("%s.branches[%d]: lap %d is past the course's %d lap%s"), *Path, b, L, C.Laps, C.Laps == 1 ? TEXT("") : TEXT("s")));
				if (P.Gate == ESkyGate::None && Want.Num() > 0) B.Warnings.Add(FString::Printf(TEXT("%s.branches[%d]: laps are ignored with gate \"none\" (every branch is open)"), *Path, b));
				Info.OpenLaps.Add(MoveTemp(Open));
			}
			for (int32 L = 1; L <= C.Laps; ++L)
			{
				bool bAny = false;
				for (const TArray<int32>& O : Info.OpenLaps) bAny |= O.Contains(L);
				if (!bAny) B.Errors.Add(FString::Printf(TEXT("%s: no branch is open on lap %d"), *Lb, L));
			}
			const int32 SplitIndex = B.Splits.Add(Info);

			// lead-ins
			TArray<double> Off, Wid;
			Slots(Ln, Ang, St.W, Off, Wid);
			const FSkyFrame At = St.Frame();
			TArray<int32> Leads;
			TArray<FState> BranchStart;
			for (int32 b = 0; b < K; ++b)
			{
				FLead Ld;
				Ld.From = St;
				Ld.From.P = St.P + At.L * Off[b];
				Ld.From.W = Wid[b];
				Ld.From.Lanes = Ln[b];
				Ld.Len = Len; Ld.Angle = Ang[b]; Ld.WEnd = Ln[b] * C.LaneWidth;
				FPieceBuild PB = LeadShape(Ld);
				PB.End.Lanes = Ln[b];
				TArray<FSkyFrame> Fr;
				LayPiece(PB, Ld.From, Fr);
				Leads.Add(AddSeg(ESkySeg::SplitLead, ESkyPiece::Split, Seq, Pi, b, Ln[b], MoveTemp(Fr), FString::Printf(TEXT("%s.branches[%d] (lead-in)"), *Path, b), Tail));
				FState BS = PB.End;
				BS.S = B.Segs[Leads.Last()].Frames.Last().S;
				BranchStart.Add(BS);
			}
			B.Splits[SplitIndex].LeadSegs = Leads;

			// the branches
			TArray<FState> Ends;
			TArray<TArray<int32>> Tails;
			TArray<int32> First, Last;
			for (int32 b = 0; b < K; ++b)
			{
				const FSkyBranch& Br = P.Branches[b];
				TArray<int32> T = { Leads[b] };
				FState E = BranchStart[b];
				First.Add(B.Segs.Num());
				if (Br.Seq != INDEX_NONE)
				{
					if (!C.Seqs.IsValidIndex(Br.Seq) || Br.Seq == 0 || Used.Contains(Br.Seq))
						B.Errors.Add(FString::Printf(TEXT("%s.branches[%d]: its piece list is missing or used twice"), *Path, b));
					else
					{
						Used.Add(Br.Seq);
						SeqPath.SetNum(FMath::Max(SeqPath.Num(), C.Seqs.Num()));
						SeqPath[Br.Seq] = FString::Printf(TEXT("%s.branches[%d].pieces"), *Path, b);
						E = BakeSeq(Br.Seq, E, Depth + 1, T);
					}
				}
				Last.Add(B.Segs.Num());
				if (FMath::Abs(E.Roll) > 0.05) B.Errors.Add(FString::Printf(TEXT("%s.branches[%d]: ends upside down or tilted; right it (another corkscrew) before the merge"), *Path, b));
				Ends.Add(E);
				Tails.Add(T);
			}

			// the merge: ahead of the farthest branch end along the branches' average heading, connectors into slots
			FVector Dir(0, 0, 0);
			int32 Sum = 0;
			for (int32 b = 0; b < K; ++b) { Dir += FVector(FMath::Cos(Ends[b].Yaw), FMath::Sin(Ends[b].Yaw), 0); Sum += Ln[b]; }
			if (Dir.Size() < 0.3 * K) B.Errors.Add(Lb + TEXT(": the branches end pointing different ways, so they can't merge: turn them to end heading the same way"));
			Dir = Dir.GetSafeNormal();
			if (Dir.IsNearlyZero()) Dir = FVector(FMath::Cos(St.Yaw), FMath::Sin(St.Yaw), 0);
			const FVector Lft(-Dir.Y, Dir.X, 0);
			double Lat = 0, Z = 0, TMax = -1e18;
			TArray<double> EndLat;
			for (int32 b = 0; b < K; ++b)
			{
				Lat += FVector::DotProduct(Ends[b].P, Lft) * Ln[b];
				Z += Ends[b].P.Z * Ln[b];
				TMax = FMath::Max(TMax, FVector::DotProduct(Ends[b].P, Dir));
				EndLat.Add(FVector::DotProduct(Ends[b].P, Lft));
			}
			Lat /= FMath::Max(Sum, 1); Z /= FMath::Max(Sum, 1);
			const double MergeYaw = FMath::Atan2(Dir.Y, Dir.X);
			const double WIn = St.W;   // the merge mirrors the split: slots across the width the track had before it
			TArray<double> MOff, MWid;
			Slots(Ln, EndLat, WIn, MOff, MWid);
			TArray<FHermite> Hs;
			TArray<FSkyFrame> SlotF;
			FVector M = FVector::ZeroVector;
			bool bOk = false;
			TArray<int32> Bad;
			for (const double Extra : { 12.0, 18.0, 25.0, 35.0, 50.0, 70.0, 95.0, 125.0, 160.0, 200.0, 250.0, 300.0 })
			{
				M = Dir * (TMax + Extra) + Lft * Lat + FVector(0, 0, Z);
				Hs.Reset(); SlotF.Reset(); Bad.Reset();
				for (int32 b = 0; b < K; ++b)
				{
					FSkyFrame E = Ends[b].Frame();
					FSkyFrame Sl = MakeFrame(M + Lft * MOff[b], MergeYaw, 0, MWid[b]);
					double R, Sl2;
					const FHermite H = BestHermite(E, Sl, R, Sl2);
					if (R < ConnMinRadius || Sl2 > ConnMaxSlope) Bad.Add(b);
					Hs.Add(H); SlotF.Add(Sl);
				}
				if (Bad.Num() == 0) { bOk = true; break; }
			}
			if (!bOk)
				for (const int32 b : Bad)
					B.Errors.Add(FString::Printf(TEXT("%s.branches[%d]: can't reach the merge (its connector would be tighter than a %s m radius or steeper than %s degrees): end the branches closer together, heading the same way and at similar heights"),
						*Path, b, *Num(ConnMinRadius), *Num(ConnMaxSlope)));
			// merge connectors
			TArray<int32> MLeads;
			TArray<double> BranchLen;
			for (int32 b = 0; b < K; ++b)
			{
				TArray<FSkyFrame> Fr;
				FSkyFrame E = Ends[b].Frame();
				ConnectorFrames(Hs[b], E, SlotF[b], Ends[b].W, MWid[b], 0, Ends[b].S, Fr);
				BranchLen.Add(Fr.Last().S - St.S);
				MLeads.Add(AddSeg(ESkySeg::MergeLead, ESkyPiece::Split, Seq, Pi, b, Ln[b], MoveTemp(Fr), FString::Printf(TEXT("%s.branches[%d] (merge connector)"), *Path, b), Tails[b]));
			}
			// S runs at the same rate on every branch so they all reach the merge at the same S (branch 0 sets it)
			for (int32 b = 0; b < K; ++b)
			{
				const double Scale = BranchLen[b] > 1e-3 ? BranchLen[0] / BranchLen[b] : 1.0;
				if (FMath::Abs(Scale - 1) < 1e-9) continue;
				auto Rescale = [&](int32 Seg) { for (FSkyFrame& F : B.Segs[Seg].Frames) F.S = St.S + (F.S - St.S) * Scale; };
				Rescale(Leads[b]);
				for (int32 s = First[b]; s < Last[b]; ++s) Rescale(s);
				Rescale(MLeads[b]);
			}
			// the trunk: from the slots' width to merge_lanes
			const int32 NOut = P.MergeLanes > 0 ? FMath::Clamp(P.MergeLanes, MinLanes, MaxLanes) : St.Lanes;
			FState TS;
			TS.LaneW = C.LaneWidth; TS.P = M; TS.Yaw = MergeYaw; TS.Roll = 0; TS.W = WIn; TS.Lanes = St.Lanes; TS.S = St.S + BranchLen[0];
			FSkyPiece Tp; Tp.Type = ESkyPiece::Lanes; Tp.Lanes = NOut; Tp.Length = MLen; Tp.Align = 0;
			FPieceBuild PB;
			TArray<FString> Ignore;
			MakePieceShape(Tp, TS, Lb, PB, Ignore, Ignore);
			PB.End.W = NOut * C.LaneWidth; PB.End.Lanes = NOut;
			TArray<FSkyFrame> Fr;
			LayPiece(PB, TS, Fr);
			const int32 Trunk = AddSeg(ESkySeg::MergeTrunk, ESkyPiece::Split, Seq, Pi, INDEX_NONE, NOut, MoveTemp(Fr), Lb + TEXT(" merge"), MLeads);
			Tail = { Trunk };
			FState Out = PB.End;
			Out.S = B.Segs[Trunk].Frames.Last().S;
			return Out;
		}

		void BakeClose(int32 Pi, const FState& St, TArray<int32>& Tail, const FString& Lb)
		{
			const FSkyFrame Goal = [&]() { FSkyFrame F = MakeFrame(C.Start, FMath::DegreesToRadians(C.Yaw), 0, FMath::Clamp(C.Lanes, MinLanes, MaxLanes) * C.LaneWidth); return F; }();
			const FSkyFrame From = St.Frame();
			if (FMath::Abs(St.Roll) > 0.05) B.Errors.Add(Lb + TEXT(": the track must be the right way up to close the lap"));
			double R = 1e9, Sl = 0;
			const double D = FVector::Dist(From.P, Goal.P);
			TArray<FSkyFrame> Fr;
			if (D < 0.3 && FVector::DotProduct(From.F, Goal.F) > 0.999)
			{
				Fr = { From, Goal };
				Fr[0].S = St.S; Fr[1].S = St.S + D; Fr[1].Width = Goal.Width;
			}
			else
			{
				const FHermite H = BestHermite(From, Goal, R, Sl);
				if (R < ConnMinRadius || Sl > ConnMaxSlope)
					B.Errors.Add(FString::Printf(TEXT("%s: can't reach the start gate smoothly from the end of the track (the connector would be tighter than a %s m radius or steeper than %s degrees; it's %s m away): end the track closer to the start, heading toward it and at a similar height"),
						*Lb, *Num(ConnMinRadius), *Num(ConnMaxSlope), *Num(FMath::RoundToDouble(D))));
				ConnectorFrames(H, From, Goal, St.W, Goal.Width, 2, St.S, Fr);
			}
			const int32 Seg = AddSeg(ESkySeg::CloseLink, ESkyPiece::Close, 0, Pi, INDEX_NONE, FMath::Clamp(C.Lanes, MinLanes, MaxLanes), MoveTemp(Fr), Lb, Tail);
			if (B.Segs.Num() > 0) B.Segs[Seg].Next.AddUnique(0);
			Tail = { Seg };
			B.bLapCourse = true;
		}

		void Run();
		void Clearances();
	};

	// --- clearance: no two parts of the track closer than 3 m unless they're neighbours along it ---

	double SegSegDist(const FVector& P1, const FVector& Q1, const FVector& P2, const FVector& Q2)
	{
		// closest points of two segments (Ericson, Real-Time Collision Detection 5.1.9)
		const FVector D1 = Q1 - P1, D2 = Q2 - P2, R = P1 - P2;
		const double A = D1 | D1, E = D2 | D2, F = D2 | R;
		double S = 0, T = 0;
		if (A <= 1e-9 && E <= 1e-9) return R.Size();
		if (A <= 1e-9) T = FMath::Clamp(F / E, 0.0, 1.0);
		else
		{
			const double Cc = D1 | R;
			if (E <= 1e-9) S = FMath::Clamp(-Cc / A, 0.0, 1.0);
			else
			{
				const double Bb = D1 | D2, Den = A * E - Bb * Bb;
				S = Den > 1e-12 ? FMath::Clamp((Bb * F - Cc * E) / Den, 0.0, 1.0) : 0.0;
				T = (Bb * S + F) / E;
				if (T < 0) { T = 0; S = FMath::Clamp(-Cc / A, 0.0, 1.0); }
				else if (T > 1) { T = 1; S = FMath::Clamp((Bb - Cc) / A, 0.0, 1.0); }
			}
		}
		return ((P1 + D1 * S) - (P2 + D2 * T)).Size();
	}

	void FBaker::Clearances()
	{
		const int32 NS = B.Segs.Num();
		if (NS < 2) return;
		// joints: segment ends that meet (union-find), then path distances between joints up to NearPath
		TArray<int32> Par;
		Par.SetNum(NS * 2);
		for (int32 i = 0; i < Par.Num(); ++i) Par[i] = i;
		auto Find = [&Par](int32 X) { while (Par[X] != X) { Par[X] = Par[Par[X]]; X = Par[X]; } return X; };
		for (int32 i = 0; i < NS; ++i) for (const int32 N : B.Segs[i].Next) if (N >= 0 && N < NS) Par[Find(i * 2 + 1)] = Find(N * 2);
		TArray<double> SegLen;
		SegLen.SetNum(NS);
		for (int32 i = 0; i < NS; ++i)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[i].Frames;
			double L = 0;
			for (int32 k = 1; k < Fr.Num(); ++k) L += FVector::Dist(Fr[k].P, Fr[k - 1].P);
			SegLen[i] = L;
		}
		TMap<int32, TArray<TPair<int32, double>>> Adj;
		for (int32 i = 0; i < NS; ++i)
		{
			const int32 A = Find(i * 2), Bn = Find(i * 2 + 1);
			Adj.FindOrAdd(A).Add({ Bn, SegLen[i] });
			Adj.FindOrAdd(Bn).Add({ A, SegLen[i] });
		}
		TMap<uint64, double> Dist;   // joint pair -> path distance (only when < NearPath)
		auto Key = [](int32 A, int32 Bn) { return A < Bn ? ((uint64)(uint32)A << 32) | (uint32)Bn : ((uint64)(uint32)Bn << 32) | (uint32)A; };
		for (const auto& KV : Adj)
		{
			TMap<int32, double> Best;
			TArray<TPair<double, int32>> Open = { { 0.0, KV.Key } };
			Best.Add(KV.Key, 0);
			while (Open.Num())
			{
				int32 Bi = 0;
				for (int32 k = 1; k < Open.Num(); ++k) if (Open[k].Key < Open[Bi].Key) Bi = k;
				const TPair<double, int32> Cur = Open[Bi];
				Open.RemoveAtSwap(Bi);
				if (Cur.Key > Best.FindRef(Cur.Value) + 1e-9) continue;
				for (const TPair<int32, double>& E : Adj[Cur.Value])
				{
					const double Nd = Cur.Key + E.Value;
					if (Nd >= NearPath) continue;
					const double* Old = Best.Find(E.Key);
					if (!Old || Nd < *Old - 1e-9) { Best.Add(E.Key, Nd); Open.Add({ Nd, E.Key }); }
				}
			}
			for (const auto& Bv : Best) { double& D = Dist.FindOrAdd(Key(KV.Key, Bv.Key), 1e18); D = FMath::Min(D, Bv.Value); }
		}
		auto JD = [&](int32 A, int32 Bn) -> double { if (A == Bn) return 0; const double* D = Dist.Find(Key(A, Bn)); return D ? *D : 1e18; };

		struct FProbe { int32 Seg; double S; FVector A, Bp; FVector Lo, Hi; };
		TArray<FProbe> Pr;
		for (int32 i = 0; i < NS; ++i)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[i].Frames;
			double S = 0;
			for (int32 k = 0; k < Fr.Num(); ++k)
			{
				if (k) S += FVector::Dist(Fr[k].P, Fr[k - 1].P);
				if ((k % 2) && k != Fr.Num() - 1) continue;
				FProbe P;
				P.Seg = i; P.S = S;
				P.A = Fr[k].P + Fr[k].L * (Fr[k].Width * 0.5);
				P.Bp = Fr[k].P - Fr[k].L * (Fr[k].Width * 0.5);
				const FVector H(Clearance * 0.5);
				P.Lo = P.A.ComponentMin(P.Bp) - H;
				P.Hi = P.A.ComponentMax(P.Bp) + H;
				Pr.Add(P);
			}
		}
		// loop zones: a loop's exit runs beside its own entry, so its neighbours near either end don't count
		struct FZone { int32 Seg, J0, J1; };
		TArray<FZone> Zones;
		for (int32 i = 0; i < NS; ++i) if (SegLoopR[i] > 0) Zones.Add({ i, Find(i * 2), Find(i * 2 + 1) });
		auto ToJoint = [&](const FProbe& P, int32 J) { return FMath::Min(P.S + JD(Find(P.Seg * 2), J), SegLen[P.Seg] - P.S + JD(Find(P.Seg * 2 + 1), J)); };
		auto InZone = [&](const FProbe& P, const FZone& Z) { return P.Seg == Z.Seg || FMath::Min(ToJoint(P, Z.J0), ToJoint(P, Z.J1)) < 15.0; };
		auto PathDist = [&](const FProbe& P, const FProbe& Q)
		{
			if (P.Seg == Q.Seg) return FMath::Abs(P.S - Q.S);
			const int32 PJ[2] = { Find(P.Seg * 2), Find(P.Seg * 2 + 1) }, QJ[2] = { Find(Q.Seg * 2), Find(Q.Seg * 2 + 1) };
			const double PD[2] = { P.S, SegLen[P.Seg] - P.S }, QD[2] = { Q.S, SegLen[Q.Seg] - Q.S };
			double Best = 1e18;
			for (int32 a = 0; a < 2; ++a) for (int32 b = 0; b < 2; ++b) Best = FMath::Min(Best, PD[a] + JD(PJ[a], QJ[b]) + QD[b]);
			return Best;
		};
		// spatial hash
		const double Cell = 8.0;
		auto CellOf = [Cell](const FVector& V) { return FIntVector(FMath::FloorToInt(V.X / Cell), FMath::FloorToInt(V.Y / Cell), FMath::FloorToInt(V.Z / Cell)); };
		auto CellKey = [](const FIntVector& C) { return ((uint64)(uint32)(C.X + 0x100000) << 42) | ((uint64)(uint32)(C.Y + 0x100000) << 21) | (uint64)(uint32)(C.Z + 0x100000); };
		TMap<uint64, TArray<int32>> Grid;
		for (int32 p = 0; p < Pr.Num(); ++p)
		{
			const FIntVector A = CellOf(Pr[p].Lo), Bc = CellOf(Pr[p].Hi);
			for (int32 x = A.X; x <= Bc.X; ++x) for (int32 y = A.Y; y <= Bc.Y; ++y) for (int32 z = A.Z; z <= Bc.Z; ++z)
				Grid.FindOrAdd(CellKey(FIntVector(x, y, z))).Add(p);
		}
		struct FHit { int32 SegA, SegB; double D; };
		TMap<uint64, FHit> Hits;   // per pair of labels (pieces), the closest
		for (const auto& KV : Grid)
		{
			const TArray<int32>& In = KV.Value;
			for (int32 i = 0; i < In.Num(); ++i)
			{
				const FProbe& P = Pr[In[i]];
				for (int32 j = i + 1; j < In.Num(); ++j)
				{
					const FProbe& Q = Pr[In[j]];
					if (P.Seg == Q.Seg) continue;
					// boxes overlap? and count the pair once: in the cell holding the overlap's low corner
					const FVector Lo = P.Lo.ComponentMax(Q.Lo), Hi = P.Hi.ComponentMin(Q.Hi);
					if (Lo.X > Hi.X || Lo.Y > Hi.Y || Lo.Z > Hi.Z) continue;
					if (CellKey(CellOf(Lo)) != KV.Key) continue;
					if (PathDist(P, Q) < NearPath) continue;
					bool bZone = false;
					for (const FZone& Z : Zones) if (InZone(P, Z) && InZone(Q, Z)) { bZone = true; break; }
					if (bZone) continue;
					const double D = SegSegDist(P.A, P.Bp, Q.A, Q.Bp);
					if (D >= Clearance) continue;
					const int32 Hi2 = FMath::Max(P.Seg, Q.Seg), Lo2 = FMath::Min(P.Seg, Q.Seg);
					const uint64 K = Key(Hi2, Lo2);
					FHit* H = Hits.Find(K);
					if (!H) Hits.Add(K, { Hi2, Lo2, D });
					else H->D = FMath::Min(H->D, D);
				}
			}
		}
		TArray<FHit> All;
		Hits.GenerateValueArray(All);
		All.Sort([](const FHit& A, const FHit& Bh) { return A.SegA < Bh.SegA || (A.SegA == Bh.SegA && A.SegB < Bh.SegB); });
		TSet<FString> Said;
		int32 Count = 0;
		for (const FHit& H : All)
		{
			const FString Msg = FString::Printf(TEXT("%s comes within %s m of %s: keep at least %s m between parts of the track (or cross over or under with more room)"),
				*SegLabel[H.SegA], *Num(FMath::RoundToDouble(H.D * 10) / 10), *SegLabel[H.SegB], *Num(Clearance));
			if (Said.Contains(SegLabel[H.SegA] + SegLabel[H.SegB])) continue;
			Said.Add(SegLabel[H.SegA] + SegLabel[H.SegB]);
			if (++Count > 12) { B.Errors.Add(TEXT("... and more parts of the track too close together")); break; }
			B.Errors.Add(Msg);
		}
	}

	void FBaker::Run()
	{
		B = FSkyBaked();
		if (C.Seqs.Num() == 0) { B.Errors.Add(TEXT("pieces: the course has no piece list")); return; }
		SeqPath.SetNum(C.Seqs.Num());
		SeqPath[0] = TEXT("pieces");
		Used.Add(0);
		// course settings
		InRange(B.Errors, TEXT("course"), TEXT("lanes"), C.Lanes, FLim{ (double)MinLanes, (double)MaxLanes });
		InRange(B.Errors, TEXT("course"), TEXT("lane_width"), C.LaneWidth, FLim{ MinLaneWidth, MaxLaneWidth });
		B.LaneWidth = FMath::Clamp(C.LaneWidth, MinLaneWidth, MaxLaneWidth);
		InRange(B.Errors, TEXT("course"), TEXT("laps"), C.Laps, FLim{ 1, (double)MaxLaps });
		InRange(B.Errors, TEXT("course"), TEXT("opponents"), C.Opponents, FLim{ 0, (double)MaxOpponents });
		InRange(B.Errors, TEXT("course"), TEXT("skill"), C.Skill, LimSkill);
		if (!C.Start.ContainsNaN() && C.Start.GetAbsMax() > 1e6) B.Errors.Add(TEXT("start: out of range"));
		// piece count (every sequence a split reaches)
		{
			TArray<int32> Stack = { 0 };
			TSet<int32> Seen;
			while (Stack.Num())
			{
				const int32 S = Stack.Pop();
				if (!C.Seqs.IsValidIndex(S) || Seen.Contains(S)) continue;
				Seen.Add(S);
				for (const FSkyPiece& P : C.Seqs[S].Pieces)
				{
					++B.PieceCount;
					for (const FSkyBranch& Br : P.Branches) Stack.Add(Br.Seq);
				}
			}
			if (B.PieceCount > MaxPieces) B.Errors.Add(FString::Printf(TEXT("pieces: %d pieces in all (branches included); the most is %d"), B.PieceCount, MaxPieces));
		}
		const TArray<FSkyPiece>& Main = C.Seqs[0].Pieces;
		if (Main.Num() == 0) B.Errors.Add(TEXT("pieces: the course has no pieces yet (start with { \"type\": \"start\" })"));
		else if (Main[0].Type != ESkyPiece::Start) B.Errors.Add(Label(TEXT("pieces[0]"), Main[0].Type) + TEXT(": the first piece must be start"));
		S0 = Main.Num() && Main[0].Type == ESkyPiece::Start ? -StartLength : 0.0;
		FState St;
		St.P = C.Start;
		St.Yaw = FMath::DegreesToRadians(C.Yaw);
		St.LaneW = B.LaneWidth;
		St.Lanes = FMath::Clamp(C.Lanes, MinLanes, MaxLanes);
		St.W = St.Lanes * St.LaneW;
		St.S = S0;
		TArray<int32> Tail;
		const FState E = BakeSeq(0, St, 0, Tail);
		if (!bMainEndSet) { MainEnd = E.Frame(); MainEnd.Width = E.W; }
		B.End = MainEnd;

		const bool bFinish = Main.Num() && Main.Last().Type == ESkyPiece::Finish;
		if (C.Laps > 1 && !B.bLapCourse) B.Errors.Add(FString::Printf(TEXT("course: %d laps need a lap course: end it with { \"type\": \"close\" } (or set laps to 1)"), C.Laps));
		if (Main.Num() > 1 && !B.bLapCourse && !bFinish)
			B.Warnings.Add(TEXT("course: the track doesn't end with finish or close yet (the end of the track counts as the finish)"));
		// a course without a finish gate still has one at its end, so a race can run on it
		if (!B.bLapCourse && !bFinish && B.Segs.Num() > 0 && Tail.Num() > 0)
			Gate(ESkyPiece::Finish, Tail[0], B.Segs[Tail[0]].Frames.Num() - 1);
		// length: start gate to finish gate, or once round
		if (B.bLapCourse && B.Segs.Num()) B.Length = B.Segs.Last().Frames.Last().S - S0;
		else
		{
			const FSkyBaked::FGate* Fin = B.Gates.FindByPredicate([](const FSkyBaked::FGate& G) { return G.Type == ESkyPiece::Finish; });
			B.Length = Fin ? Fin->At.S : E.S;
		}
		// the starting grid: 8 slots behind the start gate, 2 a row on 1-2 lanes (more on wider track), staggered
		if (B.Segs.Num() && Main.Num() && Main[0].Type == ESkyPiece::Start)
		{
			const TArray<FSkyFrame>& Fr = B.Segs[0].Frames;
			const int32 PerRow = FMath::Max(2, FMath::Clamp(C.Lanes, MinLanes, MaxLanes));
			const double Len = Fr.Last().S - Fr[0].S;
			for (int32 i = 0; i < 8; ++i)
			{
				const int32 Row = i / PerRow, Col = i % PerRow;
				const double Back = 6.0 + Row * (PerRow > 2 ? 9.0 : 6.5) + (Col % 2) * 3.0;
				const double At = FMath::Clamp(Len - Back, 0.0, Len);
				const int32 k = FMath::Clamp(FMath::RoundToInt(At / FMath::Max(Len, 1.0) * (Fr.Num() - 1)), 0, Fr.Num() - 1);
				const FSkyFrame& F = Fr[k];
				const double Across = F.Width * ((Col + 0.5) / PerRow - 0.5);
				const FVector P = F.P - F.L * Across;   // column 0 on the left
				const FRotator Rot = FRotationMatrix::MakeFromXZ(DirToUE(F.F), DirToUE(F.U)).Rotator();
				B.Grid.Add(FTransform(Rot, ToUE(P)));
			}
		}
		// bounds, heights, build area
		B.MinZ = 1e18; B.MaxZ = -1e18;
		const bool bArea = Area.IsValid && Area.GetSize().X > 0.01 && Area.GetSize().Y > 0.01;
		for (int32 i = 0; i < B.Segs.Num(); ++i)
		{
			bool bOut = false;
			FString Why;
			for (const FSkyFrame& F : B.Segs[i].Frames)
			{
				for (const double Sd : { -0.5, 0.0, 0.5 })
				{
					const FVector Q = F.P + F.L * (F.Width * Sd);
					B.Bounds += Q;
					if (F.bDeck) { B.MinZ = FMath::Min(B.MinZ, Q.Z); B.MaxZ = FMath::Max(B.MaxZ, Q.Z); }
					if (bArea && !bOut)
					{
						if (Q.X < Area.Min.X) { bOut = true; Why = FString::Printf(TEXT("x %s, the area starts at %s"), *Num(FMath::RoundToDouble(Q.X)), *Num(Area.Min.X)); }
						else if (Q.X > Area.Max.X) { bOut = true; Why = FString::Printf(TEXT("x %s, the area ends at %s"), *Num(FMath::RoundToDouble(Q.X)), *Num(Area.Max.X)); }
						else if (Q.Y < Area.Min.Y) { bOut = true; Why = FString::Printf(TEXT("y %s, the area starts at %s"), *Num(FMath::RoundToDouble(Q.Y)), *Num(Area.Min.Y)); }
						else if (Q.Y > Area.Max.Y) { bOut = true; Why = FString::Printf(TEXT("y %s, the area ends at %s"), *Num(FMath::RoundToDouble(Q.Y)), *Num(Area.Max.Y)); }
					}
				}
			}
			if (bOut) B.Errors.Add(FString::Printf(TEXT("%s leaves the build area (it reaches %s)"), *SegLabel[i], *Why));
		}
		if (B.MinZ > B.MaxZ) { B.MinZ = B.MaxZ = C.Start.Z; }
		if (!B.Bounds.IsValid) B.Bounds = FBox(C.Start, C.Start);
		Clearances();
		B.bValid = B.Errors.Num() == 0;
	}
}

void SkyCourse::Bake(const FSkyCourse& Course, const FBox& BuildArea, FSkyBaked& Out)
{
	using namespace SkyModel;
	FBaker Bk(Course, BuildArea, Out);
	Bk.Run();
}

// --- queries ----------------------------------------------------------------------------------------------------------

FSkyFrame SkyCourse::EndOf(const FSkyBaked& Baked, const FSkyCourse& Course, int32 Seq, int32* OutLanes)
{
	using namespace SkyModel;
	auto Fallback = [&]() { FSkyFrame F = SkyGeom::MakeFrame(Course.Start, FMath::DegreesToRadians(Course.Yaw), 0, Course.Lanes * Course.LaneWidth); if (OutLanes) *OutLanes = Course.Lanes; return F; };
	if (Seq == 0)
	{
		if (Baked.Segs.Num() == 0) return Fallback();
		// the main line's end (before any close)
		int32 Lanes = Course.Lanes;
		for (int32 i = Baked.Segs.Num() - 1; i >= 0; --i)
		{
			const FSkySegment& S = Baked.Segs[i];
			if (S.Seq == 0 && S.Kind != ESkySeg::CloseLink && (S.Kind == ESkySeg::Piece || S.Kind == ESkySeg::MergeTrunk)) { Lanes = S.Lanes; break; }
		}
		if (OutLanes) *OutLanes = Lanes;
		return Baked.End;
	}
	// a branch: its last piece's end, or its lead-in's end while it's empty
	int32 Best = INDEX_NONE;
	for (int32 i = 0; i < Baked.Segs.Num(); ++i)
	{
		const FSkySegment& S = Baked.Segs[i];
		if (S.Seq == Seq && (S.Kind == ESkySeg::Piece || S.Kind == ESkySeg::MergeTrunk)) Best = i;   // the last one laid
	}
	if (Best == INDEX_NONE)
	{
		for (int32 s = 0; s < Course.Seqs.Num() && Best == INDEX_NONE; ++s)
			for (int32 p = 0; p < Course.Seqs[s].Pieces.Num() && Best == INDEX_NONE; ++p)
			{
				const FSkyPiece& P = Course.Seqs[s].Pieces[p];
				for (int32 b = 0; b < P.Branches.Num(); ++b)
					if (P.Branches[b].Seq == Seq)
						for (int32 i = 0; i < Baked.Segs.Num(); ++i)
						{
							const FSkySegment& S = Baked.Segs[i];
							if (S.Kind == ESkySeg::SplitLead && S.Seq == s && S.Piece == p && S.Branch == b) { Best = i; break; }
						}
			}
	}
	if (Best == INDEX_NONE || Baked.Segs[Best].Frames.Num() == 0) return Fallback();
	if (OutLanes) *OutLanes = Baked.Segs[Best].Lanes;
	return Baked.Segs[Best].Frames.Last();
}

TArray<int32> SkyCourse::Route(const FSkyBaked& Baked, int32 Lap, const TArray<int32>& Choice)
{
	using namespace SkyModel;
	TArray<int32> Out;
	if (Baked.Segs.Num() == 0) return Out;
	const int32 L = FMath::Max(1, Lap);
	int32 Seg = 0;
	TSet<int32> Seen;
	while (Baked.Segs.IsValidIndex(Seg) && !Seen.Contains(Seg))
	{
		Seen.Add(Seg);
		Out.Add(Seg);
		const TArray<int32>& Nx = Baked.Segs[Seg].Next;
		if (Nx.Num() == 0) break;
		if (Nx.Num() == 1) { if (Nx[0] == 0) break; Seg = Nx[0]; continue; }
		// a split: the first branch open this lap, or the chosen one if it's open
		int32 Si = INDEX_NONE;
		for (int32 s = 0; s < Baked.Splits.Num(); ++s) if (Baked.Splits[s].LeadSegs.Contains(Nx[0])) { Si = s; break; }
		if (Si == INDEX_NONE) { Seg = Nx[0]; continue; }
		const FSkyBaked::FSplitInfo& Sp = Baked.Splits[Si];
		auto Open = [&](int32 b) { return Sp.OpenLaps.IsValidIndex(b) && Sp.OpenLaps[b].Contains(L); };
		int32 Pick = INDEX_NONE;
		if (Choice.IsValidIndex(Si) && Sp.LeadSegs.IsValidIndex(Choice[Si]) && Open(Choice[Si])) Pick = Choice[Si];
		for (int32 b = 0; b < Sp.LeadSegs.Num() && Pick == INDEX_NONE; ++b) if (Open(b)) Pick = b;
		if (Pick == INDEX_NONE) Pick = 0;
		Seg = Sp.LeadSegs[Pick];
	}
	return Out;
}

// --- shared with the track --------------------------------------------------------------------------------------------

bool SkyGeom::PieceFrames(const FSkyPiece& Piece, const FSkyFrame& Start, int32 Lanes, const FSkyFrame* CloseTo, TArray<TArray<FSkyFrame>>& Out, FString& Error)
{
	using namespace SkyModel;
	Out.Reset();
	FState St;
	St.P = Start.P;
	YawRoll(Start, St.Yaw, St.Roll);
	St.Roll = FMath::Abs(St.Roll) < 1e-3 ? 0.0 : St.Roll;
	St.Lanes = FMath::Clamp(Lanes, MinLanes, MaxLanes);
	// no course here: a boundary frame's width is its lanes times the lane width, so that gives the course's lane width
	St.LaneW = Start.Width > 1.0 ? FMath::Clamp(Start.Width / St.Lanes, MinLaneWidth, MaxLaneWidth) : DefaultLaneWidth;
	St.W = St.Lanes * St.LaneW;
	St.S = Start.S;
	TArray<FString> Errors, Warnings;
	if (Piece.Type == ESkyPiece::Split)
	{
		const int32 K = FMath::Clamp(Piece.Branches.Num(), 0, MaxBranches);
		TArray<int32> Ln;
		TArray<double> Ang;
		for (int32 b = 0; b < K; ++b) { Ln.Add(FMath::Clamp(Piece.Branches[b].Lanes <= 0 ? St.Lanes : Piece.Branches[b].Lanes, MinLanes, MaxLanes)); Ang.Add(Clamp(Piece.Branches[b].Angle, LimBranchAngle)); }
		TArray<double> Off, Wid;
		Slots(Ln, Ang, St.W, Off, Wid);
		const FSkyFrame At = St.Frame();
		for (int32 b = 0; b < K; ++b)
		{
			FLead Ld;
			Ld.From = St; Ld.From.P = St.P + At.L * Off[b]; Ld.From.W = Wid[b];
			Ld.Len = Clamp(Piece.Length, LimSplitLen); Ld.Angle = Ang[b]; Ld.WEnd = Ln[b] * St.LaneW;
			FPieceBuild PB = LeadShape(Ld);
			LayPiece(PB, Ld.From, Out.AddDefaulted_GetRef());
		}
		if (K < 2) { Error = TEXT("a split needs 2 to 4 branches"); return false; }
		return true;
	}
	if (Piece.Type == ESkyPiece::Close)
	{
		if (!CloseTo) { Error = TEXT("nowhere to close to"); return false; }
		FSkyFrame From = St.Frame();
		double R, Sl;
		const FHermite H = BestHermite(From, *CloseTo, R, Sl);
		ConnectorFrames(H, From, *CloseTo, St.W, CloseTo->Width, 2, St.S, Out.AddDefaulted_GetRef());
		if (R < ConnMinRadius || Sl > ConnMaxSlope) { Error = TEXT("can't reach the start gate smoothly from here"); return false; }
		return true;
	}
	FPieceBuild PB;
	MakePieceShape(Piece, St, Label(TEXT("piece"), Piece.Type), PB, Errors, Warnings);
	LayPiece(PB, St, Out.AddDefaulted_GetRef());
	if (Errors.Num()) { Error = Errors[0]; return false; }
	return true;
}

void SkyGeom::LaneLines(double Width, int32 Lanes0, int32 Lanes1, int32 Align, double Along01, TArray<double>& Out, double LaneWidth)
{
	using namespace SkyModel;
	Out.Reset();
	const int32 N = Along01 < 0.5 ? Lanes0 : Lanes1;
	if (N < 2) return;
	const double Inner = Width * 0.5 - LipWidth - 0.6;
	for (int32 i = 1; i < N; ++i)
	{
		double Y;
		if (Align < 0) Y = Width * 0.5 - i * LaneWidth;              // the left edge fixed: lanes counted from the left
		else if (Align > 0) Y = -Width * 0.5 + i * LaneWidth;        // the right edge fixed
		else Y = (i - N * 0.5) * (Width / N);                          // centred: evenly across
		if (FMath::Abs(Y) < Inner) Out.Add(Y);
	}
}

int32 SkyGeom::InnerEdges(const FSkyBaked& Baked, int32 Seg)
{
	using namespace SkyModel;
	if (!Baked.Segs.IsValidIndex(Seg)) return 0;
	const FSkySegment& S = Baked.Segs[Seg];
	if (S.Kind != ESkySeg::SplitLead && S.Kind != ESkySeg::MergeLead) return 0;
	// compare this lead with its siblings at the end where they touch: who's to the left and right of it
	const bool bStart = S.Kind == ESkySeg::SplitLead;
	if (S.Frames.Num() == 0) return 0;
	const FSkyFrame& Me = bStart ? S.Frames[0] : S.Frames.Last();
	bool bLeft = false, bRight = false;
	for (int32 i = 0; i < Baked.Segs.Num(); ++i)
	{
		const FSkySegment& O = Baked.Segs[i];
		if (i == Seg || O.Kind != S.Kind || O.Seq != S.Seq || O.Piece != S.Piece || O.Frames.Num() == 0) continue;
		const FSkyFrame& Th = bStart ? O.Frames[0] : O.Frames.Last();
		const double Side = FVector::DotProduct(Th.P - Me.P, Me.L);
		if (Side > 0.01) bLeft = true; else if (Side < -0.01) bRight = true;
	}
	return (bLeft ? 1 : 0) | (bRight ? 2 : 0);
}

// --- the example and the guide ----------------------------------------------------------------------------------------

FSkyCourse SkyCourse::Example(const FVector& Start, double Yaw)
{
	using namespace SkyModel;
	FSkyCourse C;
	C.Name = TEXT("Sky Loop");
	C.Author = TEXT("Sky City");
	C.Start = Start;
	C.Yaw = Yaw;
	C.Lanes = 2;
	C.LaneWidth = DefaultLaneWidth;
	C.Skin = ESkySkin::Unveil;
	C.Laps = 3;
	C.Opponents = 3;
	C.Skill = 0.8;
	auto Pc = [](ESkyPiece T) { FSkyPiece P = DefaultPiece(T, 2); return P; };
	auto Straight = [&](double L) { FSkyPiece P = Pc(ESkyPiece::Straight); P.Length = L; return P; };
	auto Curve = [&](double A, double R, double Bk) { FSkyPiece P = Pc(ESkyPiece::Curve); P.Angle = A; P.Radius = R; P.Bank = Bk; return P; };
	auto Ramp = [&](double L, double R) { FSkyPiece P = Pc(ESkyPiece::Ramp); P.Length = L; P.Rise = R; return P; };
	// a "U": out along the start line (loop, a hill, a jump), a banked U-turn left, back past the start through a split
	// (corkscrew on laps 1 and 3, wallride on lap 2), and a U-turn into a short close behind the start gate; it fits
	// 60 m behind the start, 360 m ahead and 115 m to the left (8 m lanes: the wallride and corkscrew branches are 150 m) (the build area's start spot leaves 60 m behind)
	TArray<FSkyPiece> M;
	M.Add(Pc(ESkyPiece::Start));
	M.Add(Straight(40));
	{ FSkyPiece P = Pc(ESkyPiece::Booster); P.Length = 12; M.Add(P); }
	{ FSkyPiece P = Pc(ESkyPiece::Loop); P.Radius = 10; P.Offset = -1; M.Add(P); }
	M.Add(Straight(30));
	M.Add(Ramp(40, 8));
	M.Add(Straight(20));
	M.Add(Ramp(40, -8));
	M.Add(Straight(20));
	{ FSkyPiece P = Pc(ESkyPiece::Jump); P.Gap = 36; P.Drop = 0; M.Add(P); }
	M.Add(Straight(10));
	M.Add(Pc(ESkyPiece::Checkpoint));
	M.Add(Curve(180, 31.5, 20));
	{ FSkyPiece P = Pc(ESkyPiece::Lanes); P.Lanes = 4; P.Length = 20; M.Add(P); }
	{
		FSkyPiece P = Pc(ESkyPiece::Split);
		P.Length = 30; P.Gate = ESkyGate::Lights; P.MergeLength = 25; P.MergeLanes = 2;
		P.Branches.Reset();
		FSkyBranch A; A.Lanes = 2; A.Angle = 12; A.Laps = { 1, 3 };
		FSkyBranch Bb; Bb.Lanes = 2; Bb.Angle = -12; Bb.Laps = { 2 };
		A.Seq = C.Seqs.AddDefaulted();
		{ FSkyPiece K = Pc(ESkyPiece::Corkscrew); K.Length = 150; K.Turns = 1; C.Seqs[A.Seq].Pieces.Add(K); }
		Bb.Seq = C.Seqs.AddDefaulted();
		{ FSkyPiece W = Pc(ESkyPiece::WallRide); W.Length = 70; W.Side = -1; C.Seqs[Bb.Seq].Pieces.Add(W); C.Seqs[Bb.Seq].Pieces.Add(Straight(80)); }
		P.Branches = { A, Bb };
		M.Add(P);
	}
	M.Add(Pc(ESkyPiece::Checkpoint));
	M.Add(Straight(40));
	M.Add(Curve(180, 40, 15));
	M.Add(Pc(ESkyPiece::Close));
	C.Seqs[0].Pieces = MoveTemp(M);
	return C;
}

FString SkyCourse::Guide()
{
	return TEXT(R"GUIDE(SKY CITY COURSE FORMAT (skycity-course, version 2)

UNITS AND FRAME
- Metres and degrees. x and y are the ground plane, z is up. Yaw is counter-clockwise from +x (yaw 90 faces +y).
- "start" is where the start piece begins, on the deck surface (put z about 0.3 m above the ground).
- Pieces snap end to end: each starts where the last ended, facing the same way, at the same height, with the same
  lanes. You never give positions after the start. + angles turn LEFT, - angles turn RIGHT.
- The track is 1 to 4 lanes (2 by default). Each lane is "lane_width" metres wide: 5.5 (standard), 8 (wide, the default)
  or 11 (extra wide), the same for the whole course, so 2 lanes are 16 m wide by default. Every number below that depends
  on the width is given for 8 m lanes. Every piece ends level (except a part-turn corkscrew).

THE COURSE
{ "format": "skycity-course", "version": 2, "name": "...", "author": "...",
  "start": { "x": 0, "y": 0, "z": 0.3, "yaw": 0 },
  "lanes": 2,            1-4, lanes at the start
  "lane_width": 8,       5.5 (standard), 8 (wide) or 11 (extra wide) m per lane; default 8. A version 1 file without it is 5.5
  "skin": "unveil",      "unveil" (concrete with red LED trim), "classic" (orange toy track, 0.6 m rails), "neon"
  "laps": 3,             1-9; more than 1 needs a lap course (ends with close)
  "opponents": 3,        0-7 AI cars;  "skill": 0.8   0.3-1.2
  "catch_up": true,      AI rubber band: a car far ahead eases off, one far behind pushes (never the player); default true
  "pieces": [ ... ] }
Unknown settings are errors, so spell them exactly as below. Missing optional settings get the defaults shown.

PIECES (type: settings, hard limits, default)
- start: no settings. Must be first. 30 m: the starting grid (8 cars) and the start gate at its end.
- finish: no settings. 6 m, the gate in the middle. Ends a point-to-point course (laps 1); must be last.
- checkpoint: no settings. 6 m gate. Up to 32. Cars must pass them in order.
- straight: length 2-300 (30).
- booster: length 4-30 (10). A speed strip that pushes cars at 45 m/s^2.
- curve: angle -270..270 (90; + left, - right, at least 1), radius 8-300 (40, at the centre line), bank -45..45 (0;
  + tilts into the turn). The bank rises and falls within the piece. The radius must be at least half the track width
  + 2 m: at 8 m lanes 8 (the minimum) for 1 lane, 10 for 2, 14 for 3, 18 for 4.
- ramp: length 4-150 (30, measured along the ground), rise -60..60 (8; - goes down). S-shaped, level at both ends.
  The steepest point is 1.5 x rise / length and must be <= 45 degrees: |rise| <= length / 1.5.
- jump: gap 4-80 (20), drop -30..30 (0). A 15 degree lip (7.8 m), an open gap, then a landing pad (16 m or more) that
  ends drop metres higher (+) or lower (-) than the jump started. The pad starts where the flight path of the take-off
  speed lands: that speed is the MINIMUM (slower cars fall short into the gap, faster ones land further down the pad),
  so plan for cars to arrive 5-15% faster. Minimum speeds for drop 0: gap 20 -> 34 m/s (76 mph), gap 36 -> 45 m/s
  (100 mph), gap 50 -> 52 m/s (117 mph). Landing lower (drop -) needs less speed, higher (drop +) more.
  The flight path is in the baked frames (frames with no deck), so get_course can show where cars fly.
- loop: radius 6-30 (12), offset 0 to 4 x lane_width + 1 (default the track width + 1 m: 17 m on 2 lanes of 8 m). A full
  vertical loop; the exit is shifted sideways (+ left) by offset so it clears the entry.
- corkscrew: length 20-260 (default: the shortest that works), turns 0.5-2 (1). The track climbs a few metres while
  level, rolls round its own axis (a helix round an axis 1 m above the deck, so above ~40 m/s speed presses cars in
  upside down), then comes back down: the climb keeps the rolling deck's lower edge above where it started, so it
  works at ground level. The roll is slow (about 70 m a turn): a wide deck twisting fast is steep away from its middle,
  and a deck wider than 11 m twists slower still (by the square root of 11 / its width). So with 8 m lanes one turn
  needs 110 m on 1 lane, 150 m on 2, 200 m on 3 and 250 m on 4 (climbs of 3.3, 7.4, 11.6 and 15.8 m); half a turn
  needs 35 to 60 m less. A wide, multi-lane corkscrew is long: narrow the track first (a lanes piece). Whole turns end level; a half turn leaves the track upside down. Where
  the deck is on its side or upside down its edges become 1 m rails. Cars without wall fans (below level 4) slide off.
- wallride: length 15-150 (default: what the lanes need, at least 40), side "left"/"right" (left). The track twists up
  to vertical on that side and back. It needs at least 4 x width + 6 m: with 8 m lanes 38 m for 1 lane, 70 m for 2, 102 m
  for 3, 134 m for 4 (the default is at least 40). The edges become 1 m rails while the deck is tilted. Cars without wall fans (below level 4) slide down it.
- lanes: lanes 1-4 (required), length 10-80 (25), align "center"/"left"/"right" (center: which edge stays put).
- split: length 15-80 (30), gate "lights"/"wall"/"none" (lights), merge_length 15-80 (30), merge_lanes 1-4 (default:
  the lanes before the split), branches: 2-4 of
    { "lanes": 1-4 (default the lanes at the split), "angle": -45..45 (+ left; default spread from +20 to -20),
      "laps": [1, 3] (default every lap), "pieces": [ ... ] }
- close: no settings. The last piece of a lap course: a generated connector back into the start piece.

SPLITS, LAPS AND ROUTING
- A split divides the track into 2-4 branches. Each branch has its own lead-in (length m long, curving off by its
  angle, the leftmost angle on the left), then its own pieces, which can include another split (3 levels deep).
- After the last piece of every branch the game generates smooth connectors into a merge, placed ahead of the
  farthest branch end along the branches' average heading. The merge then runs merge_length m and narrows or widens
  to merge_lanes, and the main track carries on. A connector can't be tighter than a 15 m radius or steeper than 35
  degrees: end the branches heading roughly the same way, at similar heights, not too far apart sideways, or the
  error names the branch that can't reach the merge.
- laps: on lap courses a branch can be open on some laps only. gate "lights" shows green/red signals over each
  branch, "wall" also raises a barrier across closed branches, "none" leaves every branch open (laps ignored).
  Every lap must have at least one open branch at every split. Branches spread at least 15-20 degrees apart (or
  turn away) so they're 3 m apart once past the lead-ins.
- close generates a connector from the end of the main line into the start piece: end the track a fair way behind
  the start (40 m or more), heading toward it, at about the start's height.

CHECKS (errors say where, with the JSON path, e.g. "pieces[6].branches[1].pieces[0] (curve): radius 4 is below the minimum 8")
- Up to 400 pieces in all (branches included), 32 checkpoints, splits 3 deep.
- The whole course inside the build area (get_player tells you the box).
- No two parts of the track closer than 3 m unless they're neighbours along it (a loop's exit beside its own entry is
  fine). To cross the track, go over or under it with 3 m or more between the decks (a car is 1.24 m tall).
- The deck must not sink into the ground; leave about 0.3 m under it or sit it on the ground.

TIPS
- Speed: the car tops out at 63 m/s (141 mph) on its motors and 103 m/s (230 mph) with boost. Gravity is 25.4 m/s^2.
- Loops: at the top the car needs v^2 / r > 25.4 m/s^2, and it loses speed climbing, so enter at about
  sqrt(130 x radius) m/s or more: radius 8 -> 32 m/s (72 mph), 10 -> 36 m/s (81 mph), 15 -> 44 m/s (99 mph),
  20 -> 51 m/s (114 mph). Put a 40 m+ straight and a booster before a loop and a straight after it.
- Corkscrews and wallrides are easiest at speed; cars without wall fans (below level 4) may slide off a wallride.
- Jumps: give them a straight approach, and pick the gap for the speed cars will have there (see jump above). A ramp
  up then a jump with a negative drop makes a big, slow jump.
- Bank fast curves 10-25 degrees. Radius 40+ m curves can be taken flat out; under 20 m cars must brake.
- Leave room for merges (they need 25-60 m past the branch ends) and for close (it needs to swing round: no
  tighter than a 15 m radius).
- Read the "ends" (where the next piece would start) after every change, and keep inside the build area.

EXAMPLE (a lap course on 8 m lanes, about 950 m: out along the start line, a U-turn, back through a split, a U-turn into the close)
{ "format": "skycity-course", "version": 2, "name": "Sky Loop", "author": "Sky City",
  "start": { "x": 0, "y": 0, "z": 0.3, "yaw": 0 },
  "lanes": 2, "lane_width": 8, "skin": "unveil", "laps": 3, "opponents": 3, "skill": 0.8, "catch_up": true,
  "pieces": [
    { "type": "start" },
    { "type": "straight", "length": 40 },
    { "type": "booster", "length": 12 },
    { "type": "loop", "radius": 10 },
    { "type": "straight", "length": 30 },
    { "type": "ramp", "length": 40, "rise": 8 },
    { "type": "straight", "length": 20 },
    { "type": "ramp", "length": 40, "rise": -8 },
    { "type": "straight", "length": 20 },
    { "type": "jump", "gap": 36, "drop": 0 },
    { "type": "straight", "length": 10 },
    { "type": "checkpoint" },
    { "type": "curve", "angle": 180, "radius": 31.5, "bank": 20 },
    { "type": "lanes", "lanes": 4, "length": 20, "align": "center" },
    { "type": "split", "length": 30, "gate": "lights", "merge_length": 25, "merge_lanes": 2,
      "branches": [
        { "lanes": 2, "angle": 12, "laps": [1, 3], "pieces": [ { "type": "corkscrew", "length": 150, "turns": 1 } ] },
        { "lanes": 2, "angle": -12, "laps": [2], "pieces": [ { "type": "wallride", "length": 70, "side": "right" },
                                                              { "type": "straight", "length": 80 } ] }
      ] },
    { "type": "checkpoint" },
    { "type": "straight", "length": 40 },
    { "type": "curve", "angle": 180, "radius": 40, "bank": 15 },
    { "type": "close" }
  ] }
Why it closes: the loop shifts the track 17 m left, the first U-turn (radius 31.5) moves it 63 m further left, and the
last U-turn (radius 40) brings it back 80 m, so the track ends on the start line, about 12 m behind the start piece,
heading the same way: close is then a short straight. Both branches are 150 m long, so the merge sits on the line
between them. Plan a lap course's lateral offsets like this so close has an easy job.
)GUIDE");
}
