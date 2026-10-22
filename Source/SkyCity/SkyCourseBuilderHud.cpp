// Everything the Course Builder draws on the canvas: the info panel, toasts, warnings, the palette strip with its icons,
// the settings of the piece about to be placed, the fit banner, the hint line, the menus and the driving hint.
// Same look as the car's HUD (SkysterHUD.cpp): Roboto, S = ClipY / 1080, white on dark glass with cyan for "selected".
#include "SkyCourseBuilderImpl.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Font.h"
#include "GameFramework/HUD.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Paths.h"
#include "SkysterCar.h"
#include "GlobalRenderResources.h"
#include "TextureResource.h"

using namespace SkyBuilder;

static const FLinearColor Ink(1.f, 1.f, 1.f, 0.95f);
static const FLinearColor Dim(0.75f, 0.85f, 1.f, 0.8f);
static const FLinearColor Faint(0.75f, 0.85f, 1.f, 0.45f);
static const FLinearColor Back(0.02f, 0.03f, 0.05f, 0.74f);
static constexpr float TS = 1.12f;   // text a little larger than the car HUD's: this one is read at arm's length from a sofa
static const FLinearColor Green(0.35f, 1.f, 0.55f, 0.95f);
static const FLinearColor Gold(1.f, 0.82f, 0.35f, 0.95f);
static const FLinearColor Red(1.f, 0.4f, 0.32f, 0.97f);
static const FLinearColor Cyan(0.25f, 0.88f, 1.f, 0.95f);

// ============================================================================================ small drawing helpers

void FSkyCourseBuilderImpl::Text(const FString& T, float X, float Y, float Size, const FLinearColor& Col, int32 Align)
{
	float W = 0, H = 0;
	Size *= TS;
	if (Align != 0) Hud->GetTextSize(T, W, H, Font.Get(), Size);
	Hud->DrawText(T, Col, Align == 2 ? X - W : Align == 1 ? X - W * 0.5f : X, Y, Font.Get(), Size);
}

float FSkyCourseBuilderImpl::TextW(const FString& T, float Size)
{
	float W = 0, H = 0;
	Hud->GetTextSize(T, W, H, Font.Get(), Size * TS);
	return W;
}

void FSkyCourseBuilderImpl::Panel(float X, float Y, float W, float H, const FLinearColor& Col)
{
	Hud->DrawRect(Col, X, Y, W, H);
}

void FSkyCourseBuilderImpl::Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float W)
{
	Hud->DrawLine(X0, Y0, X1, Y1, Col, W);
}

void FSkyCourseBuilderImpl::Poly(const TArray<FVector2D>& Pts, const FLinearColor& Col, float W, bool bClose)
{
	for (int32 i = 0; i + 1 < Pts.Num(); ++i) Line(Pts[i].X, Pts[i].Y, Pts[i + 1].X, Pts[i + 1].Y, Col, W);
	if (bClose && Pts.Num() > 2) Line(Pts.Last().X, Pts.Last().Y, Pts[0].X, Pts[0].Y, Col, W);
}

void FSkyCourseBuilderImpl::Tri(const FVector2D& A, const FVector2D& B, const FVector2D& C, const FLinearColor& Col)
{
	FCanvasTriangleItem T(A, B, C, GWhiteTexture);
	T.SetColor(Col);
	T.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(T);
}

// a button name on a small dark chip; returns its width
void FSkyCourseBuilderImpl::Key(const FString& Label, float X, float Y, float H, const FLinearColor& Col, float* OutW)
{
	const float Tw = TextW(Label, 0.72f * S);
	const float W = Tw + 18.f * S;
	Panel(X, Y, W, H, FLinearColor(0.f, 0.f, 0.f, 0.55f));
	Line(X, Y, X + W, Y, Faint, 1.f);
	Line(X, Y + H, X + W, Y + H, Faint, 1.f);
	Line(X, Y, X, Y + H, Faint, 1.f);
	Line(X + W, Y, X + W, Y + H, Faint, 1.f);
	float Tw2 = 0, Th2 = 0;
	Hud->GetTextSize(Label, Tw2, Th2, Font.Get(), 0.72f * S * TS);
	Text(Label, X + W * 0.5f, Y + (H - Th2) * 0.5f, 0.72f * S, Col, 1);
	if (OutW) *OutW = W;
}

// ============================================================================================ entry

