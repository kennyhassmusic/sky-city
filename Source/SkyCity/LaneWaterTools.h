// Lane 9 (water A/B test, gen/water-plugin only): set a Water plugin body's per-point spline curves (river width,
// depth, velocity) from Python. UWaterSplineMetadata isn't reachable from Python in UE 5.8.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "LaneWaterTools.generated.h"

UCLASS()
class ULaneWaterTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Width (cm, full width), depth (cm) and velocity scalar per spline point. Returns the point count, or < 0. */
	UFUNCTION(BlueprintCallable, Category = "Lane9|Water")
	static int32 SetWaterBodyPointCurves(AActor* WaterBody, const TArray<float>& WidthsCm, const TArray<float>& DepthsCm,
		const TArray<float>& Velocities);
};
