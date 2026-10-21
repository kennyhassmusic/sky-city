using UnrealBuildTool;

public class SkyCityEditorTarget : TargetRules
{
	public SkyCityEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyCity");
	}
}