void FSkyCourseBuilderImpl::DrawHud(AHUD* InHud, UCanvas* InCanvas, float InS)
{
	Hud = InHud;
	Canvas = InCanvas;
	S = InS;
	if (!Hud || !Canvas) return;
	if (!Font.IsValid()) Font.Reset(LoadObject<UFont>(nullptr, TEXT("/Engine/EngineFonts/Roboto.Roboto")));
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode || !Font.IsValid()) return;
	if (Mode->IsDriving()) { DrawDriving(); return; }
	if (!bWasActive) return;
	DrawBuild();
	switch (Screen)
	{
	case EBuilderScreen::Menu: DrawMenu(); break;
	case EBuilderScreen::Load: DrawLoad(); break;
	case EBuilderScreen::Name: DrawName(); break;
	case EBuilderScreen::Garage: DrawGarage(); break;
	default: break;
	}
	DrawToasts();
}

void FSkyCourseBuilderImpl::DrawBuild()
{
	DrawInfo();
	DrawWarnings();
	DrawPalette();
}

// ============================================================================================ top left: the course

void FSkyCourseBuilderImpl::DrawInfo()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const FSkyCourse& C = Mode->GetCourse();
	const FSkyBaked& B = Mode->GetBaked();
	const float X = 40.f * S, Y = 34.f * S, W = 560.f * S;
	const bool bBranch = P->EditSeq != 0;
	Panel(X - 14.f * S, Y - 10.f * S, W + 28.f * S, 156.f * S, Back);
	Text(C.Name.ToUpper(), X, Y, 1.25f * S, Ink);
	const FString Kind = B.bValid ? (B.bLapCourse ? FString::Printf(TEXT("lap course · %d lap%s"), C.Laps, C.Laps == 1 ? TEXT("") : TEXT("s")) : FString(TEXT("point to point"))) : FString(TEXT("not baked"));
	Text(FString::Printf(TEXT("%d pieces · %d m · %s"), B.PieceCount, FMath::RoundToInt(B.Length), *Kind), X, Y + 34.f * S, 0.8f * S, Dim);
	Text(FString::Printf(TEXT("%d lane%s at the cursor · skin %s · %d opponent%s"), CursorLanes, CursorLanes == 1 ? TEXT("") : TEXT("s"), SkyCourse::SkinName(C.Skin), C.Opponents, C.Opponents == 1 ? TEXT("") : TEXT("s")), X, Y + 60.f * S, 0.72f * S, Faint);
	Text(TEXT("EDITING"), X, Y + 90.f * S, 0.72f * S, Faint);
	Text(SeqLabel(C, B, P->EditSeq), X + 82.f * S, Y + 88.f * S, 0.85f * S, bBranch ? Gold : Cyan);
	if (Mode->IsMcpEnabled()) Text(TEXT("LLM LINK ON"), X + W, Y + 4.f * S, 0.72f * S, Green, 2);
}

// ============================================================================================ top right: warnings

void FSkyCourseBuilderImpl::DrawWarnings()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	TArray<FString> Worth;
	for (const FString& Wn : Mode->GetBaked().Warnings) if (!IsRoutineWarning(Wn)) Worth.Add(Wn);
	if (Worth.Num() == 0) return;
	const float W = 520.f * S, X = Canvas->ClipX - W - 40.f * S;
	float Y = 34.f * S;
	const int32 N = FMath::Min(Worth.Num(), 4);
	Panel(X - 14.f * S, Y - 10.f * S, W + 28.f * S, (44.f + N * 26.f) * S, Back);
	Text(FString::Printf(TEXT("HEADS UP · %d"), Worth.Num()), X, Y, 0.85f * S, Gold);
	Y += 32.f * S;
	for (int32 i = 0; i < N; ++i)
	{
		FString T = Worth[i];
		while (T.Len() > 8 && TextW(T, 0.72f * S) > W) T = T.Left(T.Len() - 4) + TEXT("...");
		Text(T, X, Y, 0.72f * S, Dim);
		Y += 26.f * S;
	}
}

// ============================================================================================ top centre: toasts

