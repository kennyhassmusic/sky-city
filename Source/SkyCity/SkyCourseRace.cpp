// ASkyCourseRace (see SkyCourse.h). STUB: to be written by the race/AI agent.
#include "SkyCourse.h"
#include "SkysterCar.h"

class FSkyCourseRaceImpl {};
ASkyCourseRace::ASkyCourseRace() { PrimaryActorTick.bCanEverTick = true; }
void ASkyCourseRace::Tick(float DeltaSeconds) { Super::Tick(DeltaSeconds); }
void ASkyCourseRace::Begin(ASkyCourseTrack*, const FSkyCourse&, ASkysterCar*, int32, double) { bRunning = true; }
void ASkyCourseRace::End() { bRunning = false; }
TArray<ASkyCourseRace::FResult> ASkyCourseRace::GetResults() const { return {}; }
void ASkyCourseRace::DrawHud(AHUD*, UCanvas*, float) {}
