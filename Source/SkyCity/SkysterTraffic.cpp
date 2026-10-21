#include "SkysterTraffic.h"

#include "Algo/BinarySearch.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Math/Box2D.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SkysterCar.h"
#include "SkysterFleet.h"

bool ASkysterTraffic::GGround = true;
bool ASkysterTraffic::GSky = false;

namespace
{
	constexpr int32 CAB = 3;                                    // SkyFleet::Cars index of the Cybercab
	constexpr double SKY_LANE = 1.3;                            // sky lanes are spread wider than the street's
	constexpr double ACC = 1.8, DEC = 3.0;                      // m/s^2: comfortable, the way people drive in town
	constexpr double LC_LEN = 30.0;                             // a lane change takes 30 m
	constexpr double JAM = 2.0;                                 // bumper gap kept when stopped behind a car, m
	constexpr double SHELL = 0.15;                              // the last-resort check keeps bodies this far apart, m
	constexpr double MARGIN = 0.45;                             // crossing paths closer than their half widths + this conflict, m
	constexpr double LOOK = 60.0;                               // following looks this far into the next link, m
	constexpr double REQ_AFTER = 10.0;                          // s of waiting at a junction before a car queues a request
	constexpr double CELL = 16.0;                               // the body grid's cells, m
	constexpr double FADE_T = 0.4;                              // s to shrink away before reappearing elsewhere

	// why a car is held (FCar::Why)
	enum EWhy : uint8 { W_None, W_Signal, W_Stop, W_Car, W_Cross, W_Yield, W_Conflict, W_Exit, W_Hold, W_Player, W_Lane };

	FVector UEOf(const FVector2D& P, double Z) { return FVector(P.Y * 100.0, P.X * 100.0, Z); }
	double YawOf(const FVector2D& D) { return FMath::RadiansToDegrees(FMath::Atan2(D.X, D.Y)); }
	FVector2D Right(const FVector2D& T) { return FVector2D(T.Y, -T.X); }
	double Cross2(const FVector2D& A, const FVector2D& B) { return A.X * B.Y - A.Y * B.X; }

	FVector2D Bez(const FVector2D& A, const FVector2D& B, const FVector2D& C, double U, FVector2D* Dir)
	{
		const double V = 1.0 - U;
		if (Dir) *Dir = (2.0 * V * (B - A) + 2.0 * U * (C - B)).GetSafeNormal();
		return A * (V * V) + B * (2.0 * V * U) + C * (U * U);
	}

	// how far two boxes (centre, unit heading, half length, half width) overlap: the smallest overlap over the
	// separating axes; <= 0 means apart
	double ObbDepth(const FVector2D& P1, const FVector2D& D1, double HL1, double HW1, const FVector2D& P2, const FVector2D& D2, double HL2, double HW2)
	{
		const FVector2D N1(-D1.Y, D1.X), N2(-D2.Y, D2.X);
		const FVector2D Axes[4] = { D1, N1, D2, N2 };
		const FVector2D Dp = P2 - P1;
		double Best = 1e9;
		for (const FVector2D& A : Axes)
		{
			const double R1 = HL1 * FMath::Abs(FVector2D::DotProduct(D1, A)) + HW1 * FMath::Abs(FVector2D::DotProduct(N1, A));
			const double R2 = HL2 * FMath::Abs(FVector2D::DotProduct(D2, A)) + HW2 * FMath::Abs(FVector2D::DotProduct(N2, A));
			Best = FMath::Min(Best, R1 + R2 - FMath::Abs(FVector2D::DotProduct(Dp, A)));
			if (Best <= 0) return Best;
		}
		return Best;
	}

	double PtSeg(const FVector2D& X, const FVector2D& A, const FVector2D& B)
	{
		const FVector2D AB = B - A;
		const double L2 = AB.SizeSquared();
		const double T = L2 < 1e-12 ? 0.0 : FMath::Clamp(FVector2D::DotProduct(X - A, AB) / L2, 0.0, 1.0);
		return FVector2D::Distance(X, A + AB * T);
	}

	double SegSeg(const FVector2D& P, const FVector2D& Q, const FVector2D& A, const FVector2D& B)
	{
		const double O1 = Cross2(Q - P, A - P), O2 = Cross2(Q - P, B - P), O3 = Cross2(B - A, P - A), O4 = Cross2(B - A, Q - A);
		if (O1 * O2 < 0 && O3 * O4 < 0) return 0.0;
		return FMath::Min(FMath::Min(PtSeg(P, A, B), PtSeg(Q, A, B)), FMath::Min(PtSeg(A, P, Q), PtSeg(B, P, Q)));
	}

	// do two polylines come closer than Lim?
	template <typename TA, typename TB>
	bool PolyClose(const TA& A, const TB& B, double Lim)
	{
		if (A.Num() < 2 || B.Num() < 2) return false;
		FBox2D BA(ForceInit), BB(ForceInit);
		for (const FVector2D& P : A) BA += P;
		for (const FVector2D& P : B) BB += P;
		if (!BA.ExpandBy(Lim).Intersect(BB)) return false;
		for (int32 i = 0; i + 1 < A.Num(); ++i)
		{
			for (int32 j = 0; j + 1 < B.Num(); ++j)
			{
				if (SegSeg(A[i], A[i + 1], B[j], B[j + 1]) < Lim) return true;
			}
		}
		return false;
	}

	template <typename TA>
	bool PolySegClose(const TA& A, const FVector2D& P, const FVector2D& Q, double Lim)
	{
		for (int32 i = 0; i + 1 < A.Num(); ++i)
		{
			if (SegSeg(A[i], A[i + 1], P, Q) < Lim) return true;
		}
		return false;
	}
}

ASkysterTraffic::ASkysterTraffic()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostPhysics;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SkyHeads = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("SkyHeads"));
	SkyHeads->SetupAttachment(RootComponent);
	SkyHeads->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SkyHeads->SetCastShadow(false);
	SkyStops = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("SkyStops"));
	SkyStops->SetupAttachment(RootComponent);
	SkyStops->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SkyStops->SetCastShadow(false);
	// the hit boxes are solid, but the Roadster bounces off traffic instead of driving up it (ASkysterCar::Collide)
	Tags.Add(TEXT("NoWallRide"));
}

void ASkysterTraffic::BeginPlay()
{
	Super::BeginPlay();
	if (!Load())
	{
		UE_LOG(LogTemp, Warning, TEXT("SkysterTraffic: no Content/SkyCity/Data/traffic.json, no traffic"));
		SetActorTickEnabled(false);
		return;
	}
	for (const SkyFleet::FCar& M : SkyFleet::Cars)
	{
		BodyMeshes.Add(LoadObject<UStaticMesh>(nullptr, *SkyFleet::MeshPath(M.Name, TEXT("Body"))));
		for (int32 w = 0; w < 6; ++w) WheelMeshes.Add(w < M.NumWheels ? LoadObject<UStaticMesh>(nullptr, *SkyFleet::MeshPath(M.Name, M.W[w].Part)) : nullptr);
	}
	OnLink.SetNum(Links.Num());
	BuildSigns();
	bPending = true;                                         // populated on the first tick, once the camera is where you are
}

bool ASkysterTraffic::Load()
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir() / TEXT("SkyCity/Data/traffic.json")))) return false;
	TSharedPtr<FJsonObject> Root;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid()) return false;
	GroupTime = Root->GetNumberField(TEXT("group_time"));
	for (const auto& KV : Root->GetObjectField(TEXT("nodes"))->Values)
	{
		const TArray<TSharedPtr<FJsonValue>>& A = KV.Value->AsArray();
		Nodes.Add(FCString::Atoi(*KV.Key), FVector2D(A[0]->AsNumber(), A[1]->AsNumber()));
	}
	for (const auto& KV : Root->GetObjectField(TEXT("units"))->Values)
	{
		const TArray<TSharedPtr<FJsonValue>>& A = KV.Value->AsArray();
		Units.Add(FCString::Atoi(*KV.Key), TPair<int32, double>((int32)A[0]->AsNumber(), A[1]->AsNumber()));
	}
	TMultiMap<int32, int32> From;
	for (const TSharedPtr<FJsonValue>& V : Root->GetArrayField(TEXT("links")))
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FLink L;
		L.A = (int32)O->GetNumberField(TEXT("a"));
		L.B = (int32)O->GetNumberField(TEXT("b"));
		L.V = O->GetNumberField(TEXT("v"));
		L.Ctrl = (int32)O->GetNumberField(TEXT("c"));
		L.Unit = (int32)O->GetNumberField(TEXT("u"));
		L.Group = (int32)O->GetNumberField(TEXT("g"));
		L.bHw = O->GetBoolField(TEXT("hw"));
		O->TryGetStringField(TEXT("n"), L.Name);
		for (const TSharedPtr<FJsonValue>& P : O->GetArrayField(TEXT("p")))
		{
			const TArray<TSharedPtr<FJsonValue>>& A = P->AsArray();
			L.P.Add(FVector2D(A[0]->AsNumber(), A[1]->AsNumber()));
		}
		for (const TSharedPtr<FJsonValue>& X : O->GetArrayField(TEXT("o"))) L.O.Add(X->AsNumber());
		if (L.P.Num() < 2 || L.O.Num() == 0) continue;
		L.S.Add(0.0);
		for (int32 i = 1; i < L.P.Num(); ++i) L.S.Add(L.S.Last() + FVector2D::Distance(L.P[i - 1], L.P[i]));
		L.Len = L.S.Last();
		if (L.Len < 1.0) continue;
		L.Mid = At(L, L.Len * 0.5, 0.0);
		From.Add(L.A, Links.Num());
		Links.Add(MoveTemp(L));
	}
	for (FLink& L : Links)
	{
		TArray<int32> Out;
		From.MultiFind(L.B, Out);
		for (int32 j : Out)
		{
			if (!(Links[j].B == L.A && Links[j].A == L.B)) L.Next.Add(j);
		}
		if (L.Next.Num() == 0) L.Next = Out;                     // a dead end: turn round
	}
	for (int32 i = 0; i < Links.Num(); ++i)
	{
		NodeIn.FindOrAdd(Links[i].B).Add(i);
		NodeOut.FindOrAdd(Links[i].A).Add(i);
	}
	SanitizeLanes();
	BoxExtents();
	UE_LOG(LogTemp, Display, TEXT("SkysterTraffic: %d links, %d signalised units, %d lanes dropped (inside an opposite lane)"), Links.Num(), Units.Num(), LanesDropped);
	return Links.Num() > 0;
}

// traffic.json has a few carriageways whose lanes run inside the opposite direction's lanes (less than a car's width
// apart for 6 m or more): cars there would meet head on. Such a lane is dropped from the link that can spare one.
void ASkysterTraffic::SanitizeLanes()
{
	struct FSamp { int32 L, Lane; FVector2D Q, T; };
	TArray<FSamp> Samp;
	TMap<int64, TArray<int32>> G;
	constexpr double Step = 3.0, C = 4.0;
	const auto Key = [](int32 X, int32 Y) { return ((int64)X << 32) ^ (int64)(uint32)Y; };
	for (int32 i = 0; i < Links.Num(); ++i)
	{
		const FLink& L = Links[i];
		const int32 N = FMath::Max(2, (int32)(L.Len / Step));
		for (int32 k = 0; k <= N; ++k)
		{
			const double S = L.Len * k / N;
			if (S < 3.0 || S > L.Len - 3.0) continue;
			FVector2D T;
			const FVector2D P = At(L, S, 0.0, &T);
			for (int32 j = 0; j < L.O.Num(); ++j)
			{
				const FVector2D Q = P + Right(T) * L.O[j];
				G.FindOrAdd(Key(FMath::FloorToInt32(Q.X / C), FMath::FloorToInt32(Q.Y / C))).Add(Samp.Num());
				Samp.Add({ i, j, Q, T });
			}
		}
	}
	TMap<uint64, int32> Hits;
	TArray<uint64> Order;
	for (const FSamp& A : Samp)
	{
		const int32 GX = FMath::FloorToInt32(A.Q.X / C), GY = FMath::FloorToInt32(A.Q.Y / C);
		for (int32 dx = -1; dx <= 1; ++dx)
		{
			for (int32 dy = -1; dy <= 1; ++dy)
			{
				const TArray<int32>* Cell = G.Find(Key(GX + dx, GY + dy));
				if (!Cell) continue;
				for (int32 o : *Cell)
				{
					const FSamp& B = Samp[o];
					if (B.L == A.L || FVector2D::DotProduct(A.T, B.T) > -0.7 || FVector2D::DistSquared(A.Q, B.Q) >= 2.4 * 2.4) continue;
					const uint64 K = ((uint64)(uint32)(A.L * 8 + A.Lane) << 32) | (uint64)(uint32)(B.L * 8 + B.Lane);
					int32& H = Hits.FindOrAdd(K);
					if (H++ == 0) Order.Add(K);
				}
			}
		}
	}
	TMap<int32, TSet<int32>> Drop;
	for (const uint64 K : Order)
	{
		if (Hits[K] * Step < 6.0) continue;
		const int32 KA = (int32)(uint32)(K >> 32), KB = (int32)(uint32)K;
		const int32 LA = KA / 8, NA = KA % 8, LB = KB / 8, NB = KB % 8;
		const int32 SpareA = Links[LA].O.Num() - Drop.FindOrAdd(LA).Num();
		const int32 SpareB = Links[LB].O.Num() - Drop.FindOrAdd(LB).Num();
		if (SpareA >= 2 && (Links[LA].O.Num() >= Links[LB].O.Num() || SpareB < 2)) Drop[LA].Add(NA);
		else if (SpareB >= 2) Drop[LB].Add(NB);
	}
	for (TPair<int32, TSet<int32>>& D : Drop)
	{
		if (D.Value.Num() == 0) continue;
		FLink& L = Links[D.Key];
		TArray<double> Keep;
		for (int32 j = 0; j < L.O.Num(); ++j) if (!D.Value.Contains(j)) Keep.Add(L.O[j]);
		if (Keep.Num() == 0) continue;
		LanesDropped += L.O.Num() - Keep.Num();
		L.O = MoveTemp(Keep);
	}
}