void FSkyCourseBuilderImpl::DrawToasts()
{
	float Y = 34.f * S;
	const float Cx = Canvas->ClipX * 0.5f;
	for (int32 i = Toasts.Num() - 1; i >= 0; --i)
	{
		const FToast& T = Toasts[i];
		const double Age = Time - T.Born;
		if (Age > 6.0 || Age < 0) continue;
		const float A = (float)FMath::Clamp(6.0 - Age, 0.0, 1.0);
		const float W = FMath::Min(Canvas->ClipX - 80.f * S, FMath::Max(TextW(T.Title, 1.1f * S), TextW(T.Sub, 0.8f * S)) + 44.f * S);
		const float H = (T.Sub.IsEmpty() ? 42.f : 68.f) * S;
		Panel(Cx - W * 0.5f, Y, W, H, FLinearColor(0.02f, 0.03f, 0.05f, 0.72f * A));
		Panel(Cx - W * 0.5f, Y, 5.f * S, H, T.bBad ? FLinearColor(Red.R, Red.G, Red.B, A) : FLinearColor(Cyan.R, Cyan.G, Cyan.B, A));
		Text(T.Title, Cx, Y + 7.f * S, 1.1f * S, FLinearColor(1, 1, 1, 0.95f * A), 1);
		if (!T.Sub.IsEmpty())
		{
			FString Sub = T.Sub;
			while (Sub.Len() > 8 && TextW(Sub, 0.8f * S) > W - 30.f * S) Sub = Sub.Left(Sub.Len() - 4) + TEXT("...");
			Text(Sub, Cx, Y + 38.f * S, 0.8f * S, FLinearColor(0.75f, 0.85f, 1.f, 0.88f * A), 1);
		}
		Y += H + 8.f * S;
		if (Y > Canvas->ClipY * 0.35f) break;
	}
}

// ============================================================================================ the palette

void FSkyCourseBuilderImpl::DrawIcon(ESkyPiece Type, float Cx, float Cy, float Sz, const FLinearColor& Col)
{
	// shapes drawn in a -1..1 box (v up), a few lines each
	auto Pt = [&](double U, double V) { return FVector2D(Cx + U * Sz, Cy - V * Sz); };
	const float Th = FMath::Max(1.6f, 2.4f * S);
	const FLinearColor Soft(Col.R, Col.G, Col.B, Col.A * 0.4f);
	auto Arc = [&](double Ux, double Vy, double R, double A0, double A1, int32 N, TArray<FVector2D>& Out)
	{
		for (int32 i = 0; i <= N; ++i)
		{
			const double A = FMath::DegreesToRadians(A0 + (A1 - A0) * i / N);
			Out.Add(Pt(Ux + R * FMath::Cos(A), Vy + R * FMath::Sin(A)));
		}
	};
	TArray<FVector2D> L;
	switch (Type)
	{
	case ESkyPiece::Straight:
		Poly({ Pt(-0.4, -1), Pt(-0.4, 1) }, Soft, Th);
		Poly({ Pt(0.4, -1), Pt(0.4, 1) }, Soft, Th);
		Poly({ Pt(0, -1), Pt(0, 1) }, Col, Th);
		break;
	case ESkyPiece::Curve:
		Arc(0.9, -0.9, 1.3, 180, 90, 10, L);
		Poly(L, Col, Th);
		break;
	case ESkyPiece::Ramp:
		for (int32 i = 0; i <= 14; ++i)
		{
			const double U = -1.0 + 2.0 * i / 14, T = FMath::Clamp((U + 0.45) / 0.9, 0.0, 1.0);
			L.Add(Pt(U, -0.45 + 0.9 * (T * T * (3 - 2 * T))));
		}
		Poly(L, Col, Th);
		break;
	case ESkyPiece::Jump:
		Poly({ Pt(-1, -0.55), Pt(-0.35, -0.55), Pt(-0.05, -0.1) }, Col, Th);
		Poly({ Pt(0.45, -0.1), Pt(1, -0.1) }, Col, Th);
		Poly({ Pt(-0.05, -0.1), Pt(0.45, -0.1) }, Soft, Th);
		Poly({ Pt(0.05, -0.1), Pt(0.05, -0.8) }, Soft, Th);
		Poly({ Pt(0.35, -0.1), Pt(0.35, -0.8) }, Soft, Th);
		break;
	case ESkyPiece::Loop:
		Arc(0, 0.2, 0.62, 0, 360, 24, L);
		Poly(L, Col, Th);
		Poly({ Pt(-1, -0.85), Pt(0, -0.42), Pt(1, -0.85) }, Col, Th);
		break;
	case ESkyPiece::Corkscrew:
		for (int32 i = 0; i <= 24; ++i)
		{
			const double V = -1.0 + 2.0 * i / 24;
			L.Add(Pt(0.55 * FMath::Sin(V * UE_PI * 1.5), V));
		}
		Poly(L, Col, Th);
		break;
	case ESkyPiece::WallRide:
		Poly({ Pt(-1, -0.75), Pt(0.15, -0.75) }, Col, Th);
		Arc(0.15, -0.0, 0.75, -90, 0, 8, L);
		Poly(L, Col, Th);
		Poly({ Pt(0.9, 0.0), Pt(0.9, 0.95) }, Col, Th);
		break;
	case ESkyPiece::Booster:
		for (int32 k = 0; k < 3; ++k)
		{
			const double V = -0.8 + 0.6 * k;
			Poly({ Pt(-0.6, V), Pt(0, V + 0.5), Pt(0.6, V) }, k == 0 ? Soft : Col, Th);
		}
		break;
	case ESkyPiece::Lanes:
		Poly({ Pt(-0.22, -1), Pt(-0.22, -0.25), Pt(-0.8, 0.9) }, Col, Th);
		Poly({ Pt(0.22, -1), Pt(0.22, -0.25), Pt(0.8, 0.9) }, Col, Th);
		Poly({ Pt(0, -1), Pt(0, 0.9) }, Soft, Th);
		break;
	case ESkyPiece::Split:
		Poly({ Pt(0, -1), Pt(0, -0.1) }, Col, Th);
		Poly({ Pt(0, -0.1), Pt(-0.7, 0.9) }, Col, Th);
		Poly({ Pt(0, -0.1), Pt(0.7, 0.9) }, Col, Th);
		break;
	case ESkyPiece::Checkpoint:
		Poly({ Pt(-0.7, -0.9), Pt(-0.7, 0.75) }, Col, Th);
		Poly({ Pt(0.7, -0.9), Pt(0.7, 0.75) }, Col, Th);
		Poly({ Pt(-0.7, 0.75), Pt(0.7, 0.75) }, Col, Th);
		Poly({ Pt(-0.7, 0.3), Pt(0.7, 0.3) }, Soft, Th);
		break;
	case ESkyPiece::Finish:
		for (int32 r = 0; r < 3; ++r)
			for (int32 c = 0; c < 4; ++c)
			{
				const float Cell = Sz * 0.42f;
				const float X0 = Cx - Cell * 2.f + c * Cell, Y0 = Cy - Cell * 1.5f + r * Cell;
				if ((r + c) % 2 == 0) Hud->DrawRect(Col, X0, Y0, Cell, Cell);
				else Hud->DrawRect(Soft, X0, Y0, Cell, Cell);
			}
		break;
	case ESkyPiece::Close:
		Arc(0, 0, 0.7, 60, 360, 22, L);
		Poly(L, Col, Th);
		{
			const FVector2D Tip = Pt(0.7 * FMath::Cos(FMath::DegreesToRadians(60)), 0.7 * FMath::Sin(FMath::DegreesToRadians(60)));
			Tri(Tip + FVector2D(0, -6.f * S), Tip + FVector2D(-9.f * S, 5.f * S), Tip + FVector2D(9.f * S, 6.f * S), Col);
		}
		break;
	default: break;
	}
}

