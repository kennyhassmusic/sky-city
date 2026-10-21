using UnrealBuildTool;

public class SkyCityTarget : TargetRules
{
	public SkyCityTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyCity");
	}
}
