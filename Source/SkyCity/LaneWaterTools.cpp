#include "LaneWaterTools.h"
#include "WaterBodyActor.h"
#include "WaterBodyComponent.h"
#include "WaterSplineMetadata.h"

int32 ULaneWaterTools::SetWaterBodyPointCurves(AActor* Actor, const TArray<float>& WidthsCm, const TArray<float>& DepthsCm,
	const TArray<float>& Velocities)
{
	AWaterBody* Body = Cast<AWaterBody>(Actor);
	if (!Body)
	{
		return -1;
	}
	UWaterSplineMetadata* Meta = Body->GetWaterSplineMetadata();
	if (!Meta)
	{
		return -2;
	}
	Meta->Modify();
	auto Fill = [](FInterpCurveFloat& Curve, const TArray<float>& Values)
	{
		for (int32 i = 0; i < Curve.Points.Num() && i < Values.Num(); ++i)
		{
			Curve.Points[i].OutVal = Values[i];
		}
	};
	Fill(Meta->RiverWidth, WidthsCm);
	Fill(Meta->Depth, DepthsCm);
	Fill(Meta->WaterVelocityScalar, Velocities);
	if (UWaterBodyComponent* Comp = Body->GetWaterBodyComponent())
	{
		FOnWaterBodyChangedParams Params;
		Params.bShapeOrPositionChanged = true;
		Params.bUserTriggered = true;
		Comp->OnWaterBodyChanged(Params);
	}
	return Meta->RiverWidth.Points.Num();
}