void FSkyCourseBuilderImpl::DrawFitBanner(float X, float Y, float W)
{
	if (bFits)
	{
		Panel(X, Y + 4.f * S, 12.f * S, 12.f * S, Green);
		Text(TEXT("FITS"), X + 22.f * S, Y - 2.f * S, 1.0f * S, Green);
		return;
	}
	Panel(X, Y + 4.f * S, 12.f * S, 12.f * S, Red);
	Text(TEXT("BLOCKED"), X + 22.f * S, Y - 2.f * S, 1.0f * S, Red);
	FString R = FitReason;
	const float Room = W - 130.f * S;
	while (R.Len() > 8 && TextW(R, 0.75f * S) > Room) R = R.Left(R.Len() - 4) + TEXT("...");
	Text(R, X + 118.f * S, Y + 2.f * S, 0.75f * S, FLinearColor(1.f, 0.78f, 0.74f, 0.95f));
}

void FSkyCourseBuilderImpl::DrawPalette()
{
	const float CxScr = Canvas->ClipX * 0.5f;
	const float Gap = 8.f * S;
	const float Tw = FMath::Min(100.f * S, (Canvas->ClipX - 80.f * S - (NumPalette - 1) * Gap) / NumPalette);
	const float Th = 90.f * S;
	const float Total = NumPalette * Tw + (NumPalette - 1) * Gap;
	const float X0 = CxScr - Total * 0.5f;
	const float HintH = 78.f * S;
	const float Y0 = Canvas->ClipY - HintH - Th - 6.f * S;
	const ESkyPiece Sel = Palette[P->PaletteIndex];

	// the settings of the selected piece, above the strip
	EF F[3];
	FieldsFor(Sel, F);
	const float PW = FMath::Min(Total, 1100.f * S), PH = 134.f * S;
	const float PX = CxScr - PW * 0.5f, PY = Y0 - PH - 10.f * S;
	Panel(PX, PY, PW, PH, Back);
	Text(PieceLabel(Sel), PX + 18.f * S, PY + 8.f * S, 1.35f * S, Ink);
	Text(PieceHelp(Sel), PX + 18.f * S, PY + 48.f * S, 0.72f * S, Dim);
	// the up to three settings: label, value, and the button that changes it
	const float Cols0 = PX + PW * 0.36f;
	const float ColW = (PX + PW - 18.f * S - Cols0) / 3.f;
	for (int32 i = 0; i < 3; ++i)
	{
		if (F[i] == EF::None) continue;
		const float X = Cols0 + ColW * i;
		const bool bActive = i == 0 || i == SecondField;
		const FFieldInfo I = InfoFor(Sel, F[i]);
		Text(I.Label, X, PY + 8.f * S, 0.78f * S, bActive ? Cyan : Faint);
		Text(FormatField(P->Pending, F[i]), X, PY + 30.f * S, 1.45f * S, bActive ? Ink : Dim);
		const FString Btn = i == 0 ? FString(TEXT("D-pad up / down")) : (F[2] != EF::None ? FString(i == SecondField ? TEXT("LB / RB (R3 swaps)") : TEXT("R3 to edit")) : FString(TEXT("LB / RB")));
		Text(Btn, X, PY + 72.f * S, 0.68f * S, bActive ? Dim : Faint);
	}
	// whether it fits, on its own row: the bake's reason can be long
	Panel(PX + 14.f * S, PY + 100.f * S, PW - 28.f * S, 1.f * S, Faint);
	DrawFitBanner(PX + 18.f * S, PY + 108.f * S, PW - 36.f * S);

	// the strip
	for (int32 i = 0; i < NumPalette; ++i)
	{
		const bool bSel = i == P->PaletteIndex;
		const float X = X0 + i * (Tw + Gap);
		const float Lift = bSel ? 8.f * S : 0.f;
		Panel(X, Y0 - Lift, Tw, Th + Lift, bSel ? FLinearColor(0.08f, 0.22f, 0.3f, 0.85f) : Back);
		if (bSel)
		{
			Panel(X, Y0 - Lift, Tw, 4.f * S, Cyan);
			Line(X, Y0 - Lift, X, Y0 + Th, Cyan, 1.5f);
			Line(X + Tw, Y0 - Lift, X + Tw, Y0 + Th, Cyan, 1.5f);
		}
		DrawIcon(Palette[i], X + Tw * 0.5f, Y0 - Lift + 36.f * S, FMath::Min(24.f * S, Tw * 0.3f), bSel ? Ink : Dim);
		Text(PieceLabel(Palette[i]), X + Tw * 0.5f, Y0 - Lift + Th + Lift - 24.f * S, 0.62f * S, bSel ? Ink : Faint, 1);
	}

	// the hint line: what each button does right now
	struct FHint { FString Key, What; };
	TArray<FHint> Hints;
	Hints.Add({ TEXT("D-pad L/R"), TEXT("piece") });
	if (F[0] != EF::None) Hints.Add({ TEXT("D-pad U/D"), FString(InfoFor(Sel, F[0]).Label).ToLower() });
	if (F[1] != EF::None) Hints.Add({ TEXT("LB/RB"), FString(InfoFor(Sel, F[F[2] != EF::None && SecondField == 2 ? 2 : 1]).Label).ToLower() });
	Hints.Add({ TEXT("A"), TEXT("place") });
	Hints.Add({ TEXT("B"), TEXT("remove") });
	Hints.Add({ TEXT("Y"), TEXT("test drive") });
	Hints.Add({ TEXT("X"), TEXT("menu") });
	Hints.Add({ TEXT("View"), TEXT("branch") });
	Hints.Add({ TEXT("Menu"), TEXT("garage") });
	Hints.Add({ TEXT("sticks"), TEXT("pan, orbit") });
	Hints.Add({ TEXT("triggers"), TEXT("zoom") });
	const float KH = 24.f * S;
	TArray<float> Ws;
	float Sum = 0;
	for (const FHint& H : Hints)
	{
		const float W = TextW(H.Key, 0.72f * S) + 18.f * S + 8.f * S + TextW(H.What, 0.78f * S) + 22.f * S;
		Ws.Add(W);
		Sum += W;
	}
	const float Avail = Canvas->ClipX - 60.f * S;
	float Y = Y0 + Th + 14.f * S;
	int32 Idx = 0;
	const int32 Rows = Sum > Avail ? 2 : 1;
	const float PerRow = Sum / Rows;
	for (int32 Row = 0; Row < Rows; ++Row)
	{
		float RowW = 0;
		int32 Start = Idx;
		while (Idx < Hints.Num() && (Row == Rows - 1 || RowW + Ws[Idx] * 0.5f < PerRow)) RowW += Ws[Idx++];
		float X = CxScr - RowW * 0.5f;
		for (int32 i = Start; i < Idx; ++i)
		{
			float KW = 0;
			Key(Hints[i].Key, X, Y, KH, Gold, &KW);
			Text(Hints[i].What, X + KW + 8.f * S, Y + 2.f * S, 0.78f * S, Dim);
			X += Ws[i];
		}
		Y += KH + 6.f * S;
	}
	Text(TEXT("Keyboard: arrows, Q/E, R, Enter, Backspace, T, M, Tab, Esc · WASD pan · Z/C orbit · PgUp/PgDn or wheel zoom · right-drag orbit · U undo"),
		CxScr, Canvas->ClipY - 22.f * S, 0.66f * S, Faint, 1);
}