// Where the junction box is along each link: many links end (or start) at the node itself, in the middle of the
// junction, rather than at its mouth. The box reaches as far along the link as the other legs' lanes do.
void ASkysterTraffic::BoxExtents()
{
	const auto LanePts = [this](const FLink& M, bool bEnd, TArray<FVector2D>& Out)
	{
		FVector2D T;
		const FVector2D P = At(M, bEnd ? M.Len : 0.0, 0.0, &T);
		const FVector2D R = Right(T);
		for (double O : M.O) Out.Add(P + R * O);
		Out.Add(P + R * (M.O[0] - 1.8));
		Out.Add(P + R * (M.O.Last() + 1.8));
	};
	for (FLink& L : Links)
	{
		L.SB = L.Ctrl != 0 ? 4.0 : 1.0;                          // the stop bar sits ~4 m before a controlled mouth
		L.EX = 0.0;
	}
	TArray<FVector2D> Pts;
	for (int32 i = 0; i < Links.Num(); ++i)
	{
		FLink& L = Links[i];
		if (const FVector2D* N = Nodes.Find(L.B))
		{
			FVector2D T;
			const FVector2D E = At(L, L.Len, 0.0, &T);
			Pts.Reset();
			if (const TArray<int32>* In = NodeIn.Find(L.B)) for (int32 j : *In) if (j != i) LanePts(Links[j], true, Pts);
			if (const TArray<int32>* Out = NodeOut.Find(L.B))
			{
				for (int32 j : *Out)
				{
					const FLink& M = Links[j];
					if (!(M.B == L.A && M.A == L.B)) LanePts(M, false, Pts);
				}
			}
			if (Pts.Num())
			{
				double MinP = 1e9;
				for (const FVector2D& Q : Pts) MinP = FMath::Min(MinP, FVector2D::DotProduct(Q - *N, T));
				const double Extra = FMath::Min(15.0, FMath::Max(0.0, FMath::Max(0.0, -MinP) - FVector2D::Distance(E, *N)));
				L.SB = FMath::Min(L.SB + Extra, FMath::Max(L.SB, L.Len - 2.0));
			}
		}
		if (const FVector2D* N = Nodes.Find(L.A))
		{
			FVector2D T;
			const FVector2D B0 = At(L, 0.0, 0.0, &T);
			Pts.Reset();
			if (const TArray<int32>* In = NodeIn.Find(L.A))
			{
				for (int32 j : *In)
				{
					const FLink& M = Links[j];
					if (!(M.A == L.B && M.B == L.A)) LanePts(M, true, Pts);
				}
			}
			if (const TArray<int32>* Out = NodeOut.Find(L.A)) for (int32 j : *Out) if (j != i) LanePts(Links[j], false, Pts);
			if (Pts.Num())
			{
				double MaxP = -1e9;
				for (const FVector2D& Q : Pts) MaxP = FMath::Max(MaxP, FVector2D::DotProduct(Q - *N, T));
				L.EX = FMath::Min3(15.0, FMath::Max(0.0, FMath::Max(0.0, MaxP) - FVector2D::Distance(B0, *N)), FMath::Max(0.0, L.Len - 2.0));
			}
		}
	}
}

// The street signal heads' lens rule (M_SignalLens2): t = frac(T / (GT * N) + phase), this approach's slot
// s = t * N - group wrapped into [0, N): green below 0.8, yellow to 1, red after.
int32 ASkysterTraffic::Signal(int32 Unit, int32 Group, double T) const
{
	const TPair<int32, double>* U = Units.Find(Unit);
	if (!U) return 0;
	const double N = FMath::Max(1, U->Key);
	const double t = FMath::Frac(T / (GroupTime * N) + U->Value);
	double s = t * N - Group;
	s -= N * FMath::FloorToDouble(s / N);
	return s < 0.8 ? 0 : s < 1.0 ? 1 : 2;
}

FVector2D ASkysterTraffic::At(const FLink& L, double S, double Off, FVector2D* Dir) const
{
	S = FMath::Clamp(S, 0.0, L.Len);
	int32 i = FMath::Clamp(Algo::UpperBound(L.S, S) - 1, 0, L.P.Num() - 2);
	const double Seg = FMath::Max(L.S[i + 1] - L.S[i], 1e-6);
	const FVector2D T = (L.P[i + 1] - L.P[i]).GetSafeNormal();
	if (Dir) *Dir = T;
	return FMath::Lerp(L.P[i], L.P[i + 1], (S - L.S[i]) / Seg) + Right(T) * Off;
}

double ASkysterTraffic::LaneOff(const FCar& C, const FLink& L, int32 Lane) const
{
	return L.O[FMath::Clamp(Lane, 0, L.O.Num() - 1)] * (C.bSky ? SKY_LANE : 1.0);
}

// where across its link the car is now: moving from the lane it came in on to the one it wants, plus a crash shove
double ASkysterTraffic::LatNow(const FCar& C) const
{
	const FLink& L = Links[C.Link];
	const double A = LaneOff(C, L, C.NextLane), B = LaneOff(C, L, C.Lane);
	return A + (B - A) * FMath::SmoothStep(0.0, 1.0, C.LatK) + C.Shove;
}

UStaticMeshComponent* ASkysterTraffic::MakePart(UStaticMesh* Mesh, USceneComponent* Parent, float Cull)
{
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->SetGenerateOverlapEvents(false);
	C->SetCachedMaxDrawDistance(Cull);
	C->SetupAttachment(Parent);
	C->RegisterComponent();
	return C;
}

// Floating signals over the sky lanes: one head over the lanes of every signalised approach, at the stop line,
// facing the arriving cabs and lit on the street signals' clock; a floating STOP where the street has a stop sign.
void ASkysterTraffic::BuildSigns()
{
	UStaticMesh* Head = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/City/Roads/Kit/RK_SigHead3/StaticMeshes/RK_SigHead3.RK_SigHead3"));
	UStaticMesh* Panel = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/City/Roads/Kit/RK_SignPanel/StaticMeshes/RK_SignPanel.RK_SignPanel"));
	if (Head) SkyHeads->SetStaticMesh(Head);
	if (Panel) SkyStops->SetStaticMesh(Panel);
	SkyHeads->SetNumCustomDataFloats(3);
	SkyStops->SetNumCustomDataFloats(1);
	const double Z = SkyHeight * 100.0;
	for (const FLink& L : Links)
	{
		if (L.Ctrl == 0) continue;
		FVector2D T;
		double Mid = 0;
		for (double O : L.O) Mid += O;
		Mid = Mid / L.O.Num() * SKY_LANE;
		const FVector2D P = At(L, FMath::Max(0.0, L.Len - 3.0), Mid, &T);
		// the props' convention: Unreal yaw = -(plan yaw of the way it faces), and it faces the arriving traffic
		const double Yaw = -FMath::RadiansToDegrees(FMath::Atan2(-T.Y, -T.X));
		if (L.Ctrl == 1 && Head)
		{
			const TPair<int32, double>* U = Units.Find(L.Unit);
			if (!U) continue;
			const int32 I = SkyHeads->AddInstance(FTransform(FRotator(0, Yaw, 0), UEOf(P, Z + 650.0), FVector(2.4)), true);
			SkyHeads->SetCustomDataValue(I, 0, (float)U->Value, false);
			SkyHeads->SetCustomDataValue(I, 1, (float)L.Group, false);
			SkyHeads->SetCustomDataValue(I, 2, (float)U->Key, false);
		}
		else if (L.Ctrl == 2 && Panel)
		{
			const int32 I = SkyStops->AddInstance(FTransform(FRotator(0, Yaw, 0), UEOf(P, Z + 600.0), FVector(0.75 / 0.9 * 3.0, 3.0, 0.75 / 0.9 * 3.0)), true);
			SkyStops->SetCustomDataValue(I, 0, 2.0f, false);    // the sign atlas' STOP cell
		}
	}
	SkyHeads->MarkRenderStateDirty();
	SkyStops->MarkRenderStateDirty();
	SkyHeads->SetVisibility(false);
	SkyStops->SetVisibility(false);
}

void ASkysterTraffic::SetGround(bool bOn)
{
	bGround = GGround = bOn;
	Clear(false);
	if (bOn && IsReady()) Populate(false, GroundCars);
}

void ASkysterTraffic::SetSky(bool bOn)
{
	bSky = GSky = bOn;
	Clear(true);
	if (SkyHeads) SkyHeads->SetVisibility(bOn);
	if (SkyStops) SkyStops->SetVisibility(bOn);
	if (bOn && IsReady()) Populate(true, SkyCabs);
}

void ASkysterTraffic::Clear(bool bSkyLayer)
{
	for (int32 i = Cars.Num() - 1; i >= 0; --i)
	{
		if (Cars[i].bSky != bSkyLayer) continue;
		if (UStaticMeshComponent* B = Bodies.IsValidIndex(Cars[i].Comp) ? Bodies[Cars[i].Comp].Get() : nullptr)
		{
			TArray<USceneComponent*> Kids;
			B->GetChildrenComponents(false, Kids);
			for (USceneComponent* K : Kids) K->DestroyComponent();
			B->DestroyComponent();
			Bodies[Cars[i].Comp] = nullptr;
		}
		if (Boxes.IsValidIndex(Cars[i].Comp)) Boxes[Cars[i].Comp] = nullptr;
		Cars.RemoveAt(i);
	}
	// the car indices moved: the per-tick books are rebuilt on the next tick
	for (TArray<int32>& A : OnLink) A.Reset();
	Touched.Reset();
	Grid.Reset();
	Occ.Reset();
}

void ASkysterTraffic::Populate(bool bSkyLayer, int32 Count)
{
	static const int32 Weights[] = { 3, 3, 2, 2, 1 };       // Model 3, Model Y, Cybertruck, Cybercab, Semi
	for (int32 n = 0; n < Count; ++n)
	{
		FCar C;
		C.bSky = bSkyLayer;
		if (bSkyLayer) C.Model = CAB;
		else
		{
			int32 R = Rand.RandRange(0, 10), M = 0;
			while (R >= Weights[M]) { R -= Weights[M]; ++M; }
			C.Model = M;
		}
		UStaticMesh* BM = BodyMeshes.IsValidIndex(C.Model) ? BodyMeshes[C.Model].Get() : nullptr;
		if (!BM) continue;
		const SkyFleet::FCar& Def = SkyFleet::Cars[C.Model];
		C.Len = Def.Size.X / 100.0;
		C.W = Def.Size.Y / 100.0;
		C.Want = Rand.FRandRange(0.88, 1.06);
		// free road only: no free spot anywhere, one car fewer
		if (!Place(C, 20.0, bSkyLayer ? 650.0 : 450.0) && !Place(C, 0.0, 1e6)) continue;
		C.bPlaced = false;
		UStaticMeshComponent* Body = MakePart(BM, RootComponent, bSkyLayer ? 60000.f : 30000.f);
		Body->SetCastShadow(!bSkyLayer);
		for (int32 w = 0; w < Def.NumWheels; ++w)
		{
			UStaticMesh* WM = WheelMeshes[C.Model * 6 + w];
			if (!WM) continue;
			UStaticMeshComponent* Wh = MakePart(WM, Body, 9000.f);
			Wh->SetCastShadow(false);
			Wh->SetRelativeLocation(Def.W[w].P - FVector(Def.OffX, 0, 0));   // the body sits on its own centre
		}
		// the hit box: what the Roadster's body sweeps (Visibility channel) run into; nothing else collides with it
		UBoxComponent* Box = NewObject<UBoxComponent>(this);
		Box->SetMobility(EComponentMobility::Movable);
		Box->SetBoxExtent(FVector(Def.Size.X * 0.5 - 2.0, Def.Size.Y * 0.5 - 2.0, Def.Size.Z * 0.5), false);
		Box->SetRelativeLocation(FVector(0, 0, Def.Size.Z * 0.5));
		Box->SetCollisionObjectType(ECC_WorldDynamic);
		Box->SetCollisionResponseToAllChannels(ECR_Ignore);
		Box->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
		Box->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Box->SetGenerateOverlapEvents(false);
		Box->SetCanEverAffectNavigation(false);
		Box->CanCharacterStepUpOn = ECB_No;
		Box->SetHiddenInGame(true);
		Box->SetupAttachment(Body);
		Box->RegisterComponent();
		C.Comp = Bodies.Add(Body);
		Boxes.SetNum(Bodies.Num());
		Boxes[C.Comp] = Box;
		Cars.Add(C);
		Pose(Cars.Last(), Focus);
	}
}

