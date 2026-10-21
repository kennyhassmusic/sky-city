#include "SkysterPickups.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"

static UInstancedStaticMeshComponent* TaggedISM(AActor* A, const TCHAR* Tag)
{
	TArray<UInstancedStaticMeshComponent*> Comps;
	A->GetComponents(Comps);
	for (UInstancedStaticMeshComponent* C : Comps)
	{
		if (C->ComponentHasTag(Tag)) return C;
	}
	return nullptr;
}

void FSkyPickups::Gather(UWorld* World)
{
	Pads.Reset();
	PadSets.Reset();
	Bays.Reset();
	Crosses.Reset();
	AddonSpots.Reset();
	Lineups.Reset();
	Grid.Reset();
	if (!World) return;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* A = *It;
		const bool bSmall = A->ActorHasTag(TEXT("SC_PadSmall")), bBig = A->ActorHasTag(TEXT("SC_PadBig"));
		if (bSmall || bBig)
		{
			FPadSet S;
			S.Pool = TaggedISM(A, TEXT("Pool"));
			S.Ring = TaggedISM(A, TEXT("Ring"));
			S.Core = TaggedISM(A, TEXT("Core"));
			S.bBig = bBig;
			if (!S.Pool.IsValid()) continue;
			const int32 SetIdx = PadSets.Add(S);
			for (int32 i = 0; i < S.Pool->GetInstanceCount(); ++i)
			{
				FTransform X;
				S.Pool->GetInstanceTransform(i, X, true);
				FPad P;
				P.P = X.GetLocation();
				P.Yaw = X.Rotator().Yaw;
				P.bBig = bBig;
				P.Index = i;
				P.Set = SetIdx;
				const int32 Id = Pads.Add(P);
				Grid.FindOrAdd(Cell(P.P)).Add(Id);
			}
		}
		if (A->ActorHasTag(TEXT("SC_Chargers")))
		{
			BayComp = TaggedISM(A, TEXT("Bay"));
			CrossComp = TaggedISM(A, TEXT("Cross"));
			if (BayComp.IsValid())
			{
				for (int32 i = 0; i < BayComp->GetInstanceCount(); ++i)
				{
					FTransform X;
					BayComp->GetInstanceTransform(i, X, true);
					FBay B;
					B.P = X.GetLocation();
					B.Along = X.GetRotation().GetForwardVector().GetSafeNormal2D();
					B.Index = i;
					Bays.Add(B);
				}
			}
			if (CrossComp.IsValid())
			{
				for (int32 i = 0; i < CrossComp->GetInstanceCount(); ++i)
				{
					FTransform X;
					CrossComp->GetInstanceTransform(i, X, true);
					Crosses.Add(X.GetLocation());
				}
			}
		}
		if (A->ActorHasTag(TEXT("SC_Addon")))
		{
			TArray<USceneComponent*> Comps;
			A->GetComponents(Comps);
			for (USceneComponent* C : Comps)
			{
				for (const TCHAR* Id : { TEXT("nitrogen"), TEXT("combustion"), TEXT("rocket") })
				{
					if (C->ComponentHasTag(Id)) AddonSpots.Add({ Id, C->GetComponentLocation(), C });
				}
			}
		}
		if (A->ActorHasTag(TEXT("SC_Lineup")))
		{
			Lineups.Add(A->GetComponentsBoundingBox(true));
		}
	}
}

int32 FSkyPickups::CollectPad(const FVector& PosUE)
{
	const FIntPoint C0 = Cell(PosUE);
	for (int32 dx = -1; dx <= 1; ++dx)
	{
		for (int32 dy = -1; dy <= 1; ++dy)
		{
			const TArray<int32>* L = Grid.Find(FIntPoint(C0.X + dx, C0.Y + dy));
			if (!L) continue;
			for (int32 Id : *L)
			{
				FPad& P = Pads[Id];
				if (!P.bOn) continue;
				// RL pickup radii scaled to the car (js/world.js collectPad)
				const double R = P.bBig ? 500.0 : 320.0;
				if (FVector::DistSquared2D(P.P, PosUE) < R * R && FMath::Abs(P.P.Z - PosUE.Z) < 250.0)
				{
					P.bOn = false;
					P.T = P.bBig ? 10.0 : 4.0;
					PlacePad(P, 0, false);
					return P.bBig ? 2 : 1;
				}
			}
		}
	}
	return 0;
}

bool FSkyPickups::ChargerAt(const FVector& PosUE, double Now)
{
	for (FBay& B : Bays)
	{
		const FVector D = PosUE - B.P;
		if (FMath::Abs(D.Z) > 150.0) continue;
		const double Along = FVector::DotProduct(FVector(D.X, D.Y, 0), B.Along);
		const FVector Side(-B.Along.Y, B.Along.X, 0);
		const double Across = FVector::DotProduct(FVector(D.X, D.Y, 0), Side);
		// bay 3 m x 6 m on a 6.5 m pitch, with js's give: 2.3 m across, half a pitch plus 0.25 m along
		if (FMath::Abs(Across) < 230.0 && FMath::Abs(Along) < 350.0)
		{
			for (FBay& O : Bays)
			{
				if (FVector::DistSquared(O.P, B.P) < 1100.0 * 1100.0) O.LastBusy = Now;
			}
			return true;
		}
	}
	return false;
}