// ============================================================================================ menus

void FSkyCourseBuilderImpl::DrawMenu()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	const TArray<FItem> Items = BuildItems();
	Panel(0, 0, Canvas->ClipX, Canvas->ClipY, FLinearColor(0.f, 0.f, 0.f, 0.5f));
	const float Row = FMath::Min(36.f * S, (Canvas->ClipY - 250.f * S) / FMath::Max(1, Items.Num()));
	const float PW = 860.f * S;
	const float PH = 74.f * S + Items.Num() * Row + 110.f * S;
	const float X = Canvas->ClipX * 0.5f - PW * 0.5f, Y = FMath::Max(14.f * S, Canvas->ClipY * 0.5f - PH * 0.5f);
	Panel(X, Y, PW, PH, FLinearColor(0.02f, 0.03f, 0.05f, 0.9f));
	Panel(X, Y, PW, 4.f * S, Cyan);
	Text(TEXT("COURSE MENU"), X + 28.f * S, Y + 16.f * S, 1.5f * S, Ink);
	float Yy = Y + 74.f * S;
	for (int32 i = 0; i < Items.Num(); ++i)
	{
		const FItem& It = Items[i];
		const bool bSel = i == MenuSel;
		if (bSel)
		{
			Panel(X + 14.f * S, Yy - 2.f * S, PW - 28.f * S, Row - 2.f * S, FLinearColor(0.1f, 0.28f, 0.36f, 0.85f));
			Tri(FVector2D(X + 20.f * S, Yy + 4.f * S), FVector2D(X + 20.f * S, Yy + Row - 10.f * S), FVector2D(X + 31.f * S, Yy + Row * 0.5f - 3.f * S), Cyan);
		}
		const bool bDanger = It.Id == EMenuItem::Garage;
		Text(It.Label, X + 44.f * S, Yy + 3.f * S, 0.95f * S, bSel ? Ink : Dim);
		FString V = It.Value;
		if (!V.IsEmpty())
		{
			FLinearColor Vc = bSel ? Cyan : Dim;
			if (It.Id == EMenuItem::Llm) Vc = V == TEXT("ON") ? Green : Dim;
			if (It.bAdjust && bSel) V = TEXT("<  ") + V + TEXT("  >");
			while (V.Len() > 8 && TextW(V, 0.9f * S) > PW * 0.55f) V = V.Left(V.Len() - 4) + TEXT("...");
			Text(V, X + PW - 30.f * S, Yy + 3.f * S, 0.9f * S, Vc, 2);
		}
		(void)bDanger;
		Yy += Row;
	}
	// the LLM link's address and how to point Claude Code at it
	const FItem& Cur = Items.IsValidIndex(MenuSel) ? Items[MenuSel] : FItem();
	const float Fy = Y + PH - 96.f * S;
	Panel(X + 14.f * S, Fy, PW - 28.f * S, 1.f * S, Faint);
	if (Cur.Id == EMenuItem::Llm)
	{
		Text(Mode->IsMcpEnabled() ? TEXT("LLM link is ON: this computer only, courses only") : TEXT("LLM link is OFF. A switches it on: this computer only, courses only"), X + 28.f * S, Fy + 10.f * S, 0.8f * S, Ink);
		Text(TEXT("URL   http://127.0.0.1:47800/mcp"), X + 28.f * S, Fy + 36.f * S, 0.85f * S, Cyan);
		Text(TEXT("Claude Code:   claude mcp add --transport http skycity http://127.0.0.1:47800/mcp"), X + 28.f * S, Fy + 62.f * S, 0.72f * S, Dim);
	}
	else
	{
		Text(TEXT("D-pad up / down choose · left / right change · A select · B or X back"), X + 28.f * S, Fy + 12.f * S, 0.8f * S, Dim);
		Text(TEXT("Keyboard: arrows, Enter, Backspace or M back"), X + 28.f * S, Fy + 40.f * S, 0.72f * S, Faint);
	}
}