// A free spot on the road for a car (its body plus 4 m ahead and behind, and the player well clear).
bool ASkysterTraffic::FreeSpot(const FCar& C, const FVector2D& P, const FVector2D& D) const
{
	for (const FCar& O : Cars)
	{
		if (&O == &C || O.bSky != C.bSky || O.Fade > 0 || O.Link < 0) continue;
		if (FMath::Abs(O.Pos.X - P.X) > 20.0 || FMath::Abs(O.Pos.Y - P.Y) > 20.0) continue;
		if (ObbDepth(P, D, C.Len * 0.5 + 4.0, C.W * 0.5 + 0.8, O.Pos, O.Dir, O.Len * 0.5, O.W * 0.5) > 0) return false;
	}
	if (Player.bOn && Player.bSky == C.bSky && ObbDepth(P, D, C.Len * 0.5 + 6.0, C.W * 0.5 + 1.5, Player.P, Player.D, Player.Len * 0.5, Player.W * 0.5) > 0) return false;
	return true;
}

bool ASkysterTraffic::Place(FCar& C, double MinR, double MaxR)
{
	const FVector2D F(Focus.Y / 100.0, Focus.X / 100.0);
	for (int32 Try = 0; Try < 80; ++Try)
	{
		const int32 i = Rand.RandRange(0, Links.Num() - 1);
		const FLink& L = Links[i];
		if (L.Len < C.Len + 16.0) continue;
		if (!C.bSky && C.Model == 4 && L.V < 12.0) continue;   // no semis on the side streets
		const double D = FVector2D::Distance(L.Mid, F);
		if (D < MinR || D > MaxR) continue;
		// clear of both junction boxes
		const double Lo = FMath::Max(C.Len * 0.5 + 6.0, L.EX + C.Len * 0.5 + 1.0);
		const double Hi = L.Len - L.SB - C.Len * 0.5 - 2.0;
		if (Hi <= Lo) continue;
		const double S = Rand.FRandRange(Lo, Hi);
		bool bFree = true;
		for (const FCar& O : Cars)
		{
			if (&O != &C && O.Link == i && O.bSky == C.bSky && O.Fade <= 0 && FMath::Abs(O.S - S) < 14.0) { bFree = false; break; }
		}
		if (!bFree) continue;
		FCar Tmp = C;
		Enter(Tmp, i, Rand.RandRange(0, L.O.Num() - 1), S);
		Tmp.NextLane = Tmp.Lane;                             // already in the lane it wants
		Tmp.LatK = 1.0;
		Tmp.Shove = Tmp.YawOff = 0;
		FVector2D P, Dd;
		PoseXY(Tmp, P, Dd);
		if (!FreeSpot(C, P, Dd)) { ++StatRejected; continue; }
		C = Tmp;
		C.V = L.V * 0.6;
		C.Prev = -1;
		C.YieldT = C.Stuck = C.Hold = 0;
		C.Crash = C.ShoveV = C.YawV = C.Pin = C.Fade = 0;
		C.bPlaced = true;
		C.Pos = P;
		C.Dir = Dd;
		C.Lat = LatNow(C);
		return true;
	}
	return false;
}

// On a new link: choose where to go at its far end, and the lane for it (left turns from the inner lane, right turns
// from the outer, straight on any). A car arriving in another lane changes over when there's a gap.
void ASkysterTraffic::Enter(FCar& C, int32 Link, int32 FromLane, double S)
{
	C.Link = Link;
	C.S = S;
	C.bServed = false;
	C.Wait = 0;
	C.bCommit = false;
	C.ReqT = -1;
	C.YieldT = 0;
	const FLink& L = Links[Link];
	C.NextLane = FMath::Clamp(FromLane, 0, L.O.Num() - 1);   // NextLane doubles as "the lane we came in on"
	PlanNext(C);
	C.LatK = C.NextLane == C.Lane ? 1.0 : 0.0;
	PlanCurve(C);
}

void ASkysterTraffic::PlanNext(FCar& C)
{
	const FLink& L = Links[C.Link];
	C.Next = -1;
	int32 Turn = 0;                                          // -1 left, 0 straight, 1 right
	if (L.Next.Num() > 0)
	{
		FVector2D T0;
		At(L, L.Len, 0, &T0);
		double Best = -1e9;
		for (int32 j : L.Next)
		{
			FVector2D T1;
			At(Links[j], 0, 0, &T1);
			const double Cross = T0.X * T1.Y - T0.Y * T1.X, Dot = FVector2D::DotProduct(T0, T1);
			const int32 Tn = Dot > 0.7 ? 0 : (Cross > 0 ? -1 : 1);
			const double W = (Tn == 0 ? 3.0 : Tn == 1 ? 1.6 : 1.0) * Rand.FRandRange(0.2, 1.0);
			if (W > Best) { Best = W; C.Next = j; Turn = Tn; }
		}
	}
	const int32 N = L.O.Num();
	C.Lane = Turn < 0 ? 0 : Turn > 0 ? N - 1 : FMath::Clamp(C.NextLane, 0, N - 1);
}

// The crossing at the end of the link, planned from the lane the car wants: its lane in the next link and the curve.
void ASkysterTraffic::PlanCurve(FCar& C) const
{
	if (C.Next < 0) return;
	const FLink& L = Links[C.Link];
	const FLink& N = Links[C.Next];
	C.InLane = FMath::Clamp(C.Lane == L.O.Num() - 1 ? N.O.Num() - 1 : C.Lane, 0, N.O.Num() - 1);
	MakeCurve(C, L, LaneOff(C, L, C.Lane), N, C.InLane, C.Q0, C.Q1, C.Q2, C.QLen);
}

// Across the junction on a curve from this lane's end to the next link's lane start: a quadratic through the corner
// where the two lanes' lines meet (straight across when there's no such corner).
void ASkysterTraffic::MakeCurve(const FCar& C, const FLink& L, double LatEnd, const FLink& N, int32 InLane, FVector2D& OutP0, FVector2D& OutP1, FVector2D& OutP2, double& OutLen) const
{
	FVector2D T0, T2;
	OutP0 = At(L, L.Len, LatEnd, &T0);
	OutP2 = At(N, 0, LaneOff(C, N, InLane), &T2);
	OutP1 = (OutP0 + OutP2) * 0.5;
	const double Den = Cross2(T0, T2);
	if (FMath::Abs(Den) > 0.15)
	{
		const FVector2D D = OutP2 - OutP0;
		// OutP0 + A * T0 = OutP2 + B * T2: the corner is ahead of this lane's end and before the next lane's start
		// (the old test wanted B > 0, which only a few odd junctions pass, so turns were cut across in a straight line)
		const double A = Cross2(D, T2) / Den, B = Cross2(D, T0) / Den;
		if (A > 0 && A < 60 && B < 0 && B > -60) OutP1 = OutP0 + T0 * A;
	}
	double Len = 0;
	FVector2D Prev = OutP0;
	for (int32 k = 1; k <= 8; ++k) { const FVector2D Q = Bez(OutP0, OutP1, OutP2, k / 8.0, nullptr); Len += FVector2D::Distance(Prev, Q); Prev = Q; }
	OutLen = FMath::Max(Len, 1.0);
}

FString ASkysterTraffic::GetDebugStats() const
{
	int32 NG = 0, NS = 0, Moving = 0, Crashed = 0, Fading = 0, Committed = 0, Held = 0;
	for (const FCar& C : Cars)
	{
		(C.bSky ? NS : NG)++;
		Moving += C.V > 0.5 ? 1 : 0;
		Crashed += C.Crash > 0 ? 1 : 0;
		Fading += C.Fade > 0 ? 1 : 0;
		Committed += C.bCommit ? 1 : 0;
		Held += (C.Why == W_Hold || C.Why == W_Player) ? 1 : 0;
	}
	return FString::Printf(TEXT("{\"ground\":%d,\"sky\":%d,\"moving\":%d,\"committed\":%d,\"held_now\":%d,\"crashed_now\":%d,\"fading_now\":%d,")
		TEXT("\"commits\":%d,\"uncommits\":%d,\"requests\":%d,\"holds\":%d,\"relocated_stuck\":%d,\"faded\":%d,\"crashes\":%d,\"pinned\":%d,")
		TEXT("\"place_rejected\":%d,\"lanes_dropped\":%d,\"player_on\":%s,\"player_sky\":%s,\"fsd_commit\":%s}"),
		NG, NS, Moving, Committed, Held, Crashed, Fading, StatCommits, StatUncommits, StatRequests, StatHolds, StatRelocated, StatFaded,
		StatCrashes, StatPinned, StatRejected, LanesDropped, Player.bOn ? TEXT("true") : TEXT("false"), Player.bSky ? TEXT("true") : TEXT("false"),
		Fsd.bCommit ? TEXT("true") : TEXT("false"));
}

// ------------------------------------------------------------------------------------------------ the tick

void ASkysterTraffic::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!IsReady()) return;
	FVector Cam = Focus;
	if (APlayerCameraManager* PC = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		Cam = Focus = PC->GetCameraLocation();
		const FVector Fw = PC->GetCameraRotation().Vector();
		const FVector2D F2(Fw.Y, Fw.X);
		if (!F2.IsNearlyZero()) CamFwd = F2.GetSafeNormal();
	}
	UpdatePlayer(FMath::Max((double)DeltaSeconds, 1e-4));
	if (bPending)
	{
		if (Focus.IsNearlyZero()) return;
		bPending = false;
		SetGround(GGround);
		SetSky(GSky);
	}
	if (Cars.Num() == 0) return;
	const double Dt = FMath::Min((double)DeltaSeconds, 0.05);
	const double T = GetWorld()->GetTimeSeconds();
	for (int32 i : Touched) OnLink[i].Reset();
	Touched.Reset();
	for (int32 c = 0; c < Cars.Num(); ++c)
	{
		if (!OnLink.IsValidIndex(Cars[c].Link)) continue;
		if (OnLink[Cars[c].Link].Num() == 0) Touched.Add(Cars[c].Link);
		OnLink[Cars[c].Link].Add(c);
	}
	BuildGrid();
	RebuildOcc(T);
	const FVector2D F(Focus.Y / 100.0, Focus.X / 100.0);
	for (int32 c = 0; c < Cars.Num(); ++c)
	{
		FCar& C = Cars[c];
		if (!Links.IsValidIndex(C.Link)) continue;
		if (C.Fade > 0)
		{
			// shrinking away (stuck in sight, or pinned by the player): then back onto a street out ahead
			C.Fade += Dt;
			if (C.Fade >= FADE_T)
			{
				const FVector2D Old = C.Pos;
				const int32 OldLink = C.Link;
				if (Place(C, C.bSky ? 200.0 : 140.0, C.bSky ? 650.0 : 450.0)) { GridMove(c, Old); UpdateOcc(c, OldLink); ++StatFaded; }
				else C.Fade = FADE_T - 0.01;
			}
			C.bPlaced = false;
			Pose(C, Cam);
			continue;
		}
		const FCar Snap = C;
		Step(c, Dt, T);
		if (C.bPlaced)
		{
			C.bPlaced = false;
			GridMove(c, Snap.Pos);
			UpdateOcc(c, Snap.Link);
			Pose(C, Cam);
			continue;
		}
		// last resort: a move that would push this body into another one (or the player's car) isn't made
		FVector2D NP, ND;
		PoseXY(C, NP, ND);
		const uint8 Blocked = OverlapAny(c, NP, ND, Snap.Pos, Snap.Dir);
		if (Blocked != W_None)
		{
			const double Hold = C.Hold + Dt, Stuck = C.Stuck;
			if (Snap.Why != W_Hold && Snap.Why != W_Player) ++StatHolds;
			C = Snap;
			C.V = 0;
			C.Hold = Hold;
			C.Stuck = Stuck;
			C.Why = Blocked;
		}
		else
		{
			C.Hold = FMath::Max(0.0, C.Hold - Dt * 0.5);
			C.Pos = NP;
			C.Dir = ND;
			if (C.S >= 0) C.Lat = LatNow(C);
			GridMove(c, Snap.Pos);
		}
		if (C.bCommit != Snap.bCommit || C.Link != Snap.Link || C.ReqT != Snap.ReqT || C.bInOcc || Inside(C)) UpdateOcc(c, Snap.Link);
		Unstick(c, Dt);
		// far behind you: back onto a street out ahead (cars draw out to 300 m, cabs 600 m: they come and go beyond that)
		if (C.Fade <= 0 && !C.bPlaced)
		{
			const FVector2D P = C.S < 0 ? C.P2 : C.Pos;
			if (FVector2D::Distance(P, F) > (C.bSky ? 800.0 : 600.0))
			{
				const FVector2D Old = C.Pos;
				const int32 OldLink = C.Link;
				if (Place(C, C.bSky ? 200.0 : 140.0, C.bSky ? 650.0 : 450.0)) { GridMove(c, Old); UpdateOcc(c, OldLink); }
			}
		}
		C.bPlaced = false;
		Pose(C, Cam);
	}
	PlayerContact(Dt);
}

