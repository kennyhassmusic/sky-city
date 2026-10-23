using UnrealBuildTool;

public class SkyCity : ModuleRules
{
	public SkyCity(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "Json", "RenderCore" });
		// Course Builder: runtime track meshes, the local MCP server (HTTP), JSON (de)serialisation
		PrivateDependencyModuleNames.AddRange(new string[] { "ProceduralMeshComponent", "HTTPServer", "JsonUtilities", "ApplicationCore" });
	}
}