void FSkyCourseBuilderImpl::DrawLoad()
{
	Panel(0, 0, Canvas->ClipX, Canvas->ClipY, FLinearColor(0.f, 0.f, 0.f, 0.5f));
	const float Row = 36.f * S, PW = 700.f * S;
	const int32 Visible = 12;
	const float PH = 84.f * S + Visible * Row + 54.f * S;
	const float X = Canvas->ClipX * 0.5f - PW * 0.5f, Y = FMath::Max(14.f * S, Canvas->ClipY * 0.5f - PH * 0.5f);
	Panel(X, Y, PW, PH, FLinearColor(0.02f, 0.03f, 0.05f, 0.9f));
	Panel(X, Y, PW, 4.f * S, Cyan);
	Text(TEXT("LOAD COURSE"), X + 28.f * S, Y + 16.f * S, 1.5f * S, Ink);
	if (LoadList.Num() == 0)
	{
		Text(TEXT("No saved courses yet."), X + 28.f * S, Y + 100.f * S, 1.0f * S, Dim);
		Text(TEXT("Save one from the course menu, or drop a course .json into Saved/Courses."), X + 28.f * S, Y + 136.f * S, 0.8f * S, Faint);
	}
	const int32 First = FMath::Clamp(LoadSel - Visible / 2, 0, FMath::Max(0, LoadList.Num() - Visible));
	for (int32 k = 0; k < Visible && First + k < LoadList.Num(); ++k)
	{
		const int32 i = First + k;
		const float Yy = Y + 84.f * S + k * Row;
		if (i == LoadSel)
		{
			Panel(X + 14.f * S, Yy - 2.f * S, PW - 28.f * S, Row - 3.f * S, FLinearColor(0.1f, 0.28f, 0.36f, 0.85f));
			Tri(FVector2D(X + 20.f * S, Yy + 5.f * S), FVector2D(X + 20.f * S, Yy + Row - 12.f * S), FVector2D(X + 31.f * S, Yy + Row * 0.5f - 4.f * S), Cyan);
		}
		Text(LoadList[i], X + 44.f * S, Yy + 4.f * S, 0.95f * S, i == LoadSel ? Ink : Dim);
	}
	Text(TEXT("D-pad up / down choose · A load · B back"), X + 28.f * S, Y + PH - 40.f * S, 0.8f * S, Dim);
}

