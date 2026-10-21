#include "SkysterProgress.h"

#include "Kismet/GameplayStatics.h"
#include "SkysterCar.h"

static const TCHAR* SLOT = TEXT("Skyster");

static FString UnlockText(const FString& What)
{
	if (What == TEXT("boost")) return TEXT("Boost unlocks at level 3 · Thrusters");
	if (What == TEXT("airbrake")) return TEXT("The air brake (LT in the air) unlocks at level 3 · Thrusters");
	if (What == TEXT("doubleJump")) return TEXT("Double jumps and flips unlock at level 2 · Sport");
	if (What == TEXT("walls")) return TEXT("Wall riding unlocks at level 4 · Fans");
	if (What == TEXT("hover")) return TEXT("Hover unlocks at level 5 · Plaid");
	if (What == TEXT("flight")) return TEXT("Flight unlocks at level 6 · Rocket");
	return TEXT("Not unlocked yet");
}

void FSkyProgress::Load()
{
	if (const USkysterSave* S = Cast<USkysterSave>(UGameplayStatics::LoadGameFromSlot(SLOT, 0)))
	{
		Level = FMath::Clamp(S->Level, 0, Skyster::NumLevels - 1);
		Earned = FMath::Clamp(S->Earned, 0, Skyster::NumLevels - 1);
		Done = TSet<FString>(S->Done);
		Owned = TSet<FString>(S->Addons);
	}
}

void FSkyProgress::Save() const
{
	USkysterSave* S = Cast<USkysterSave>(UGameplayStatics::CreateSaveGameObject(USkysterSave::StaticClass()));
	if (!S) return;
	S->Level = Level;
	S->Earned = Earned;
	S->Done = Done.Array();
	S->Addons = Owned.Array();
	UGameplayStatics::SaveGameToSlot(S, SLOT, 0);
}

void FSkyProgress::SetLevel(int32 I, ASkysterCar& Car)
{
	Level = (I % Skyster::NumLevels + Skyster::NumLevels) % Skyster::NumLevels;
	Best.Reset();
	RunDriftT = RunWallT = 0;
	Car.ApplyCaps(Skyster::CapsFor(Level));
	Save();
}

void FSkyProgress::Reset(ASkysterCar& Car)
{
	Earned = 0;
	Done.Reset();
	SetLevel(0, Car);
}

bool FSkyProgress::Met(const FSkyGoal& G) const
{
	const double* X = Best.Find(G.Stat);
	if (!X) return false;
	return G.bMin ? *X <= G.Target : *X >= G.Target;
}

double FSkyProgress::FuelMult() const
{
	double M = 1;
	for (const Skyster::FAddon& A : Skyster::Addons) if (Owned.Contains(A.Id)) M *= A.Mult;
	return M;
}

FString FSkyProgress::BestAddon() const
{
	FString B;
	for (const Skyster::FAddon& A : Skyster::Addons) if (Owned.Contains(A.Id)) B = A.Id;
	return B;
}

bool FSkyProgress::Grant(const FString& Id)
{
	if (Owned.Contains(Id)) return false;
	Owned.Add(Id);
	Save();
	return true;
}

// The car's own events plus a look at its state, once per frame while playing.
void FSkyProgress::Update(double Dt, ASkysterCar& Car)
{
	auto Up = [this](const FString& K, double X) { double* B = Best.Find(K); if (!B) Best.Add(K, X); else if (X > *B) *B = X; };
	Up(TEXT("mph"), Car.GetSpeedMph());
	if (Car.bGrounded && Car.bDrifting) RunDriftT += Dt; else RunDriftT = 0;
	Up(TEXT("driftT"), RunDriftT);
	if (Car.bGrounded && Car.Sup.Kind != ASkysterCar::ESurface::Ground) RunWallT += Dt; else RunWallT = 0;
	Up(TEXT("wallT"), RunWallT);
	if (!Car.bGrounded) Up(TEXT("height"), Car.Pos.Z - Car.GroundY);
	for (const FSkyEvent& E : Car.Events)
	{
		switch (E.Type)
		{
		case ESkyEv::Move: Up(E.Name, Best.FindRef(E.Name) + 1); break;
		case ESkyEv::Pad: Up(TEXT("pads"), Best.FindRef(TEXT("pads")) + 1); break;
		case ESkyEv::Touchdown: if (E.Name == TEXT("ground")) Up(TEXT("airT"), Car.Jump.AirT); break;
		case ESkyEv::Combo: if (E.Name == TEXT("landed")) Up(TEXT("combo"), E.I); break;
		case ESkyEv::Sixty: { double* B = Best.Find(TEXT("sixty")); if (!B) Best.Add(TEXT("sixty"), E.A); else if (E.A < *B) *B = E.A; break; }
		case ESkyEv::Locked:
		{
			const double Now = Car.SimTime;
			const double* Last = LockToastT.Find(E.Name);
			if (!Last || Now - *Last >= 6.0)
			{
				LockToastT.Add(E.Name, Now);
				Car.Toast(UnlockText(E.Name), FString::Printf(TEXT("you're at level %d · %s · Menu > D-pad to test any level"), Level + 1, Current().Name));
			}
			break;
		}
		default: break;
		}
	}
	// challenges
	const FSkyLevel& L = Current();
	bool bFresh = false;
	for (int32 i = 0; i < L.NumGoals; ++i)
	{
		const FSkyGoal& G = L.Goals[i];
		if (Done.Contains(G.Id) || !Met(G)) continue;
		Done.Add(G.Id);
		bFresh = true;
		Car.Toast(TEXT("Challenge done"), G.Text);
	}
	if (bFresh)
	{
		Save();
		bool bAll = true;
		for (int32 i = 0; i < L.NumGoals; ++i) bAll &= Done.Contains(L.Goals[i].Id);
		if (bAll && Level + 1 < Skyster::NumLevels)
		{
			Earned = FMath::Max(Earned, Level + 1);
			PendingLevel = Level + 1;
			PendingT = 1.6;
		}
	}
	if (PendingLevel >= 0 && (PendingT -= Dt) <= 0)
	{
		const int32 N = PendingLevel;
		PendingLevel = -1;
		SetLevel(N, Car);
		Car.Toast(FString::Printf(TEXT("Level %d unlocked: %s"), N + 1, Skyster::Levels[N].Name), Skyster::Levels[N].Blurb);
	}
}
