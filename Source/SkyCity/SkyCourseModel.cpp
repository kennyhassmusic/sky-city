// The course file and the bake (see SkyCourse.h). STUB: to be written by the course-geometry agent.
#include "SkyCourse.h"
#include "Engine/World.h"
#include "Misc/Paths.h"

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

static const TCHAR* GPieceNames[] = { TEXT("start"), TEXT("finish"), TEXT("checkpoint"), TEXT("straight"), TEXT("curve"), TEXT("ramp"), TEXT("jump"),
	TEXT("loop"), TEXT("corkscrew"), TEXT("wallride"), TEXT("booster"), TEXT("lanes"), TEXT("split"), TEXT("close") };
static_assert(UE_ARRAY_COUNT(GPieceNames) == (int32)ESkyPiece::Count, "piece names");
const TCHAR* SkyCourse::PieceName(ESkyPiece T) { return (int32)T < (int32)ESkyPiece::Count ? GPieceNames[(int32)T] : TEXT("?"); }
ESkyPiece SkyCourse::PieceFromName(const FString& N)
{
	for (int32 i = 0; i < (int32)ESkyPiece::Count; ++i) if (N.Equals(GPieceNames[i], ESearchCase::IgnoreCase)) return (ESkyPiece)i;
	return ESkyPiece::Count;
}
const TCHAR* SkyCourse::SkinName(ESkySkin S) { return S == ESkySkin::Classic ? TEXT("classic") : S == ESkySkin::Neon ? TEXT("neon") : TEXT("unveil"); }

bool SkyCourse::Parse(const FString&, FSkyCourse&, TArray<FString>& Errors) { Errors.Add(TEXT("not implemented yet")); return false; }
FString SkyCourse::Write(const FSkyCourse&) { return TEXT("{}"); }
bool SkyCourse::ParsePiece(const TSharedPtr<FJsonObject>&, FSkyCourse&, FSkyPiece&, const FString&, TArray<FString>& Errors) { Errors.Add(TEXT("not implemented yet")); return false; }
TSharedPtr<FJsonObject> SkyCourse::PieceToJson(const FSkyCourse&, const FSkyPiece&) { return nullptr; }
void SkyCourse::Bake(const FSkyCourse&, const FBox&, FSkyBaked& Out) { Out = FSkyBaked(); Out.Errors.Add(TEXT("not implemented yet")); }
FSkyFrame SkyCourse::EndOf(const FSkyBaked& Baked, const FSkyCourse&, int32, int32* OutLanes) { if (OutLanes) *OutLanes = DefaultLanes; return Baked.End; }
TArray<int32> SkyCourse::Route(const FSkyBaked&, int32, const TArray<int32>&) { return {}; }
FSkyPiece SkyCourse::DefaultPiece(ESkyPiece Type, int32) { FSkyPiece P; P.Type = Type; return P; }
FString SkyCourse::Guide() { return TEXT("not implemented yet"); }
FSkyCourse SkyCourse::Example(const FVector& Start, double Yaw) { FSkyCourse C; C.Start = Start; C.Yaw = Yaw; return C; }
