// ASkyCourseTrack (see SkyCourse.h). STUB: to be written by the course-geometry agent.
#include "SkyCourse.h"
#include "ProceduralMeshComponent.h"

ASkyCourseTrack::ASkyCourseTrack() { PrimaryActorTick.bCanEverTick = false; RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root")); }
const FSkyBaked& ASkyCourseTrack::Build(const FSkyCourse& Course, const FBox& BuildArea) { SkyCourse::Bake(Course, BuildArea, Baked); return Baked; }
void ASkyCourseTrack::SetBranchOpen(int32, int32, bool) {}
void ASkyCourseTrack::ShowPreview(const FSkyPiece*, const FSkyFrame&, int32, bool) {}
void ASkyCourseTrack::Highlight(int32) {}
void ASkyCourseTrack::UpdateGlow(const TArray<FVector>&, float) {}
void ASkyCourseTrack::Clear() {}
