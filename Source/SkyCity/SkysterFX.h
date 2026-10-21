// Skyster's soft particles (js/fx.js Particles), drawn as camera-facing quads through one instanced mesh per pool:
// cold-gas vapour, tyre smoke, dust and damage smoke (lit, translucent), fire and sparks (additive).
// Units are Unreal's: cm, cm/s; Grav in cm/s^2 (negative rises, like smoke). Each instance carries its colour, alpha
// and age (0-1, which picks the frame of the smoke flipbook) in five custom data floats for the material.
// A particle given a floor (world Z) lands on it and rolls outward along the ground, like the thruster smoke in the
// reveal photos.
#pragma once

#include "CoreMinimal.h"

class UInstancedStaticMeshComponent;

struct FSkyPool
{
	struct FPart
	{
		FVector P, V;
		FLinearColor C;
		float Life, MaxLife, Size, Grow, A, Drag, Grav, Roll, Spin, Floor, Phase;
		FVector2f Out;  // the way it spreads when it lands
		bool bLanded;
	};

	/** Sizes the pool and parks every instance (zero scale) so the instance count never changes. bUpright keeps sprites
	 *  near upright (the smoke flipbook carries light from above), else they spin freely. */
	void Init(UInstancedStaticMeshComponent* InIsm, int32 InMax, bool bInSort, bool bInStretch, bool bInUpright = false);
	void Emit(const FVector& P, const FVector& V, float Life, float Size, float Grow, const FLinearColor& C, float A, float Drag = 1.f, float Grav = 0.f, float Floor = -1e9f);
	/** Ages and moves the particles, then writes them to the instances facing the camera (far ones first when sorted). */
	void Update(float Dt, const FVector& Cam);
	void Clear() { Parts.Reset(); }
	int32 Num() const { return Parts.Num(); }

private:
	UInstancedStaticMeshComponent* Ism = nullptr; // owned by the car as a component
	TArray<FPart> Parts;
	TArray<FTransform> Xfs;
	TArray<float> Data;
	TArray<int32> Order;
	FRandomStream Rand{ 1234 };
	int32 Max = 0, LastN = 0;
	bool bSort = false, bStretch = false, bUpright = false;
};