void ASkysterTraffic::Step(int32 Ci, double Dt, double T)
{
	FCar& C = Cars[Ci];
	const FLink& L = Links[C.Link];
	C.Why = W_None;
	double V0 = L.V * C.Want * (C.bSky ? 1.35 : 1.0);
	if (C.S < 0) V0 = FMath::Min(V0, 9.0);                    // through the junction
	double Gap = 1e9, VLead = 0, LDot = 1;
	int32 LWho = 0;                                          // 1 a car, 2 the player
	const double MyLat = C.S >= 0 ? LatNow(C) : LaneOff(C, L, C.NextLane);
	const double Tgt = LaneOff(C, L, C.Lane);
	bool bSideBlock = false;
	// the car ahead on this link: anyone whose body is across my lane (or the lane I'm moving over to)
	for (int32 o : OnLink[C.Link])
	{
		if (o == Ci || !Cars.IsValidIndex(o)) continue;
		const FCar& O = Cars[o];
		if (O.Link != C.Link || O.bSky != C.bSky || O.Fade > 0) continue;
		const double Half = (O.W + C.W) * 0.5 + 0.2;
		if (O.S >= 0 && C.S >= 0 && C.LatK < 1.0 && FMath::Abs(O.S - C.S) < (O.Len + C.Len) * 0.5 + 1.0)
		{
			// someone alongside in the lane I want: wait for the gap before moving over
			const double NL = MyLat + (Tgt - MyLat) * 0.2;
			if (FMath::Abs(O.Lat - NL) < Half && FMath::Abs(O.Lat - MyLat) >= Half * 0.9) bSideBlock = true;
		}
		if (O.S <= C.S) continue;
		if (O.S >= 0 && C.S >= 0)
		{
			if (FMath::Abs(O.Lat - MyLat) > Half && !(C.LatK < 1.0 && FMath::Abs(O.Lat - Tgt) < Half && O.S - C.S < 30.0)) continue;
		}
		else if (O.S >= 0)
		{
			if (FMath::Abs(O.Lat - MyLat) > Half) continue;
		}
		else if (O.NextLane != C.NextLane) continue;
		const double G = O.S - C.S - (O.Len + C.Len) * 0.5;
		if (G < Gap) { Gap = G; VLead = O.V; LDot = 1; LWho = 1; }
	}
	// into the next link, across the crossing (its real length: some are 1 m, some 40)
	if (C.Next >= 0 && C.S >= 0 && L.Len - C.S < LOOK)
	{
		const FLink& N = Links[C.Next];
		const double Dn = (L.Len - C.S) + C.QLen;
		const double LatIn = LaneOff(C, N, C.InLane);
		for (int32 o : OnLink[C.Next])
		{
			if (o == Ci || !Cars.IsValidIndex(o)) continue;
			const FCar& O = Cars[o];
			if (O.Link != C.Next || O.bSky != C.bSky || O.Fade > 0) continue;
			if (O.S < 0) { if (O.NextLane != C.InLane) continue; }
			else if (FMath::Abs(O.Lat - LatIn) > (O.W + C.W) * 0.5 + 0.2) continue;
			const double G = Dn + O.S - (O.Len + C.Len) * 0.5;
			if (G < Gap) { Gap = G; VLead = O.V; LDot = 1; LWho = 1; }
		}
	}
	// bodies straight ahead, whatever link they're on (short links, bends, crossings, overlapping streets, the player)
	{
		double RV = 0, RDot = 1;
		bool bRP = false;
		const double G = RayAhead(C.Pos, C.Dir, C.W, C.Len, FMath::Max(8.0, C.V * 1.5 + 6.0), C.bSky, Ci, true, RV, RDot, bRP);
		if (G < Gap) { Gap = G; VLead = RV; LDot = RDot; LWho = bRP ? 2 : 1; }
	}
	if (bSideBlock) V0 *= 0.8;                               // drop back to let the car alongside go by
	if (LWho == 2) C.Why = W_Player;
	else if (LWho == 1) C.Why = LDot > 0.7 ? W_Car : W_Cross;
	// the end of the link: signals, stop signs, and the right to cross
	if (C.S >= 0 && C.Next >= 0)
	{
		const double DStop = L.Len - L.SB - C.S;
		if (C.bCommit)
		{
			// reserved but going nowhere (blocked in front of the line): give the junction back
			if (C.V < 0.2 && T - C.CommitT > 8.0 && DStop > -0.5) { C.bCommit = false; ++StatUncommits; }
		}
		else
		{
			bool bStop = false;
			uint8 Why = W_None;
			if (DStop > -0.5)
			{
				if (L.Ctrl == 1)
				{
					const int32 St = Signal(L.Unit, L.Group, T);
					bStop = St == 2 || (St == 1 && C.V * C.V / (2.0 * DEC) < DStop + 1.0);
					Why = W_Signal;
				}
				else if (L.Ctrl == 2 && !C.bServed)
				{
					bStop = true;
					Why = W_Stop;
					if (DStop < 4.0 && C.V < 0.6 && (C.Wait += Dt) > 1.3) { C.bServed = true; bStop = false; }
				}
			}
			if (!bStop && DStop <= C.V * C.V / (2.0 * DEC) + 4.0 + C.V * 0.5)
			{
				if (C.LatK < 1.0 && !(C.V < 0.5 && DStop < 3.0 && C.YieldT > 3.0))
				{
					// finish the lane change before taking the junction (after 3 s at the line, go from where it is)
					bStop = true;
					Why = W_Lane;
					if (C.V < 0.5 && DStop < 3.0) C.YieldT += Dt;
				}
				else
				{
					// only the first car in its lane decides; the ones behind follow it
					bool bFirst = true;
					for (int32 o : OnLink[C.Link])
					{
						if (o == Ci || !Cars.IsValidIndex(o)) continue;
						const FCar& O = Cars[o];
						if (O.Link == C.Link && O.bSky == C.bSky && O.S > C.S && !O.bCommit && O.Fade <= 0 && FMath::Abs(O.Lat - MyLat) < (O.W + C.W) * 0.5) { bFirst = false; break; }
					}
					if (bFirst)
					{
						FPath Mine;
						MovePath(C, Mine);
						const uint8 R = CanGo(Ci, C.bSky, C.Link, C.Lane, C.Next, C.InLane, C.W, C.Len, C.V, C.YieldT, C.ReqT, C.QLen, Mine, T);
						if (R == W_None) { C.bCommit = true; C.CommitT = T; C.ReqT = -1; ++StatCommits; }
						else
						{
							bStop = true;
							Why = R;
							if (C.V < 0.5)
							{
								C.YieldT += Dt;
								if (C.YieldT > REQ_AFTER && C.ReqT < 0) { C.ReqT = T; ++StatRequests; }
							}
						}
					}
					else { bStop = DStop < 1.0; Why = W_Car; }
				}
			}
			if (bStop && DStop < Gap) { Gap = FMath::Max(0.0, DStop); VLead = 0; C.Why = Why; }
		}
	}
	if (C.Crash > 0)
	{
		// hit by the player: brake to a stop, shoved aside, wait, then carry on
		C.Crash -= Dt;
		C.V = FMath::Max(0.0, C.V - 9.0 * Dt);
		C.Shove = FMath::Clamp(C.Shove + C.ShoveV * Dt, -1.6, 1.6);
		C.ShoveV *= FMath::Exp(-4.0 * Dt);
		C.YawOff = FMath::Clamp(C.YawOff + C.YawV * Dt, -25.0, 25.0);
		C.YawV *= FMath::Exp(-4.0 * Dt);
	}
	else
	{
		if (C.Shove != 0 || C.YawOff != 0)
		{
			// straighten up back into the lane
			const double K = FMath::Exp(-0.8 * Dt);
			C.Shove *= K;
			C.YawOff *= K;
			if (FMath::Abs(C.Shove) < 0.01 && FMath::Abs(C.YawOff) < 0.1) C.Shove = C.YawOff = 0;
		}
		// intelligent driver model: speed up toward the limit, keep a safe time gap, brake smoothly
		const double SStar = JAM + C.V * 1.2 + C.V * (C.V - VLead) / (2.0 * FMath::Sqrt(ACC * DEC));
		double A = ACC * (1.0 - FMath::Pow(C.V / FMath::Max(V0, 0.5), 4.0) - FMath::Square(FMath::Max(SStar, 0.0) / FMath::Max(Gap, 0.3)));
		A = FMath::Clamp(A, -9.0, ACC);
		C.V = FMath::Max(0.0, C.V + A * Dt);
	}
	C.S += C.V * Dt;
	C.Spin = FMath::Fmod(C.Spin + C.V * Dt / 0.36, UE_DOUBLE_PI * 2);
	if (C.S >= 0 && C.LatK < 1.0 && !bSideBlock && !C.bCommit) C.LatK = FMath::Min(1.0, C.LatK + FMath::Max(C.V, 2.0) * Dt / LC_LEN);
	if (C.S >= L.Len)
	{
		if (C.Next < 0) { Place(C, C.bSky ? 200.0 : 140.0, C.bSky ? 650.0 : 450.0); return; }
		// across the junction on the planned curve (from where the car really is, if it didn't finish a lane change)
		const double LatEnd = LatNow(C) - C.Shove;
		if (C.LatK < 1.0 || FMath::Abs(LatEnd - LaneOff(C, L, C.Lane)) > 0.3) MakeCurve(C, L, LatEnd, Links[C.Next], C.InLane, C.Q0, C.Q1, C.Q2, C.QLen);
		C.P0 = C.Q0;
		C.P1 = C.Q1;
		C.P2 = C.Q2;
		C.TurnLen = C.QLen;
		const double Over = C.S - L.Len;
		C.Prev = C.Link;
		Enter(C, C.Next, C.InLane, -C.TurnLen + Over);
	}
}

// The body's place and heading (plan metres) for the car's state.
void ASkysterTraffic::PoseXY(const FCar& C, FVector2D& OutP, FVector2D& OutD) const
{
	const FLink& L = Links[C.Link];
	if (C.S < 0)
	{
		const double U = FMath::Clamp(1.0 + C.S / C.TurnLen, 0.0, 1.0);
		OutP = Bez(C.P0, C.P1, C.P2, U, &OutD);
		if (Links.IsValidIndex(C.Prev))
		{
			FVector2D T0, T2;
			At(Links[C.Prev], Links[C.Prev].Len, 0.0, &T0);
			At(L, 0.0, 0.0, &T2);
			// straight on with a sideways step between the two links' lanes: slide across, don't swing the body round
			if (FMath::Abs(Cross2(T0, T2)) <= 0.15 && FVector2D::DotProduct(T0, T2) > 0) OutD = (T0 * (1.0 - U) + T2 * U).GetSafeNormal();
		}
		if (C.Shove != 0) OutP += Right(OutD) * C.Shove;
	}
	else
	{
		OutP = At(L, C.S, LatNow(C), &OutD);
		if (C.LatK < 1.0 && C.NextLane != C.Lane)
		{
			// pointing into the lane change
			const double A = LaneOff(C, L, C.NextLane), B = LaneOff(C, L, C.Lane);
			const double K2 = FMath::Min(1.0, C.LatK + 2.0 / LC_LEN);
			const FVector2D Q = At(L, C.S + 2.0, A + (B - A) * FMath::SmoothStep(0.0, 1.0, K2) + C.Shove);
			if (FVector2D::DistSquared(Q, OutP) > 1e-4) OutD = (Q - OutP).GetSafeNormal();
		}
	}
	if (C.YawOff != 0)
	{
		const double Ang = FMath::DegreesToRadians(C.YawOff);
		const double Cs = FMath::Cos(Ang), Sn = FMath::Sin(Ang);
		OutD = FVector2D(OutD.X * Cs - OutD.Y * Sn, OutD.X * Sn + OutD.Y * Cs);
	}
	if (OutD.IsNearlyZero()) OutD = C.Dir;
}

