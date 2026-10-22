// FSkyCourseMcp (see SkyCourse.h). STUB: to be written by the MCP agent.
#include "SkyCourse.h"

struct FSkyCourseMcp::FState {};
FSkyCourseMcp::FSkyCourseMcp(ASkyCourseMode* InMode) : Mode(InMode) {}
FSkyCourseMcp::~FSkyCourseMcp() { Stop(); }
bool FSkyCourseMcp::Start(int32) { return false; }
void FSkyCourseMcp::Stop() {}
bool FSkyCourseMcp::IsRunning() const { return false; }
FString FSkyCourseMcp::Url() const { return FString::Printf(TEXT("http://127.0.0.1:%d/mcp"), SkyCourse::McpPort); }
