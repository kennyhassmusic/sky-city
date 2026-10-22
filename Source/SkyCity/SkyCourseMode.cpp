// ASkyCourseMode and ASkyCourseBuilderPawn (see SkyCourse.h). STUB: to be written by the builder agent.
#include "SkyCourse.h"
#include "Camera/CameraComponent.h"
#include "EngineUtils.h"
#include "SkysterCar.h"

class FSkyCourseBuilderImpl {};

ASkyCourseMode::ASkyCourseMode() { PrimaryActorTick.bCanEverTick = true; }
void ASkyCourseMode::BeginPlay() { Super::BeginPlay(); }
void ASkyCourseMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TArray<TFunction<void()>> Work;
	{ FScopeLock L(&PendingLock); Work = MoveTemp(Pending); Pending.Reset(); }
	for (TFunction<void()>& W : Work) W();
}
void ASkyCourseMode::EndPlay(const EEndPlayReason::Type Reason) { Super::EndPlay(Reason); }
ASkyCourseMode* ASkyCourseMode::Get(const UWorld* World)
{
	if (!World) return nullptr;
	TActorIterator<ASkyCourseMode> It(const_cast<UWorld*>(World));
	return It ? *It : nullptr;
}
const FSkyBaked& ASkyCourseMode::GetBaked() const { static FSkyBaked Empty; return Track ? Track->GetBaked() : Empty; }
bool ASkyCourseMode::SetCourse(const FSkyCourse& NewCourse, TArray<FString>& Errors) { Course = NewCourse; return true; }
bool ASkyCourseMode::Edit(TFunctionRef<void(FSkyCourse&)> Change, TArray<FString>& Errors) { Change(Course); return true; }
bool ASkyCourseMode::Undo() { return false; }
TArray<FString> ASkyCourseMode::ListCourses() const { return {}; }
bool ASkyCourseMode::SaveCourse(const FString&, FString& Error) { Error = TEXT("not implemented yet"); return false; }
bool ASkyCourseMode::LoadCourse(const FString&, FString& Error) { Error = TEXT("not implemented yet"); return false; }
void ASkyCourseMode::StartTestDrive(int32) { bDriving = true; }
void ASkyCourseMode::StopTestDrive() { bDriving = false; }
ASkysterCar* ASkyCourseMode::GetCar() const { return nullptr; }
bool ASkyCourseMode::SetMcpEnabled(bool) { return false; }
bool ASkyCourseMode::IsMcpEnabled() const { return false; }
void ASkyCourseMode::RunOnGameThread(TFunction<void()> Work) { FScopeLock L(&PendingLock); Pending.Add(MoveTemp(Work)); }
void ASkyCourseMode::DrawHud(AHUD*, UCanvas*, float) {}

ASkyCourseBuilderPawn::ASkyCourseBuilderPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	RootComponent = Camera;
}
void ASkyCourseBuilderPawn::Tick(float DeltaSeconds) { Super::Tick(DeltaSeconds); }
void ASkyCourseBuilderPawn::DrawHud(AHUD*, UCanvas*, float) {}