void ASkysterTraffic::Pose(FCar& C, const FVector& Cam)
{
	UStaticMeshComponent* Body = Bodies.IsValidIndex(C.Comp) ? Bodies[C.Comp].Get() : nullptr;
	if (!Body) return;
	const double Yaw = YawOf(C.Dir);
	double Z = 0.0, Roll = 0.0;
	if (C.bSky)
	{
		// cabs bank into the turns and bob gently on their fans
		const double Prev = Body->GetComponentRotation().Yaw;
		const double Rate = FMath::FindDeltaAngleDegrees(Prev, Yaw) / FMath::Max((double)GetWorld()->GetDeltaSeconds(), 1e-3);
		C.Bank = FMath::Lerp(C.Bank, FMath::Clamp(Rate * 0.35, -22.0, 22.0), 0.08);
		Roll = C.Bank;
		Z = SkyHeight * 100.0 + 40.0 * FMath::Sin(GetWorld()->GetTimeSeconds() * 1.3 + C.Comp);
	}
	const FVector Loc = UEOf(C.Pos, Z);
	Body->SetWorldLocationAndRotation(Loc, FRotator(0, Yaw, Roll));
	// shrinking away: smaller each frame, and no longer solid
	const double Scale = C.Fade > 0 ? FMath::Max(0.02, 1.0 - C.Fade / FADE_T) : 1.0;
	if (!FMath::IsNearlyEqual(Body->GetComponentScale().X, Scale, 1e-3)) Body->SetWorldScale3D(FVector(Scale));
	const bool bBox = C.Fade <= 0;
	if (bBox != C.bBoxOn)
	{
		C.bBoxOn = bBox;
		if (UBoxComponent* Box = Boxes.IsValidIndex(C.Comp) ? Boxes[C.Comp].Get() : nullptr) Box->SetCollisionEnabled(bBox ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	}
	// wheels turn only where you could see them turn
	const bool bNear = FVector::DistSquared(Loc, Cam) < FMath::Square(8000.0);
	if (bNear || C.bWheels)
	{
		C.bWheels = bNear;
		TArray<USceneComponent*> Kids;
		Body->GetChildrenComponents(false, Kids);
		for (USceneComponent* K : Kids)
		{
			if (K && K->IsA<UStaticMeshComponent>()) K->SetRelativeRotation(FRotator(-FMath::RadiansToDegrees(C.Spin), 0, 0));
		}
	}
}

// ------------------------------------------------------------------------------------------------ junctions

// Is the car crossing a junction, or is its tail still in the box?
bool ASkysterTraffic::Inside(const FCar& C) const
{
	return C.S < 0 || (C.Prev >= 0 && C.S - C.Len * 0.5 < Links[C.Link].EX + 0.5);
}

// The crossing a car has planned: from its stop line, over the curve, to where the box ends in the next link.
void ASkysterTraffic::MovePath(const FCar& C, FPath& Out) const
{
	Out.Reset();
	if (!Links.IsValidIndex(C.Link) || !Links.IsValidIndex(C.Next)) return;
	const FLink& L = Links[C.Link];
	const FLink& N = Links[C.Next];
	FVector2D Q0 = C.Q0, Q1 = C.Q1, Q2 = C.Q2;
	double Lat = LaneOff(C, L, C.Lane);
	if (C.LatK < 1.0)
	{
		// still between lanes: the crossing from where it is (it won't move over any more once it has reserved)
		double QL = 0;
		Lat = LatNow(C) - C.Shove;
		MakeCurve(C, L, Lat, N, C.InLane, Q0, Q1, Q2, QL);
	}
	Out.Add(At(L, FMath::Max(0.0, L.Len - L.SB), Lat));
	if (L.SB > 1.5) Out.Add(Q0);
	for (int32 k = 1; k <= 8; ++k) Out.Add(Bez(Q0, Q1, Q2, k / 8.0, nullptr));
	if (N.EX > 0.5) Out.Add(At(N, N.EX, LaneOff(C, N, C.InLane)));
}

// What a car crossing the junction still covers: from its tail to its nose, or to where the box ends.
void ASkysterTraffic::InsidePath(const FCar& C, FPath& Out) const
{
	Out.Reset();
	const FLink& L = Links[C.Link];
	const double Lat = LaneOff(C, L, C.NextLane);
	const double Tail = C.S - C.Len * 0.5 - 0.5;
	if (Tail < 0)
	{
		const double U0 = FMath::Clamp(1.0 + Tail / C.TurnLen, 0.0, 1.0);
		for (int32 k = 0; k <= 6; ++k) Out.Add(Bez(C.P0, C.P1, C.P2, U0 + (1.0 - U0) * k / 6.0, nullptr));
	}
	else Out.Add(At(L, Tail, Lat));
	const double Far = FMath::Max(L.EX, C.S + C.Len * 0.5);
	if (Far > FMath::Max(Tail, 0.0) + 0.3) Out.Add(At(L, FMath::Min(Far, L.Len), Lat));
	if (Out.Num() < 2) Out.Add(At(L, FMath::Min(FMath::Max(Tail, 0.0) + 0.5, L.Len), Lat));
}

// Who goes first when paths cross: streets without a stop sign before stop-sign streets, faster streets before
// slower, and straight on before right turns before left turns (a turn gives way to the oncoming traffic).
int32 ASkysterTraffic::PrioOf(int32 LinkI, int32 NextI) const
{
	const FLink& L = Links[LinkI];
	const int32 Tn = TurnOf(LinkI, NextI);
	return (L.Ctrl == 2 ? 0 : 1) * 100 + FMath::Min(9, (int32)(L.V / 5.0)) * 10 + (Tn == 0 ? 2 : Tn > 0 ? 1 : 0);
}

// Room for the whole car on its lane past the junction box (so it never stops inside the box).
bool ASkysterTraffic::ExitRoom(int32 Self, bool bSkyLayer, int32 NextI, int32 InLane, double W, double Len) const
{
	const FLink& N = Links[NextI];
	const double Need = Len + 2.0 + N.EX;
	const double LatIn = N.O[FMath::Clamp(InLane, 0, N.O.Num() - 1)] * (bSkyLayer ? SKY_LANE : 1.0);
	if (!OnLink.IsValidIndex(NextI)) return true;
	for (int32 o : OnLink[NextI])
	{
		if (o == Self || !Cars.IsValidIndex(o)) continue;
		const FCar& O = Cars[o];
		if (O.Link != NextI || O.bSky != bSkyLayer || O.Fade > 0) continue;
		if (O.S < 0)
		{
			if (O.NextLane == InLane) return false;             // someone is crossing into the same lane
			continue;
		}
		if (FMath::Abs(O.Lat - LatIn) > (O.W + W) * 0.5 + 0.2) continue;
		if (O.S - O.Len * 0.5 < Need) return false;
	}
	return true;
}

// May a car (Self: its index, INDEX_NONE for the player's self-driving) take the crossing at the end of its link now?
// W_None when it may, else why not.
uint8 ASkysterTraffic::CanGo(int32 Self, bool bSkyLayer, int32 LinkI, int32 Lane, int32 NextI, int32 InLane, double W, double Len, double V,
	double YieldT, double ReqT, double QLen, const FPath& Mine, double T)
{
	const FLink& L = Links[LinkI];
	const int32 Node = L.B;
	if (!ExitRoom(Self, bSkyLayer, NextI, InLane, W, Len)) return W_Exit;
	// nobody inside the junction or holding a reservation on a path near mine
	if (const TArray<FOcc>* List = Occ.Find(Node * 2 + (bSkyLayer ? 1 : 0)))
	{
		for (const FOcc& O : *List)
		{
			if (O.Car == Self) continue;
			// the car ahead in my own lane, crossing the same way: following handles it
			if (O.From == LinkI && (O.FromLane == Lane || (O.bInside && O.To == NextI && O.ToLane == InLane))) continue;
			if (O.Req >= 0 && (ReqT < 0 || O.Req > ReqT)) continue;   // a later request doesn't hold me up
			if (PolyClose(Mine, O.Path, (O.W + W) * 0.5 + MARGIN)) return W_Conflict;
		}
	}
	// no body standing in the way (a car waiting with its nose in the box, a car stopped just past it)
	const auto Blocking = [&](int32 j) -> bool
	{
		if (j == LinkI || !OnLink.IsValidIndex(j)) return false;
		const FLink& Lj = Links[j];
		const double LatIn = Links[NextI].O[FMath::Clamp(InLane, 0, Links[NextI].O.Num() - 1)] * (bSkyLayer ? SKY_LANE : 1.0);
		for (int32 o : OnLink[j])
		{
			if (o == Self || !Cars.IsValidIndex(o)) continue;
			const FCar& O = Cars[o];
			if (O.Link != j || O.bSky != bSkyLayer || O.Fade > 0 || O.bInOcc) continue;
			if (j == NextI && O.S >= 0 && FMath::Abs(O.Lat - LatIn) < (O.W + W) * 0.5) continue;   // ahead in my exit lane: ExitRoom judged it
			if (O.S >= 0 && O.S - O.Len * 0.5 > Lj.EX + 12.0 && O.S + O.Len * 0.5 < Lj.Len - Lj.SB - 12.0) continue;   // mid-block, far away
			const FVector2D H = O.Dir * (O.Len * 0.5);
			if (PolySegClose(Mine, O.Pos - H, O.Pos + H, (O.W + W) * 0.5 + 0.3)) return true;
		}
		return false;
	};
	if (const TArray<int32>* In = NodeIn.Find(Node)) for (int32 j : *In) if (Blocking(j)) return W_Conflict;
	if (const TArray<int32>* Out = NodeOut.Find(Node)) for (int32 j : *Out) if (Blocking(j)) return W_Conflict;
	if (Self != INDEX_NONE && Player.bOn && Player.bSky == bSkyLayer)
	{
		const FVector2D H = Player.D * (Player.Len * 0.5);
		if (PolySegClose(Mine, Player.P - H, Player.P + H, (Player.W + W) * 0.5 + 0.5)) return W_Player;
	}
	// waited long enough: no more giving way to the stream (the request makes the others leave a gap)
	if (YieldT > REQ_AFTER) return W_None;
	// give way to cars with priority that will reach the junction before I'm across it
	const int32 MyP = PrioOf(LinkI, NextI);
	const double TGap = FMath::Clamp((QLen + Len + 4.0) / FMath::Max(V, 4.0), 2.5, 6.0);
	if (const TArray<int32>* In = NodeIn.Find(Node))
	{
		FPath Theirs;
		for (int32 j : *In)
		{
			if (j == LinkI || !OnLink.IsValidIndex(j)) continue;
			const FLink& Lj = Links[j];
			if (Lj.Ctrl == 2) continue;                              // it has to stop anyway
			for (int32 o : OnLink[j])
			{
				if (o == Self || !Cars.IsValidIndex(o)) continue;
				const FCar& O = Cars[o];
				if (O.Link != j || O.bSky != bSkyLayer || O.bCommit || O.S < 0 || O.Next < 0 || O.Fade > 0) continue;
				const double Ds = Lj.Len - Lj.SB - O.S;
				if (Ds > 70.0 || Ds < -0.5) continue;
				if (Lj.Ctrl == 1)
				{
					const int32 St = Signal(Lj.Unit, Lj.Group, T);
					if (St == 2 || (St == 1 && O.V * O.V / (2.0 * DEC) < Ds + 1.0)) continue;   // stopping for its light
				}
				if (PrioOf(j, O.Next) <= MyP) continue;
				if (Ds / FMath::Max(O.V, 2.0) > TGap) continue;
				MovePath(O, Theirs);
				if (PolyClose(Mine, Theirs, (O.W + W) * 0.5 + MARGIN)) return W_Yield;
			}
		}
	}
	// the player's self-driving car coming with priority
	if (Self != INDEX_NONE && !bSkyLayer && Fsd.bOn && !Fsd.bTurn && !Fsd.bCommit && Player.bOn && !Player.bSky && Links.IsValidIndex(Fsd.Link)
		&& Fsd.Link != LinkI && Links[Fsd.Link].B == Node && Fsd.RouteI + 1 < Fsd.Route.Num())
	{
		const FLink& Lf = Links[Fsd.Link];
		const double Ds = Lf.Len - Lf.SB - Fsd.S;
		const double Vf = Player.Vel.Size();
		const int32 NextF = Fsd.Route[Fsd.RouteI + 1];
		if (Lf.Ctrl != 2 && Ds < 70.0 && Ds > -0.5 && Ds / FMath::Max(Vf, 2.0) <= TGap && PrioOf(Fsd.Link, NextF) > MyP)
		{
			bool bComing = true;
			if (Lf.Ctrl == 1)
			{
				const int32 St = Signal(Lf.Unit, Lf.Group, T);
				bComing = !(St == 2 || (St == 1 && Vf * Vf / (2.0 * DEC) < Ds + 1.0));
			}
			if (bComing)
			{
				FsdTurnInto(NextF);                                   // the curve it will drive (the same as FsdStep plans)
				FPath Theirs;
				FsdMovePath(Theirs);
				if (PolyClose(Mine, Theirs, (Player.W + W) * 0.5 + MARGIN)) return W_Yield;
			}
		}
	}
	return W_None;
}

bool ASkysterTraffic::OccEntry(int32 Ci, int32& OutKey, FOcc& Out)
{
	const FCar& C = Cars[Ci];
	if (!Links.IsValidIndex(C.Link) || C.Fade > 0) return false;
	const int32 Sky = C.bSky ? 1 : 0;
	if (Inside(C))
	{
		Out.Car = Ci;
		Out.From = C.Prev;
		Out.FromLane = -1;
		Out.To = C.Link;
		Out.ToLane = C.NextLane;
		Out.W = C.W;
		Out.Req = -1;
		Out.bInside = true;
		InsidePath(C, Out.Path);
		OutKey = Links[C.Link].A * 2 + Sky;
		return true;
	}
	if ((C.bCommit || C.ReqT >= 0) && C.Next >= 0 && C.S >= 0)
	{
		Out.Car = Ci;
		Out.From = C.Link;
		Out.FromLane = C.Lane;
		Out.To = C.Next;
		Out.ToLane = C.InLane;
		Out.W = C.W;
		Out.Req = C.bCommit ? -1.0 : C.ReqT;
		Out.bInside = false;
		MovePath(C, Out.Path);
		OutKey = Links[C.Link].B * 2 + Sky;
		return true;
	}
	return false;
}

void ASkysterTraffic::RebuildOcc(double T)
{
	Occ.Reset();
	for (int32 c = 0; c < Cars.Num(); ++c)
	{
		Cars[c].bInOcc = false;
		int32 Key = 0;
		FOcc E;
		if (OccEntry(c, Key, E))
		{
			Occ.FindOrAdd(Key).Add(MoveTemp(E));
			Cars[c].bInOcc = true;
		}
	}
	AddFsdOcc();
}

void ASkysterTraffic::UpdateOcc(int32 Ci, int32 OldLink)
{
	FCar& C = Cars[Ci];
	const int32 Sky = C.bSky ? 1 : 0;
	const auto Remove = [&](int32 Node)
	{
		if (TArray<FOcc>* List = Occ.Find(Node * 2 + Sky)) List->RemoveAll([Ci](const FOcc& O) { return O.Car == Ci; });
	};
	if (Links.IsValidIndex(OldLink)) { Remove(Links[OldLink].A); Remove(Links[OldLink].B); }
	if (Links.IsValidIndex(C.Link) && C.Link != OldLink) { Remove(Links[C.Link].A); Remove(Links[C.Link].B); }
	C.bInOcc = false;
	int32 Key = 0;
	FOcc E;
	if (OccEntry(Ci, Key, E))
	{
		Occ.FindOrAdd(Key).Add(MoveTemp(E));
		C.bInOcc = true;
	}
}

// The player's self-driving car in the junction books, so the traffic gives way to it like to one of its own.
void ASkysterTraffic::AddFsdOcc()
{
	const FFsdState& F = Fsd;
	if (!F.bOn || !Links.IsValidIndex(F.Link) || !Player.bOn || Player.bSky) return;
	const FLink& L = Links[F.Link];
	FOcc E;
	E.Car = INDEX_NONE;
	E.W = Player.W;
	if (F.bTurn && Links.IsValidIndex(F.Next))
	{
		const double U0 = FMath::Clamp(F.U - (Player.Len * 0.5 + 0.5) / F.TurnLen, 0.0, 1.0);
		for (int32 k = 0; k <= 6; ++k) E.Path.Add(Bez(F.P0, F.P1, F.P2, U0 + (1.0 - U0) * k / 6.0, nullptr));
		const FLink& N = Links[F.Next];
		if (N.EX > 0.5) E.Path.Add(At(N, N.EX, FsdLaneOff(N, F.NextLane)));
		E.From = F.Link;
		E.To = F.Next;
		E.ToLane = F.NextLane;
		E.bInside = true;
		Occ.FindOrAdd(L.B * 2).Add(MoveTemp(E));
		return;
	}
	if (F.RouteI > 0 && F.S - Player.Len * 0.5 < L.EX + 0.5)
	{
		const double Lat = FsdLaneOff(L, F.FromLane);
		E.Path.Add(At(L, FMath::Max(0.0, F.S - Player.Len * 0.5 - 0.5), Lat));
		E.Path.Add(At(L, FMath::Min(L.Len, FMath::Max(L.EX, F.S + Player.Len * 0.5)), Lat));
		E.From = F.Route[F.RouteI - 1];
		E.To = F.Link;
		E.ToLane = F.FromLane;
		E.bInside = true;
		Occ.FindOrAdd(L.A * 2).Add(MoveTemp(E));
		return;
	}
	if ((F.bCommit || F.ReqT >= 0) && Links.IsValidIndex(F.Next))
	{
		FsdMovePath(E.Path);
		E.From = F.Link;
		E.FromLane = F.Lane;
		E.To = F.Next;
		E.ToLane = F.NextLane;
		E.Req = F.bCommit ? -1.0 : F.ReqT;
		Occ.FindOrAdd(L.B * 2).Add(MoveTemp(E));
	}
}

// ------------------------------------------------------------------------------------------------ bodies

int64 ASkysterTraffic::GKey(const FVector2D& P, bool bSkyLayer)
{
	const int64 X = FMath::FloorToInt64(P.X / CELL), Y = FMath::FloorToInt64(P.Y / CELL);
	return ((X & 0x3FFFFFFF) << 32) | ((Y & 0x3FFFFFFF) << 1) | (bSkyLayer ? 1 : 0);
}

void ASkysterTraffic::BuildGrid()
{
	Grid.Reset();
	for (int32 c = 0; c < Cars.Num(); ++c)
	{
		if (Cars[c].Link >= 0) Grid.FindOrAdd(GKey(Cars[c].Pos, Cars[c].bSky)).Add(c);
	}
}

void ASkysterTraffic::GridMove(int32 Ci, const FVector2D& OldPos)
{
	const FCar& C = Cars[Ci];
	const int64 K0 = GKey(OldPos, C.bSky), K1 = GKey(C.Pos, C.bSky);
	if (K0 == K1) return;
	if (TArray<int32>* A = Grid.Find(K0)) A->RemoveSingleSwap(Ci);
	Grid.FindOrAdd(K1).AddUnique(Ci);
}

// Would the body at NP/ND overlap another body (or the player's car) deeper than it does at OP/OD?
uint8 ASkysterTraffic::OverlapAny(int32 Ci, const FVector2D& NP, const FVector2D& ND, const FVector2D& OP, const FVector2D& OD) const
{
	const FCar& C = Cars[Ci];
	const double HL = C.Len * 0.5 + SHELL, HW = C.W * 0.5 + SHELL;
	for (int32 dx = -1; dx <= 1; ++dx)
	{
		for (int32 dy = -1; dy <= 1; ++dy)
		{
			const TArray<int32>* Cell = Grid.Find(GKey(NP + FVector2D(dx * CELL, dy * CELL), C.bSky));
			if (!Cell) continue;
			for (int32 o : *Cell)
			{
				if (o == Ci || !Cars.IsValidIndex(o)) continue;
				const FCar& O = Cars[o];
				if (O.Fade > 0 || O.bSky != C.bSky || O.Link < 0) continue;
				const double OHL = O.Len * 0.5 + SHELL, OHW = O.W * 0.5 + SHELL;
				const double Dn = ObbDepth(NP, ND, HL, HW, O.Pos, O.Dir, OHL, OHW);
				if (Dn <= 0) continue;
				if (Dn > ObbDepth(OP, OD, HL, HW, O.Pos, O.Dir, OHL, OHW) + 1e-4) return W_Hold;
			}
		}
	}
	if (Player.bOn && Player.bSky == C.bSky)
	{
		const double Dn = ObbDepth(NP, ND, HL, HW, Player.P, Player.D, Player.Len * 0.5, Player.W * 0.5);
		if (Dn > 0 && Dn > ObbDepth(OP, OD, HL, HW, Player.P, Player.D, Player.Len * 0.5, Player.W * 0.5) + 1e-4) return W_Player;
	}
	return W_None;
}

// The nearest body straight ahead of a nose (P, D: centre and heading, W, Len: its size) within Range m: the bumper
// gap, its speed along D, and how parallel it is. Self is skipped; the player's car too unless bWithPlayer.
double ASkysterTraffic::RayAhead(const FVector2D& P, const FVector2D& D, double W, double Len, double Range, bool bSkyLayer, int32 Self, bool bWithPlayer,
	double& OutV, double& OutDot, bool& bOutPlayer) const
{
	double Best = 1e9;
	OutV = 0;
	OutDot = 1;
	bOutPlayer = false;
	const FVector2D R = Right(D);
	const auto Test = [&](const FVector2D& OP, const FVector2D& OD, double OL, double OW, double OV, bool bP, const FVector2D& PVel)
	{
		const FVector2D Rel = OP - P;
		const double Lon = FVector2D::DotProduct(Rel, D);
		if (Lon <= 0 || Lon > Range + (OL + Len) * 0.5) return;
		const double Lat = FVector2D::DotProduct(Rel, R);
		const double Cd = FVector2D::DotProduct(OD, D), Cr = FVector2D::DotProduct(OD, R);
		const double Ext = FMath::Abs(Cr) * OL * 0.5 + FMath::Abs(Cd) * OW * 0.5;     // its half size across my heading
		if (FMath::Abs(Lat) > W * 0.5 + Ext + (bP ? 0.4 : 0.25)) return;
		const double G = Lon - Len * 0.5 - (FMath::Abs(Cd) * OL * 0.5 + FMath::Abs(Cr) * OW * 0.5) - (bP ? 0.5 : 0.0);
		if (G < Best)
		{
			Best = G;
			OutV = FMath::Max(0.0, bP ? FVector2D::DotProduct(PVel, D) : OV * Cd);
			OutDot = Cd;
			bOutPlayer = bP;
		}
	};
	const int32 NC = FMath::Clamp(FMath::CeilToInt32((Range + 8.0) / CELL), 1, 3);
	for (int32 dx = -NC; dx <= NC; ++dx)
	{
		for (int32 dy = -NC; dy <= NC; ++dy)
		{
			const TArray<int32>* Cell = Grid.Find(GKey(P + FVector2D(dx * CELL, dy * CELL), bSkyLayer));
			if (!Cell) continue;
			for (int32 o : *Cell)
			{
				if (o == Self || !Cars.IsValidIndex(o)) continue;
				const FCar& O = Cars[o];
				if (O.Fade > 0 || O.bSky != bSkyLayer || O.Link < 0) continue;
				Test(O.Pos, O.Dir, O.Len, O.W, O.V, false, FVector2D::ZeroVector);
			}
		}
	}
	if (bWithPlayer && Player.bOn && Player.bSky == bSkyLayer) Test(Player.P, Player.D, Player.Len, Player.W, 0.0, true, Player.Vel);
	return Best;
}

bool ASkysterTraffic::Visible(const FCar& C) const
{
	const FVector2D F(Focus.Y / 100.0, Focus.X / 100.0);
	const FVector2D Rel = C.Pos - F;
	const double D = Rel.Size();
	if (D > 250.0) return false;
	return FVector2D::DotProduct(Rel, CamFwd) > 0.3 * D;
}

// Deadlock relief: a car blocked for long (a car across its path that can't move, flaws in traffic.json, the player
// parked in its lane) goes elsewhere: at once out of sight, with a quick shrink in sight.
void ASkysterTraffic::Unstick(int32 Ci, double Dt)
{
	FCar& C = Cars[Ci];
	const bool bBlocked = C.Why == W_Hold || C.Why == W_Yield || C.Why == W_Conflict || C.Why == W_Exit || C.Why == W_Player || C.Why == W_Cross;
	if (C.V < 0.2 && bBlocked) C.Stuck += Dt;
	else if (C.V > 1.0) C.Stuck = 0;
	const bool bVis = Visible(C);
	// (waiting behind the player at a long red is fine: a minute in sight, 25 s out of sight, like any other block)
	const double Lim = bVis ? 60.0 : 25.0;
	if (C.Stuck <= Lim && C.Hold <= (bVis ? 20.0 : 8.0)) return;
	++StatRelocated;
	if (bVis)
	{
		C.Fade = 1e-3;
		UpdateOcc(Ci, C.Link);
		return;
	}
	const FVector2D Old = C.Pos;
	const int32 OldLink = C.Link;
	if (Place(C, C.bSky ? 200.0 : 140.0, C.bSky ? 650.0 : 450.0))
	{
		C.bPlaced = false;
		GridMove(Ci, Old);
		UpdateOcc(Ci, OldLink);
	}
	else C.Stuck = C.Hold = 0;
}

// The player's car as traffic sees it: where, which way, how big, how fast, and on which layer (street or sky lanes).
void ASkysterTraffic::UpdatePlayer(double Dt)
{
	Player.bOn = false;
	ASkysterCar* Car = Cast<ASkysterCar>(UGameplayStatics::GetPlayerPawn(this, 0));
	if (!Car)
	{
		Player.bHadPrev = false;
		return;
	}
	const FVector L = Car->GetActorLocation();
	const FVector2D P(L.Y / 100.0, L.X / 100.0);
	const double Z = L.Z / 100.0;
	const double Yaw = FMath::DegreesToRadians(Car->GetActorRotation().Yaw);
	Player.D = FVector2D(FMath::Sin(Yaw), FMath::Cos(Yaw));
	const int32 Veh = Car->GetVehicle();
	const FVector Sz = (Veh > 0 && Veh - 1 < (int32)UE_ARRAY_COUNT(SkyFleet::Cars)) ? SkyFleet::Cars[Veh - 1].Size : SkyFleet::ROADSTER;
	Player.Len = Sz.X / 100.0;
	Player.Speed = Car->GetSpeedMph() / 2.23694;
	Player.W = Sz.Y / 100.0;
	FVector2D Vel = FVector2D::ZeroVector;
	if (Player.bHadPrev)
	{
		Vel = (P - Player.Prev) / Dt;
		if (Vel.Size() > 120.0) Vel = FVector2D::ZeroVector;     // a teleport, not a speed
	}
	Player.Vel = Vel;
	Player.Prev = P;
	Player.bHadPrev = true;
	Player.P = P;
	if (Z > -4.0 && Z < 5.0) { Player.bOn = true; Player.bSky = false; }
	else if (FMath::Abs(Z - SkyHeight) < 5.0) { Player.bOn = true; Player.bSky = true; }
}

// The player ran into a car (the Roadster's own sweeps hit its box and do the damage): the car brakes to a stop,
// shoved a little by the hit, waits a few seconds and carries on. Pinned against the player, it shrinks away.
void ASkysterTraffic::PlayerContact(double Dt)
{
	for (int32 c = 0; c < Cars.Num(); ++c)
	{
		FCar& C = Cars[c];
		if (!Player.bOn || C.bSky != Player.bSky || C.Fade > 0 || C.Link < 0
			|| FMath::Abs(C.Pos.X - Player.P.X) > 12.0 || FMath::Abs(C.Pos.Y - Player.P.Y) > 12.0)
		{
			C.Pin = FMath::Max(0.0, C.Pin - Dt);
			continue;
		}
		if (ObbDepth(Player.P, Player.D, Player.Len * 0.5 + 0.35, Player.W * 0.5 + 0.35, C.Pos, C.Dir, C.Len * 0.5, C.W * 0.5) <= 0)
		{
			C.Pin = FMath::Max(0.0, C.Pin - Dt);
			continue;
		}
		const FVector2D VRel = Player.Vel - C.Dir * C.V;
		const double Into = FVector2D::DotProduct(VRel, (C.Pos - Player.P).GetSafeNormal());
		if (Into > 2.5 && C.Crash <= 0)
		{
			C.Crash = 3.5;
			C.ShoveV = FMath::Clamp(FVector2D::DotProduct(VRel, Right(C.Dir)) * 0.35, -4.0, 4.0);
			C.YawV = FMath::Clamp(-C.ShoveV * 10.0, -40.0, 40.0);
			const double Along = FVector2D::DotProduct(VRel, C.Dir);
			C.V = Along > 0 ? FMath::Min(C.V + Along * 0.3, 12.0) : 0.0;
			++StatCrashes;
		}
		// pinned: the player keeps pushing into it (a car parked against it, wheels still, doesn't count)
		if (Player.Speed > 0.5 || Into > 0.3) C.Pin += Dt;
		else C.Pin = FMath::Max(0.0, C.Pin - Dt * 0.5);
		if (C.Pin > 2.5)
		{
			++StatPinned;
			C.Pin = 0;
			C.Fade = 1e-3;
			UpdateOcc(c, C.Link);
		}
	}
}

// ------------------------------------------------------------------------------------------------ self-driving

double ASkysterTraffic::Project(const FLink& L, const FVector2D& P, double& OutLat) const
{
	double Best = 1e18, BestS = 0;
	OutLat = 0;
	for (int32 i = 0; i + 1 < L.P.Num(); ++i)
	{
		const FVector2D A = L.P[i], AB = L.P[i + 1] - L.P[i];
		const double Len2 = FMath::Max(AB.SizeSquared(), 1e-9);
		const double T = FMath::Clamp(FVector2D::DotProduct(P - A, AB) / Len2, 0.0, 1.0);
		const FVector2D Q = A + AB * T;
		const double D2 = FVector2D::DistSquared(P, Q);
		if (D2 < Best)
		{
			Best = D2;
			BestS = L.S[i] + FMath::Sqrt(Len2) * T;
			OutLat = FVector2D::DotProduct(P - Q, Right(AB.GetSafeNormal()));
		}
	}
	return BestS;
}

int32 ASkysterTraffic::TurnOf(int32 From, int32 To) const
{
	FVector2D T0, T1;
	At(Links[From], Links[From].Len, 0, &T0);
	At(Links[To], 0, 0, &T1);
	if (FVector2D::DotProduct(T0, T1) > 0.7) return 0;
	return (T0.X * T1.Y - T0.Y * T1.X) > 0 ? -1 : 1;
}

void ASkysterTraffic::FsdTurnInto(int32 NextLink)
{
	FFsdState& F = Fsd;
	const FLink& L = Links[F.Link];
	const FLink& N = Links[NextLink];
	F.Next = NextLink;
	const int32 Tn = TurnOf(F.Link, NextLink);
	F.NextLane = Tn < 0 ? 0 : Tn > 0 ? N.O.Num() - 1 : FMath::Clamp(F.Lane, 0, N.O.Num() - 1);
	FVector2D T0, T2;
	F.P0 = At(L, L.Len, FsdLaneOff(L, F.Lane), &T0);
	F.P2 = At(N, 0, FsdLaneOff(N, F.NextLane), &T2);
	F.P1 = (F.P0 + F.P2) * 0.5;
	const double Den = T0.X * T2.Y - T0.Y * T2.X;
	if (FMath::Abs(Den) > 0.15)
	{
		const FVector2D D = F.P2 - F.P0;
		const double A = (D.X * T2.Y - D.Y * T2.X) / Den, B = (D.X * T0.Y - D.Y * T0.X) / Den;
		if (A > 0 && A < 60 && B < 0 && B > -60) F.P1 = F.P0 + T0 * A;       // the corner (see MakeCurve)
	}
	double Len = 0;
	FVector2D Prev = F.P0;
	for (int32 k = 1; k <= 12; ++k) { const FVector2D Q = Bez(F.P0, F.P1, F.P2, k / 12.0, nullptr); Len += FVector2D::Distance(Prev, Q); Prev = Q; }
	F.TurnLen = FMath::Max(Len, 1.0);
}

// The self-driving car's planned crossing, like MovePath: stop line, curve, the box's far end.
void ASkysterTraffic::FsdMovePath(FPath& Out) const
{
	Out.Reset();
	const FFsdState& F = Fsd;
	if (!Links.IsValidIndex(F.Link) || !Links.IsValidIndex(F.Next)) return;
	const FLink& L = Links[F.Link];
	const FLink& N = Links[F.Next];
	Out.Add(At(L, FMath::Max(0.0, L.Len - L.SB), FsdLaneOff(L, F.Lane)));
	if (L.SB > 1.5) Out.Add(F.P0);
	for (int32 k = 1; k <= 8; ++k) Out.Add(Bez(F.P0, F.P1, F.P2, k / 8.0, nullptr));
	if (N.EX > 0.5) Out.Add(At(N, N.EX, FsdLaneOff(N, F.NextLane)));
}

// A destination and the quickest way there (Dijkstra over the lanes' links, time = length / speed limit): a charger
// 250 m to 2.5 km away by road when there is one, else somewhere 800 m to 2 km away.
bool ASkysterTraffic::FsdPlan()
{
	FFsdState& F = Fsd;
	const int32 N = Links.Num();
	TArray<double> Cost, Dist;
	TArray<int32> Prev;
	Cost.Init(1e18, N);
	Dist.Init(1e18, N);
	Prev.Init(-1, N);
	Cost[F.Link] = 0;
	Dist[F.Link] = Links[F.Link].Len - F.S;
	TArray<TPair<double, int32>> Heap;
	Heap.HeapPush(TPair<double, int32>(0.0, F.Link), [](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
	while (Heap.Num())
	{
		TPair<double, int32> Top;
		Heap.HeapPop(Top, [](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
		if (Top.Key > Cost[Top.Value]) continue;
		for (int32 j : Links[Top.Value].Next)
		{
			const double C = Top.Key + Links[j].Len / FMath::Max(Links[j].V, 3.0) + 2.0;
			if (C < Cost[j])
			{
				Cost[j] = C;
				Dist[j] = Dist[Top.Value] + Links[j].Len;
				Prev[j] = Top.Value;
				Heap.HeapPush(TPair<double, int32>(C, j), [](const TPair<double, int32>& A, const TPair<double, int32>& B) { return A.Key < B.Key; });
			}
		}
	}
	// the chargers' nearest lanes
	TArray<TPair<double, TPair<int32, double>>> Cands;   // (cost, (link, s))
	for (const FVector2D& G : F.Goals)
	{
		int32 BestL = -1;
		double BestD = 45.0, BestS = 0;
		for (int32 i = 0; i < N; ++i)
		{
			if (FVector2D::DistSquared(Links[i].Mid, G) > FMath::Square(Links[i].Len * 0.5 + 60.0)) continue;
			double Lat;
			const double S = Project(Links[i], G, Lat);
			const double D = FVector2D::Distance(At(Links[i], S, 0), G);
			if (D < BestD) { BestD = D; BestL = i; BestS = S; }
		}
		if (BestL >= 0 && Cost[BestL] < 1e17 && Dist[BestL] > 250.0 && Dist[BestL] < 2500.0) Cands.Add(TPair<double, TPair<int32, double>>(Cost[BestL], TPair<int32, double>(BestL, BestS)));
	}
	Cands.Sort([](const auto& A, const auto& B) { return A.Key < B.Key; });
	int32 Goal = -1;
	if (Cands.Num())
	{
		const auto& Pick = Cands[Rand.RandRange(0, FMath::Min(2, Cands.Num() - 1))];
		Goal = Pick.Value.Key;
		F.GoalS = FMath::Clamp(Pick.Value.Value, 5.0, Links[Goal].Len);
		F.DestName = FString::Printf(TEXT("Charger · %s"), Links[Goal].Name.IsEmpty() ? TEXT("nearby") : *Links[Goal].Name);
	}
	else
	{
		TArray<int32> Far;
		for (int32 i = 0; i < N; ++i) if (Cost[i] < 1e17 && Dist[i] > 800.0 && Dist[i] < 2000.0 && Links[i].Len > 40.0) Far.Add(i);
		if (Far.Num() == 0) return false;
		Goal = Far[Rand.RandRange(0, Far.Num() - 1)];
		F.GoalS = Links[Goal].Len * 0.5;
		F.DestName = Links[Goal].Name.IsEmpty() ? FString(TEXT("Across town")) : Links[Goal].Name;
	}
	F.Route.Reset();
	for (int32 i = Goal; i >= 0; i = Prev[i]) { F.Route.Insert(i, 0); if (i == F.Link) break; }
	if (F.Route.Num() == 0 || F.Route[0] != F.Link) return false;
	F.GoalLink = Goal;
	F.RouteI = 0;
	F.bArrived = false;
	F.ArriveT = 0;
	F.bCommit = false;
	F.YieldT = 0;
	F.ReqT = -1;
	if (F.Route.Num() > 1)
	{
		const int32 Tn = TurnOf(F.Link, F.Route[1]);
		const int32 Nl = Links[F.Link].O.Num();
		F.Lane = Tn < 0 ? 0 : Tn > 0 ? Nl - 1 : F.Lane;
	}
	return true;
}

bool ASkysterTraffic::FsdStart(const FVector& PosUE, double YawDeg, const TArray<FVector>& GoalsUE, FString& OutWhy)
{
	if (!IsReady()) { OutWhy = TEXT("no mapped streets on this map"); return false; }
	const FVector2D P(PosUE.Y / 100.0, PosUE.X / 100.0);
	const FVector2D H(FMath::Sin(FMath::DegreesToRadians(YawDeg)), FMath::Cos(FMath::DegreesToRadians(YawDeg)));
	int32 Best = -1;
	double BestD = 18.0, BestS = 0, BestLat = 0;
	for (int32 i = 0; i < Links.Num(); ++i)
	{
		const FLink& L = Links[i];
		if (FVector2D::DistSquared(L.Mid, P) > FMath::Square(L.Len * 0.5 + 30.0)) continue;
		double Lat;
		const double S = Project(L, P, Lat);
		if (S <= 0.5 || S >= L.Len - 0.5) continue;
		FVector2D T;
		At(L, S, 0, &T);
		if (FVector2D::DotProduct(T, H) < 0.5) continue;              // the way we're facing
		const double D = FMath::Abs(Lat) - (L.O.Last() - L.O[0]) * 0.5;
		if (D < BestD) { BestD = D; Best = i; BestS = S; BestLat = Lat; }
	}
	if (Best < 0) { OutWhy = TEXT("no mapped street lane under the car going this way"); return false; }
	Fsd = FFsdState();
	Fsd.Link = Best;
	Fsd.S = BestS;
	const FLink& L = Links[Best];
	int32 Lane = 0;
	for (int32 k = 1; k < L.O.Num(); ++k) if (FMath::Abs(L.O[k] - BestLat) < FMath::Abs(L.O[Lane] - BestLat)) Lane = k;
	Fsd.Lane = Fsd.FromLane = Lane;
	for (const FVector& G : GoalsUE) Fsd.Goals.Add(FVector2D(G.Y / 100.0, G.X / 100.0));
	if (!FsdPlan()) { OutWhy = TEXT("no route from here"); return false; }
	Fsd.FromLane = Lane;                                          // change lanes for the first turn over the next stretch
	Fsd.bOn = true;
	return true;
}

bool ASkysterTraffic::FsdStep(const FVector& PosUE, double YawDeg, double Speed, double Dt, FFsdStep& Out)
{
	FFsdState& F = Fsd;
	if (!F.bOn || !Links.IsValidIndex(F.Link)) return false;
	const FVector2D P(PosUE.Y / 100.0, PosUE.X / 100.0);
	const FVector2D H(FMath::Sin(FMath::DegreesToRadians(YawDeg)), FMath::Cos(FMath::DegreesToRadians(YawDeg)));
	const double T = GetWorld()->GetTimeSeconds();
	const double V = FMath::Max(Speed, 0.0);
	// a few seconds at the destination, then on to the next one
	if (F.bArrived)
	{
		Out.Look = P + H * 10.0;
		Out.VTarget = 0;
		Out.bArrived = true;
		Out.Hint = FString::Printf(TEXT("Arrived · %s"), *F.DestName);
		if ((F.ArriveT += Dt) > 4.0)
		{
			double Lat;
			F.S = Project(Links[F.Link], P, Lat);
			if (!FsdPlan()) return false;
		}
		return true;
	}
	const FLink* L = &Links[F.Link];
	auto LaneAt = [&](double S) { return FMath::Lerp(FsdLaneOff(*L, F.FromLane), FsdLaneOff(*L, F.Lane), FMath::SmoothStep(0.0, 30.0, S)); };
	if (!F.bTurn)
	{
		double Lat;
		F.S = Project(*L, P, Lat);
		if (FMath::Abs(Lat - LaneAt(F.S)) > 14.0) return false;
		if (F.Link == F.GoalLink && F.S >= F.GoalS - 3.0 && V < 2.0) { F.bArrived = true; F.ArriveT = 0; }
		if (F.S >= L->Len - 0.6)
		{
			if (F.RouteI + 1 >= F.Route.Num()) { F.bArrived = true; F.ArriveT = 0; return true; }
			FsdTurnInto(F.Route[F.RouteI + 1]);
			F.bTurn = true;
			F.U = 0;
		}
	}
	if (F.bTurn)
	{
		double BestU = F.U, BestD = 1e18;
		for (int32 k = 0; k <= 24; ++k)
		{
			const double U = k / 24.0;
			const double D = FVector2D::DistSquared(Bez(F.P0, F.P1, F.P2, U, nullptr), P);
			if (D < BestD) { BestD = D; BestU = U; }
		}
		F.U = FMath::Max(F.U, BestU);
		if (FMath::Sqrt(BestD) > 16.0) return false;
		if (F.U > 0.96)
		{
			F.RouteI++;
			F.Link = F.Next;
			F.FromLane = F.NextLane;
			F.Lane = F.NextLane;
			if (F.RouteI + 1 < F.Route.Num())
			{
				const int32 Tn = TurnOf(F.Link, F.Route[F.RouteI + 1]);
				const int32 Nl = Links[F.Link].O.Num();
				F.Lane = Tn < 0 ? 0 : Tn > 0 ? Nl - 1 : FMath::Clamp(F.FromLane, 0, Nl - 1);
			}
			F.bTurn = false;
			F.bServed = false;
			F.Wait = 0;
			F.bCommit = false;                                       // across: the next junction is a new decision
			F.YieldT = 0;
			F.ReqT = -1;
			L = &Links[F.Link];
			double Lat;
			F.S = FMath::Max(0.0, Project(*L, P, Lat));
		}
	}
	// the look-ahead point along the path: this lane, the curve across the junction, the next lane
	const double Ld = FMath::Clamp(5.0 + 0.45 * V, 7.0, 28.0);
	const bool bHasNext = F.RouteI + 1 < F.Route.Num();
	if (F.bTurn)
	{
		const double Rem = (1.0 - F.U) * F.TurnLen;
		if (Ld <= Rem) Out.Look = Bez(F.P0, F.P1, F.P2, F.U + Ld / F.TurnLen, nullptr);
		else { const FLink& Nx = Links[F.Next]; Out.Look = At(Nx, Ld - Rem, FsdLaneOff(Nx, F.NextLane)); }
	}
	else
	{
		const double Rem = L->Len - F.S;
		if (Ld <= Rem || !bHasNext) Out.Look = At(*L, F.S + Ld, LaneAt(F.S + Ld));
		else
		{
			FsdTurnInto(F.Route[F.RouteI + 1]);                          // where the curve will go (recomputed at the end)
			const double Left = Ld - Rem;
			if (Left <= F.TurnLen) Out.Look = Bez(F.P0, F.P1, F.P2, Left / F.TurnLen, nullptr);
			else { const FLink& Nx = Links[F.Next]; Out.Look = At(Nx, Left - F.TurnLen, FsdLaneOff(Nx, F.NextLane)); }
		}
	}
	// target speed: the limit, slower into turns, stop for signals and stop signs, take junctions by the traffic's
	// rules, follow the car ahead, ease to a stop
	double VT = L->V;
	const auto Brake = [](double D, double Dec) { return FMath::Sqrt(2.0 * Dec * FMath::Max(D, 0.0)); };
	if (F.bTurn) VT = FMath::Min(VT, 9.0);
	else
	{
		const double ToEnd = L->Len - F.S;
		if (bHasNext && TurnOf(F.Link, F.Route[F.RouteI + 1]) != 0) VT = FMath::Min(VT, FMath::Sqrt(64.0 + 2.0 * 2.5 * FMath::Max(ToEnd - 4.0, 0.0)));
		const double DStop = ToEnd - L->SB;
		bool bCtrlStop = false;
		if (L->Ctrl != 0 && DStop > -1.0 && !F.bCommit)
		{
			if (L->Ctrl == 1)
			{
				const int32 St = Signal(L->Unit, L->Group, T);
				bCtrlStop = St == 2 || (St == 1 && V * V / (2.0 * 3.5) < DStop + 1.0);
			}
			else if (!F.bServed)
			{
				bCtrlStop = true;
				if (DStop < 4.0 && V < 0.6 && (F.Wait += Dt) > 1.3) { F.bServed = true; bCtrlStop = false; }
			}
			if (bCtrlStop) VT = FMath::Min(VT, Brake(DStop - 0.5, 3.0));
		}
		// the right to cross: reserve the crossing when nothing conflicts, else wait at the line like the traffic
		if (bHasNext && !F.bCommit && !bCtrlStop && DStop <= V * V / (2.0 * DEC) + 4.0 + V * 0.5)
		{
			FsdTurnInto(F.Route[F.RouteI + 1]);
			const double MyLat = LaneAt(F.S);
			bool bFirst = true;
			for (const FCar& O : Cars)
			{
				if (!O.bSky && O.Link == F.Link && O.S > F.S && !O.bCommit && O.Fade <= 0 && FMath::Abs(O.Lat - MyLat) < (O.W + Player.W) * 0.5) { bFirst = false; break; }
			}
			uint8 R = W_Car;
			if (bFirst)
			{
				FPath Mine;
				FsdMovePath(Mine);
				R = CanGo(INDEX_NONE, false, F.Link, F.Lane, F.Next, F.NextLane, Player.W, Player.Len, V, F.YieldT, F.ReqT, F.TurnLen, Mine, T);
			}
			if (R == W_None) { F.bCommit = true; F.CommitT = T; F.ReqT = -1; }
			else
			{
				VT = FMath::Min(VT, Brake(DStop - 0.5, 3.0));
				if (V < 0.5)
				{
					F.YieldT += Dt;
					if (F.YieldT > REQ_AFTER && F.ReqT < 0) F.ReqT = T;
				}
			}
		}
		if (F.Link == F.GoalLink) VT = FMath::Min(VT, Brake(F.GoalS - F.S - 1.0, 2.5));
	}
	// the car ahead, across this lane (or turning into it), or just into the next link of the route
	const double MyLatNow = F.bTurn ? 0.0 : LaneAt(F.S);
	for (const FCar& O : Cars)
	{
		if (O.bSky || O.Fade > 0) continue;
		double Gap = 1e9;
		if (O.Link == F.Link && !F.bTurn && O.S > F.S && (O.S < 0 || FMath::Abs(O.Lat - MyLatNow) < (O.W + Player.W) * 0.5 + 0.2)) Gap = O.S - F.S;
		else if (bHasNext && O.Link == F.Route[F.RouteI + 1] && O.S < 40.0) Gap = (F.bTurn ? (1.0 - F.U) * F.TurnLen : (L->Len - F.S) + F.TurnLen) + O.S;
		if (Gap > 80.0) continue;
		Gap -= O.Len * 0.5 + 2.4 + 3.0;
		VT = FMath::Min(VT, FMath::Sqrt(FMath::Max(0.0, O.V * O.V + 2.0 * 3.0 * (Gap - 0.8 * V))));
	}
	// and any body straight ahead (crossing traffic, short links, bends)
	{
		double RV = 0, RDot = 1;
		bool bRP = false;
		const double G = RayAhead(P, H, Player.W, Player.Len, FMath::Max(8.0, V * 1.5 + 6.0), false, INDEX_NONE, false, RV, RDot, bRP);
		if (G < 1e8) VT = FMath::Min(VT, FMath::Sqrt(FMath::Max(0.0, RV * RV + 2.0 * 3.0 * (G - JAM - 0.8 * V))));
	}
	Out.VTarget = FMath::Max(0.0, VT);
	// what's next, the way the car's screen would say it
	double Left = F.bTurn ? 0.0 : L->Len - F.S;
	for (int32 i = F.RouteI + 1; i < F.Route.Num(); ++i) Left += (i + 1 == F.Route.Num()) ? F.GoalS : Links[F.Route[i]].Len;
	if (F.Link == F.GoalLink) Left = FMath::Max(0.0, F.GoalS - F.S);
	Out.DistLeft = Left;
	if (bHasNext && !F.bTurn)
	{
		const FLink& Nx = Links[F.Route[F.RouteI + 1]];
		const int32 Tn = TurnOf(F.Link, F.Route[F.RouteI + 1]);
		const FString Street = Nx.Name.IsEmpty() ? FString(TEXT("the next street")) : Nx.Name;
		const FString Dist = FString::Printf(TEXT("%d m"), (int32)(FMath::RoundToInt((L->Len - F.S) / 10.0) * 10));
		if (Tn == 0 && Nx.Name == L->Name) Out.Hint = FString::Printf(TEXT("Continue on %s"), *Street);
		else Out.Hint = FString::Printf(TEXT("%s %s · %s"), Tn < 0 ? TEXT("Turn left onto") : Tn > 0 ? TEXT("Turn right onto") : TEXT("Continue onto"), *Street, *Dist);
	}
	else Out.Hint = F.Link == F.GoalLink ? FString::Printf(TEXT("Arriving · %s"), *F.DestName) : FString::Printf(TEXT("Continue on %s"), L->Name.IsEmpty() ? TEXT("this street") : *L->Name);
	return true;
}

void ASkysterTraffic::FsdRoute(TArray<FVector2D>& Out) const
{
	Out.Reset();
	const FFsdState& F = Fsd;
	if (!F.bOn || !Links.IsValidIndex(F.Link)) return;
	if (F.bTurn)
	{
		for (int32 k = FMath::FloorToInt(F.U * 8); k <= 8; ++k) Out.Add(Bez(F.P0, F.P1, F.P2, k / 8.0, nullptr));
	}
	for (int32 i = F.RouteI + (F.bTurn ? 1 : 0); i < F.Route.Num(); ++i)
	{
		const FLink& L = Links[F.Route[i]];
		const double S0 = (i == F.RouteI && !F.bTurn) ? F.S : 0.0;
		const double S1 = (F.Route[i] == F.GoalLink) ? F.GoalS : L.Len;
		Out.Add(At(L, S0, 0));
		for (int32 k = 0; k < L.P.Num(); ++k) if (L.S[k] > S0 && L.S[k] < S1) Out.Add(L.P[k]);
		Out.Add(At(L, S1, 0));
	}
}
