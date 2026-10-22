// The Course Builder's editor (ASkyCourseBuilderPawn's private half). Only SkyCourseBuilder.cpp (controls, camera, cursor,
// fit test, menus) and SkyCourseBuilderHud.cpp (everything drawn on the canvas) include this.
#pragma once

#include "CoreMinimal.h"
#include "Engine/Font.h"
#include "InputCoreTypes.h"
#include "SkyCourse.h"
#include "UObject/StrongObjectPtr.h"

class UFont;
class UMaterialInstanceDynamic;
class UProceduralMeshComponent;
class APlayerController;

namespace SkyBuilder
{
	/** The palette: every piece you can place (the start piece is automatic), in the order the strip shows them. */
	extern const ESkyPiece Palette[];
	constexpr int32 NumPalette = 13;

	/** A setting of a piece that the D-pad / bumpers change. */
	enum class EF : uint8 { None, Length, Angle, Radius, Bank, Rise, Gap, Drop, Offset, Turns, Side, Lanes, Align, Branches, Gate };
	struct FFieldInfo { const TCHAR* Label; const TCHAR* Unit; double Step, Lo, Hi; };

	/** The up to three settings of a piece: [0] D-pad up/down, [1] LB/RB, [2] LB/RB after R3 (or R) swaps to it. */
	void FieldsFor(ESkyPiece Type, EF Out[3]);
	FFieldInfo InfoFor(ESkyPiece Type, EF Field);
	double GetField(const FSkyPiece& P, EF Field);
	void SetField(FSkyPiece& P, EF Field, double V);
	FString FormatField(const FSkyPiece& P, EF Field);
	void AdjustField(FSkyPiece& P, EF Field, int32 Dir);
	FSkyPiece MakeDefault(ESkyPiece Type, int32 LanesHere);
	const TCHAR* PieceLabel(ESkyPiece Type);
	const TCHAR* PieceHelp(ESkyPiece Type);

	/** Put a piece at the end of a sequence (a split also gets its branch sequences). Returns the first branch's sequence or INDEX_NONE. */
	int32 ApplyPlace(FSkyCourse& C, int32 Seq, const FSkyPiece& Piece, int32 LanesHere);
	/** A split's branches as a new split starts them: N of them fanned out, each with its share of the lanes (Seq left unset). */
	void FillBranches(FSkyPiece& Split, int32 LanesHere);
	/** Remove the last piece of a sequence (an empty branch removes its split). Empty string = done, else why not. Seq follows the edit. */
	FString RemoveLast(FSkyCourse& C, int32& Seq);
	struct FOwner { int32 ParentSeq = INDEX_NONE, PieceIdx = INDEX_NONE, BranchIdx = INDEX_NONE; };
	bool FindOwner(const FSkyCourse& C, int32 Seq, FOwner& Out);
	FString SeqLabel(const FSkyCourse& C, const FSkyBaked& B, int32 Seq);
	bool EndsClosed(const FSkyCourse& C, int32 Seq);
	/** A bake warning that is just the normal state of a course still being built (no finish yet): not worth a toast or a panel. */
	bool IsRoutineWarning(const FString& W);
}

enum class EBuilderScreen : uint8 { Build, Menu, Load, Name, Garage };
enum class EMenuItem : uint8
{
	Resume, NewCourse, Save, Load, Rename, Example, Undo, Skin, Laps, Opponents, Skill, Llm,
	BranchLanes, BranchAngle, BranchLaps, Gate, MergeLength, MergeLanes, Garage
};

class FSkyCourseBuilderImpl
{
public:
	explicit FSkyCourseBuilderImpl(ASkyCourseBuilderPawn* InPawn);

	// --- the pawn's entry points ---
	void Tick(float Dt);
	void DrawHud(AHUD* InHud, UCanvas* InCanvas, float InS);
	void Press(const FString& Button);
	void TypeText(const FString& Text);
	void SetCamera(double InYaw, double InPitch, double InDist, bool bSnap);
	FString StateJson() const;
	void Toast(const FString& Title, const FString& Sub = FString(), bool bBad = false);
	/** For the director: a toast on a pawn's screen (creates the editor state if the pawn hasn't ticked yet). */
	static void ToastFor(ASkyCourseBuilderPawn* Pawn, const FString& Title, const FString& Sub, bool bBad);

	// --- state the HUD reads ---
	ASkyCourseBuilderPawn* P = nullptr;
	TWeakObjectPtr<ASkyCourseMode> ModeRef;
	double Time = 0;

	// input
	struct FRepeat { bool bDown = false; double T = 0, Acc = 0; };
	TMap<FKey, FRepeat> Keys;
	TMap<FKey, FRepeat> TypeKeys;   // the name box reads the letter keys on their own, apart from the editor's shortcuts
	TArray<FString> TestQueue;
	struct FIn
	{
		double PanX = 0, PanY = 0, OrbX = 0, OrbY = 0, Zoom = 0;
		bool bLeft = false, bRight = false, bUp = false, bDown = false, bLB = false, bRB = false;
		bool bA = false, bB = false, bX = false, bY = false, bView = false, bMenu = false, bR3 = false, bUndo = false;
		bool bBackspace = false, bEnter = false, bEscape = false, bPadB = false;
		double MouseYaw = 0, MousePitch = 0, Wheel = 0;   // degrees this frame (right mouse button held), wheel notches
	};
	bool bWasActive = false, bHadPad = false;