void FSkyCourseBuilderImpl::DrawName()
{
	Panel(0, 0, Canvas->ClipX, Canvas->ClipY, FLinearColor(0.f, 0.f, 0.f, 0.55f));
	const float PW = 860.f * S, PH = 330.f * S;
	const float X = Canvas->ClipX * 0.5f - PW * 0.5f, Y = Canvas->ClipY * 0.5f - PH * 0.5f;
	Panel(X, Y, PW, PH, FLinearColor(0.02f, 0.03f, 0.05f, 0.92f));
	Panel(X, Y, PW, 4.f * S, Cyan);
	Text(bNameIsSave ? TEXT("SAVE COURSE AS") : TEXT("RENAME COURSE"), X + 28.f * S, Y + 16.f * S, 1.5f * S, Ink);
	Panel(X + 28.f * S, Y + 84.f * S, PW - 56.f * S, 64.f * S, FLinearColor(0.f, 0.f, 0.f, 0.6f));
	const bool bCaret = FMath::Fmod(Time, 1.0) < 0.6;
	const FString Shown = NameText + (bCaret ? TEXT("_") : TEXT(" "));
	Text(Shown, X + 44.f * S, Y + 92.f * S, 2.0f * S, Ink);
	Text(FString::Printf(TEXT("%d / 48"), NameText.Len()), X + PW - 40.f * S, Y + 152.f * S, 0.72f * S, Faint, 2);
	Text(TEXT("Pad: D-pad up / down turns the last letter, right adds the next, left deletes, LB / RB jump ten"), X + 28.f * S, Y + 190.f * S, 0.8f * S, Dim);
	Text(TEXT("A saves it, B cancels. Letters, digits, spaces, dashes and underscores only."), X + 28.f * S, Y + 218.f * S, 0.8f * S, Dim);
	Text(TEXT("Keyboard: just type. Enter saves, Esc cancels, Backspace deletes."), X + 28.f * S, Y + 252.f * S, 0.8f * S, Faint);
}