FString FSkyPickups::CollectAddon(const FVector& PosUE, const TSet<FString>& Owned)
{
	for (const FAddonSpot& S : AddonSpots)
	{
		if (Owned.Contains(S.Id)) continue;
		if (FVector::DistSquared2D(S.P, PosUE) < 450.0 * 450.0 && FMath::Abs(S.P.Z - PosUE.Z) < 350.0) return S.Id;
	}
	return FString();
}

void FSkyPickups::HideOwned(const TSet<FString>& Owned)
{
	for (const FAddonSpot& S : AddonSpots)
	{
		if (USceneComponent* C = S.Comp.Get()) C->SetVisibility(!Owned.Contains(S.Id), true);
	}
}

bool FSkyPickups::OverLineup(const FVector& PosUE) const
{
	for (const FBox& B : Lineups)
	{
		if (PosUE.X > B.Min.X && PosUE.X < B.Max.X && PosUE.Y > B.Min.Y && PosUE.Y < B.Max.Y && PosUE.Z > B.Max.Z + 100.0 && PosUE.Z < B.Max.Z + 1800.0) return true;
	}
	return false;
}

void FSkyPickups::PlacePad(const FPad& Pad, double Now, bool bAnimate)
{
	const FPadSet& S = PadSets[Pad.Set];
	const double K = Pad.bOn ? 1.0 : 0.0001;
	const double Bob = Pad.bOn && bAnimate ? FMath::Sin(Now * 2 + Pad.P.X * 0.003) * 8.0 : 0.0;
	const FVector Hover = Pad.P + FVector(0, 0, 75.0 + Bob);
	const FQuat Spin(FVector::UpVector, Now * (Pad.bBig ? 0.9 : 2.2) + Pad.P.X * 0.01);
	if (UInstancedStaticMeshComponent* R = S.Ring.Get())
	{
		R->UpdateInstanceTransform(Pad.Index, FTransform(Spin, Hover, FVector(K)), true, false, true);
		Dirty.Add(R);
	}
	if (UInstancedStaticMeshComponent* C = S.Core.Get())
	{
		const double Pulse = bAnimate ? 0.8 + 0.2 * FMath::Sin(Now * 6 + Pad.P.Y * 0.01) : 1.0;
		C->UpdateInstanceTransform(Pad.Index, FTransform(Spin, Hover, FVector(K * Pulse, K, K)), true, false, true);
		Dirty.Add(C);
	}
	if (UInstancedStaticMeshComponent* P = S.Pool.Get())
	{
		P->UpdateInstanceTransform(Pad.Index, FTransform(FRotator(0, Pad.Yaw, 0), Pad.P, FVector(K)), true, false, true);
		Dirty.Add(P);
	}
}

void FSkyPickups::Update(double Dt, double Now, const FVector& CarUE)
{
	for (FPad& P : Pads)
	{
		if (!P.bOn && (P.T -= Dt) <= 0)
		{
			P.bOn = true;
			PlacePad(P, Now, false);
		}
	}
	// spin and bob the ones near the car (instance updates cost, and nobody sees the far ones move)
	const FIntPoint C0 = Cell(CarUE);
	for (int32 dx = -3; dx <= 3; ++dx)
	{
		for (int32 dy = -3; dy <= 3; ++dy)
		{
			if (const TArray<int32>* L = Grid.Find(FIntPoint(C0.X + dx, C0.Y + dy)))
			{
				for (int32 Id : *L) if (Pads[Id].bOn) PlacePad(Pads[Id], Now, true);
			}
		}
	}
	// Fast chargers: always open; while a car charges the site's bays pulse green and its cross spins fast
	if (UInstancedStaticMeshComponent* B = BayComp.Get())
	{
		if (B->NumCustomDataFloats > 0)
		{
			for (const FBay& Bay : Bays)
			{
				const bool bBusy = Now - Bay.LastBusy < 0.25;
				const float V = bBusy ? 0.75f + 0.25f * FMath::Sin(Now * 8) : 0.f;
				B->SetCustomDataValue(Bay.Index, 0, V, false);
			}
			Dirty.Add(B);
		}
	}
	if (UInstancedStaticMeshComponent* X = CrossComp.Get())
	{
		for (int32 i = 0; i < Crosses.Num(); ++i)
		{
			if (FVector::DistSquared2D(Crosses[i], CarUE) > 30000.0 * 30000.0) continue;
			bool bBusy = false;
			for (const FBay& Bay : Bays) if (Now - Bay.LastBusy < 0.25 && FVector::DistSquared2D(Bay.P, Crosses[i]) < 1200.0 * 1200.0) { bBusy = true; break; }
			const FQuat Spin(FVector::UpVector, Now * (bBusy ? 6.0 : 1.5) + i);
			X->UpdateInstanceTransform(i, FTransform(Spin, Crosses[i] + FVector(0, 0, FMath::Sin(Now * 2.5 + i) * 12.0)), true, false, true);
		}
		Dirty.Add(X);
	}
	for (UInstancedStaticMeshComponent* C : Dirty) if (IsValid(C)) C->MarkRenderStateDirty();
	Dirty.Reset();
}

bool FSkyPickups::NearestRoad(const FVector& PosUE, FVector& OutUE, double& OutYawDeg) const
{
	double BestD = TNumericLimits<double>::Max();
	for (const FPad& P : Pads)
	{
		if (P.bBig) continue;
		const double D = FVector::DistSquared(P.P, PosUE);
		if (D < BestD) { BestD = D; OutUE = P.P; OutYawDeg = P.Yaw; }
	}
	return BestD < TNumericLimits<double>::Max();
}