	// camera (course frame, metres, degrees): the targets, then the eased values actually shown
	double Yaw = 0, Pitch = 52, Dist = 70;
	double YawS = 0, PitchS = 52, DistS = 70;
	FVector FocusT = FVector::ZeroVector, FocusS = FVector::ZeroVector, Pan = FVector::ZeroVector;
	bool bCamInit = false;
	double LastHeading = 0;
	double CamPulse = 0;

	// the cursor: where the next piece starts
	FSkyFrame Cursor;
	int32 CursorLanes = SkyCourse::DefaultLanes;
	bool bClosed = false;
	bool bHaveCursor = false;
	int32 SeenRevision = -1, SeenSeq = -1;
	TWeakObjectPtr<UProceduralMeshComponent> CursorMesh;
	TWeakObjectPtr<UMaterialInstanceDynamic> CursorMat;
	double CursorWidthBuilt = -1;
	double CursorBlink = 0;

	// the palette
	TArray<FSkyPiece> Stored;      // each piece type's last settings (index = ESkyPiece)
	int32 SecondField = 1;         // 1 or 2: which setting LB/RB change
	int32 DefaultsLanes = -1;      // the lane count the stored defaults were made for

	// fit test
	bool bFits = false;
	FString FitReason;
	bool bFitDirty = true;
	double FitDueAt = 0, FitMs = 0, FitMsMax = 0;
	int32 FitCount = 0;
	FSkyBaked Trial;

	// screens
	EBuilderScreen Screen = EBuilderScreen::Build;
	int32 MenuSel = 0, LoadSel = 0, GarageSel = 0, LapSel = 1;
	TArray<FString> LoadList;
	FString NameText;
	bool bNameIsSave = true;
	int32 NameWheel = 0;
	FString LastWarnKey;

	// toasts
	struct FToast { FString Title, Sub; double Born = 0; bool bBad = false; };
	TArray<FToast> Toasts;

	// drawing context (valid inside DrawHud)
	AHUD* Hud = nullptr;
	UCanvas* Canvas = nullptr;
	float S = 1.f;
	TStrongObjectPtr<UFont> Font;

	// --- menus ---
	struct FItem { EMenuItem Id = EMenuItem::Resume; FString Label, Value; bool bAdjust = false; bool bOn = true; };
	TArray<FItem> BuildItems() const;
	FString MapName(const FString& Path) const;

private:
	// logic (SkyCourseBuilder.cpp)
	FIn Gather(float Dt);
	bool Edge(APlayerController* PC, const FKey& K, float Dt, bool bRepeat, double Delay = 0.36, double Rate = 0.085, bool bTyping = false);
	void Sync();
	void OnCursorMoved(bool bSnap);
	void UpdateCamera(float Dt, const FIn& In);
	void UpdateCursorVisual(float Dt);
	void BuildCursorMesh(double Width);
	void UpdateFit();
	void MarkFitDirty() { bFitDirty = true; }
	void RefreshDefaults();
	void SelectPiece(int32 Index);
	void AdjustMain(int32 Dir);
	void AdjustSecond(int32 Dir);
	void StoreCurrent();
	void Place();
	void RemoveLast();
	void CycleSeq();
	void ToastErrors(const TArray<FString>& Errors, const TCHAR* Title);
	void HandleBuild(const FIn& In, APlayerController* PC);
	void HandleMenu(const FIn& In);
	void HandleLoad(const FIn& In);
	void HandleName(const FIn& In, APlayerController* PC, float Dt);
	void HandleGarage(const FIn& In);
	void Activate(EMenuItem Id);
	void Adjust(EMenuItem Id, int32 Dir);
	void OpenMenu();
	void CloseScreens();
	void DoNameConfirm();
	UProceduralMeshComponent* EnsureCursor();

	// drawing (SkyCourseBuilderHud.cpp)
	friend class FSkyCourseBuilderHud;
	void DrawBuild();
	void DrawInfo();
	void DrawToasts();
	void DrawWarnings();
	void DrawPalette();
	void DrawFitBanner(float X, float Y, float W);
	void DrawMenu();
	void DrawLoad();
	void DrawName();
	void DrawGarage();
	void DrawDriving();
	void DrawIcon(ESkyPiece Type, float Cx, float Cy, float Size, const FLinearColor& Col);
	void Panel(float X, float Y, float W, float H, const FLinearColor& Col);
	void Text(const FString& T, float X, float Y, float Size, const FLinearColor& Col, int32 Align = 0);   // 0 left, 1 centre, 2 right
	float TextW(const FString& T, float Size);
	void Line(float X0, float Y0, float X1, float Y1, const FLinearColor& Col, float W);
	void Poly(const TArray<FVector2D>& Pts, const FLinearColor& Col, float W, bool bClose = false);
	void Tri(const FVector2D& A, const FVector2D& B, const FVector2D& C, const FLinearColor& Col);
	void Key(const FString& Label, float X, float Y, float H, const FLinearColor& Col, float* OutW = nullptr);
};