void FSkyCourseBuilderImpl::DrawGarage()
{
	ASkyCourseMode* Mode = ModeRef.Get();
	if (!Mode) return;
	Panel(0, 0, Canvas->ClipX, Canvas->ClipY, FLinearColor(0.f, 0.f, 0.f, 0.55f));
	const ASkysterCar* Car = Mode->GetCar();
	const TArray<FName> Maps = Car ? Car->Maps : TArray<FName>();
	const float Row = 40.f * S, PW = 760.f * S;
	const float PH = 84.f * S + (Maps.Num() + 1) * Row + 130.f * S;
	const float X = Canvas->ClipX * 0.5f - PW * 0.5f, Y = Canvas->ClipY * 0.5f - PH * 0.5f;
	Panel(X, Y, PW, PH, FLinearColor(0.02f, 0.03f, 0.05f, 0.92f));
	Panel(X, Y, PW, 4.f * S, Cyan);
	Text(TEXT("GARAGE"), X + 28.f * S, Y + 16.f * S, 1.5f * S, Ink);
	Text(TEXT("Leave the Course Builder for another map"), X + 28.f * S, Y + 56.f * S, 0.8f * S, Dim);
	const FString Here = UGameplayStatics::GetCurrentLevelName(Mode, true) + (SkyCourse::IsBuildMode(Mode->GetWorld()) ? TEXT("?mode=build") : TEXT(""));
	float Yy = Y + 92.f * S;
	for (int32 i = 0; i <= Maps.Num(); ++i)
	{
		const bool bSel = i == GarageSel;
		if (bSel)
		{
			Panel(X + 14.f * S, Yy - 2.f * S, PW - 28.f * S, Row - 3.f * S, FLinearColor(0.1f, 0.28f, 0.36f, 0.85f));
			Tri(FVector2D(X + 20.f * S, Yy + 7.f * S), FVector2D(X + 20.f * S, Yy + Row - 14.f * S), FVector2D(X + 31.f * S, Yy + Row * 0.5f - 4.f * S), Cyan);
		}
		if (i == Maps.Num())
		{
			Text(TEXT("Back to building"), X + 44.f * S, Yy + 5.f * S, 1.0f * S, bSel ? Ink : Dim);
		}
		else
		{
			const FString Entry = Maps[i].ToString();
			const bool bHere = FPaths::GetBaseFilename(Entry) == Here;
			Text(MapName(Entry), X + 44.f * S, Yy + 5.f * S, 1.0f * S, bSel ? Ink : Dim);
			if (bHere) Text(TEXT("you are here"), X + PW - 30.f * S, Yy + 8.f * S, 0.8f * S, Green, 2);
		}
		Yy += Row;
	}
	Text(TEXT("D-pad up / down choose · A open · B back"), X + 28.f * S, Y + PH - 86.f * S, 0.8f * S, Dim);
	Text(TEXT("A test drive (Y) gives you the car: its Garage (Menu) has the car level and the vehicle."), X + 28.f * S, Y + PH - 54.f * S, 0.72f * S, Faint);
}

// ============================================================================================ while driving

void FSkyCourseBuilderImpl::DrawDriving()
{
	const FString A = TEXT("Y: back to building");
	const FString B = TEXT("Menu: garage");
	const float Wa = TextW(A, 1.0f * S), Wb = TextW(B, 0.8f * S);
	const float W = Wa + Wb + 90.f * S, H = 46.f * S;
	const float X = Canvas->ClipX * 0.5f - W * 0.5f, Y = Canvas->ClipY - 84.f * S;
	Panel(X, Y, W, H, FLinearColor(0.02f, 0.03f, 0.05f, 0.6f));
	Panel(X, Y, 5.f * S, H, Cyan);
	Text(A, X + 24.f * S, Y + 10.f * S, 1.0f * S, Ink);
	Text(B, X + W - 20.f * S, Y + 14.f * S, 0.8f * S, Dim, 2);
}
