#include "SkysterFX.h"

#include "Components/InstancedStaticMeshComponent.h"

// the quad is Unreal's /Engine/BasicShapes/Plane: 100 cm square in XY, facing +Z
static constexpr float QUAD = 100.f;

void FSkyPool::Init(UInstancedStaticMeshComponent* InIsm, int32 InMax, bool bInSort, bool bInStretch, bool bInUpright)
{
	Ism = InIsm;
	Max = InMax;
	bSort = bInSort;
	bStretch = bInStretch;
	bUpright = bInUpright;
	Parts.Reset();
	Parts.Reserve(Max);
	if (!Ism) return;
	Ism->ClearInstances();
	Ism->SetNumCustomDataFloats(5);
	TArray<FTransform> Parked;
	Parked.Init(FTransform(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector), Max);
	Ism->AddInstances(Parked, false, true);
}

void FSkyPool::Emit(const FVector& P, const FVector& V, float Life, float Size, float Grow, const FLinearColor& C, float A, float Drag, float Grav, float Floor)
{
	if (Max <= 0) return;
	// a full pool overwrites a random particle, like js
	FPart& N = Parts.Num() < Max ? Parts.AddDefaulted_GetRef() : Parts[Rand.RandHelper(Max)];
	N.P = P;
	N.V = V;
	N.C = C;
	N.Life = 0;
	N.MaxLife = FMath::Max(Life, 0.01f);
	N.Size = Size;
	N.Grow = Grow;
	N.A = A;
	N.Drag = Drag;
	N.Grav = Grav;
	N.Roll = bUpright ? Rand.FRandRange(-0.45f, 0.45f) : Rand.FRandRange(0.f, 2 * PI);
	N.Spin = bUpright ? Rand.FRandRange(-0.25f, 0.25f) : Rand.FRandRange(-0.8f, 0.8f);
	N.Floor = Floor;
	N.Phase = Rand.FRandRange(0.f, 0.15f);
	const float A2 = Rand.FRandRange(0.f, 2 * PI);
	N.Out = FVector2f(FMath::Cos(A2), FMath::Sin(A2));
	N.bLanded = false;
}

void FSkyPool::Update(float Dt, const FVector& Cam)
{
	if (!Ism) return;
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		FPart& Pt = Parts[i];
		Pt.Life += Dt;
		if (Pt.Life >= Pt.MaxLife)
		{
			Parts.RemoveAtSwap(i--, EAllowShrinking::No);
			continue;
		}
		const float K = FMath::Exp(-Pt.Drag * Dt);
		Pt.V *= K;
		Pt.V.Z -= Pt.Grav * Dt;
		Pt.P += Pt.V * Dt;
		if (Pt.P.Z < Pt.Floor)
		{
			// lands: the fall turns into a roll outward along the ground (away from where it came down), slowly rising
			Pt.P.Z = Pt.Floor;
			const FVector2f H(Pt.V.X, Pt.V.Y);
			const float Fall = FMath::Abs((float)Pt.V.Z);
			const FVector2f Dir = H.SizeSquared() > 400.f ? (H.GetSafeNormal() * 0.4f + Pt.Out * 0.6f).GetSafeNormal() : Pt.Out;
			Pt.V.X += Dir.X * Fall * 0.7f;
			Pt.V.Y += Dir.Y * Fall * 0.7f;
			Pt.V.Z = 25.f;
			if (!Pt.bLanded)
			{
				Pt.bLanded = true;
				Pt.Grow *= 1.6f;
				Pt.Drag = FMath::Min(Pt.Drag, 0.9f);
				Pt.Grav = FMath::Min(Pt.Grav, -15.f);
			}
		}
		Pt.Size = FMath::Min(Pt.Size + Pt.Grow * Dt, 900.f); // big clouds are built from many sprites, not giant ones
		Pt.Roll += Pt.Spin * Dt;
	}
	const int32 N = Parts.Num();
	if (N == 0 && LastN == 0) return; // nothing drawn, nothing to clear
	LastN = N;
	Order.SetNum(N);
	for (int32 i = 0; i < N; ++i) Order[i] = i;
	if (bSort)
	{
		Order.Sort([this, &Cam](int32 A, int32 B) { return FVector::DistSquared(Parts[A].P, Cam) > FVector::DistSquared(Parts[B].P, Cam); });
	}
	// every instance is rewritten each frame, unused ones parked at the camera with no size, so the bounds stay tight
	const int32 Count = Max;
	if (Count == 0) return;
	Xfs.SetNum(Count);
	Data.SetNumUninitialized(Count * 5);
	for (int32 j = 0; j < Count; ++j)
	{
		if (j >= N)
		{
			Xfs[j] = FTransform(FQuat::Identity, Cam, FVector::ZeroVector);
			Data[j * 5] = Data[j * 5 + 1] = Data[j * 5 + 2] = Data[j * 5 + 3] = Data[j * 5 + 4] = 0.f;
			continue;
		}
		const FPart& Pt = Parts[Order[j]];
		const FVector Z = (Cam - Pt.P).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
		FVector X;
		float Sx = Pt.Size / QUAD, Sy = Sx;
		const FVector Vp = Pt.V - (Pt.V | Z) * Z;
		const double Vs = Vp.Size();
		if (bStretch && Vs > 50.0)
		{
			// sparks: streaks along their motion on screen, about 25 ms of travel long
			X = Vp / Vs;
			Sx = (Pt.Size + (float)Vs * 0.025f) / QUAD;
		}
		else
		{
			FVector R = FVector::CrossProduct(FVector::UpVector, Z);
			if (!R.Normalize()) R = FVector::ForwardVector;
			const FVector U = FVector::CrossProduct(Z, R);
			X = R * FMath::Cos(Pt.Roll) + U * FMath::Sin(Pt.Roll);
		}
		const float T = Pt.Life / Pt.MaxLife;
		Xfs[j] = FTransform(FRotationMatrix::MakeFromZX(Z, X).ToQuat(), Pt.P, FVector(Sx, Sy, 1.f));
		Data[j * 5] = Pt.C.R;
		Data[j * 5 + 1] = Pt.C.G;
		Data[j * 5 + 2] = Pt.C.B;
		// the smoke flipbook thins out by itself, so smoke holds its density longer than js's (1 - t)^2
		Data[j * 5 + 3] = Pt.A * (bUpright ? 1 - T * T * T : (1 - T) * (1 - T));
		Data[j * 5 + 4] = FMath::Min(1.f, T * 0.85f + Pt.Phase);
	}
	Ism->BatchUpdateInstancesTransforms(0, Xfs, true, false, true);
	Ism->SetCustomData(0, Count - 1, Data, false);
}
