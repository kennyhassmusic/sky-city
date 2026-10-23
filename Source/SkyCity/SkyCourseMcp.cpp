// FSkyCourseMcp (see SkyCourse.h): the local MCP server that lets a player's own LLM build courses while they watch.
// Design: Design/CourseBuilder.md ("The MCP server"). Player docs: docs/COURSE_MCP.md. Test: Scripts/course/mcp_smoke_test.py.
//
// MCP Streamable HTTP, JSON responses only (no SSE): POST /mcp carries JSON-RPC 2.0, GET answers 405, DELETE ends a session.
//
// Why this is a small socket server of its own and not Unreal's HTTPServer module (read from the engine source, UE 5.8):
//  - The module can't close one port. FHttpServerModule has StopAllListeners and nothing per port, and a listener, once
//    created, lives until the module shuts down. StopAllListeners would also kill every other user of the module, such as
//    the editor's own MCP server on port 8000. "LLM link off" has to mean the port is closed, so we own the socket.
//  - Its bind address is a config string read from the engine ini ("localhost" by default, which is loopback). A stray
//    DefaultBindAddress=any anywhere would silently put the course server on the network. Here 127.0.0.1 is in the code.
//  - Every idle keep-alive connection costs a 1 ms select() per frame (BeginReadWaitTimeMS), and SetReuseAddr also sets
//    SO_REUSEPORT, which would let a second game window bind the same port.
// What it does share with the module: it is driven from the core ticker, so every request is read, run and answered on the
// GAME THREAD. Course edits therefore need no queue (ASkyCourseMode::RunOnGameThread is for other threads), and one tool
// call is run per tick at most, so a big bake costs one frame hitch and a flood of calls can't freeze the game.
//
// Security (all checked before anything is parsed as JSON-RPC):
//  - bound to 127.0.0.1 only, and every accepted peer is checked to be loopback too
//  - Origin, if present, must be http(s)://localhost, 127.0.0.1 or [::1] on any port, else 403 (DNS-rebinding / web pages)
//  - Host must be localhost, 127.0.0.1 or [::1], else 403 (DNS rebinding)
//  - request bodies are limited to 2 MB, headers to 16 KB, connections to 16, and slow clients are dropped
//  - the tools only touch the course through ASkyCourseMode (save, load and list included): this file never opens a file
#include "SkyCourse.h"
#include "SkysterCar.h"

#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/CoreDelegates.h"
#include "Misc/DefaultValueHelper.h"
#include "Misc/Guid.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#if PLATFORM_MAC || PLATFORM_LINUX
#define SKYMCP_SOCKETS 1
THIRD_PARTY_INCLUDES_START
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
THIRD_PARTY_INCLUDES_END
#else
#define SKYMCP_SOCKETS 0
#endif

DEFINE_LOG_CATEGORY_STATIC(LogSkyMcp, Log, All);

namespace SkyMcp
{
// --- limits ---------------------------------------------------------------------------------------------------------
constexpr int32 MaxHeaderBytes = 16 * 1024;
constexpr int32 MaxBodyBytes = 2 * 1024 * 1024;     // the design's 2 MB request limit
constexpr int32 MaxConnections = 16;
constexpr int32 MaxRequestsPerTick = 2;
constexpr int32 MaxSessions = 32;
constexpr int32 MaxPiecesPerCall = 100;
constexpr double IdleSeconds = 120.0;               // keep-alive connections with nothing to say
constexpr double RequestSeconds = 15.0;             // a request must be complete this long after its first byte
constexpr double WriteSeconds = 30.0;               // a client that won't read its answer
constexpr double DrainSeconds = 2.0;                // after an error answer: let the client read it before closing
static const TCHAR* const ServerName = TEXT("sky-city-courses");
static const TCHAR* const LatestProtocol = TEXT("2025-06-18");
static const TCHAR* const Protocols[] = { TEXT("2025-06-18"), TEXT("2025-03-26") };

// --- JSON helpers ---------------------------------------------------------------------------------------------------
using FObj = TSharedPtr<FJsonObject>;
using FVal = TSharedPtr<FJsonValue>;
using FValArr = TArray<TSharedPtr<FJsonValue>>;

static FObj NewObj() { return MakeShared<FJsonObject>(); }
/** Numbers go out as text so they print the way we round them (12.35, not 12.349999999999999). */
static FVal JNum(double V, int32 Decimals = 2)
{
	const double Scale = FMath::Pow(10.0, (double)Decimals);
	double R = FMath::RoundToDouble(V * Scale) / Scale;
	if (!FMath::IsFinite(R) || FMath::Abs(R) < 1e-12) R = 0.0;
	return MakeShared<FJsonValueNumberString>(FString::SanitizeFloat(R, 0));
}
static FVal JInt(int64 V) { return MakeShared<FJsonValueNumberString>(FString::Printf(TEXT("%lld"), V)); }
static FVal JStr(const FString& S) { return MakeShared<FJsonValueString>(S); }
static FVal JBool(bool B) { return MakeShared<FJsonValueBoolean>(B); }
static FVal JObj(const FObj& O) { return MakeShared<FJsonValueObject>(O); }
static FVal JArr(FValArr A) { return MakeShared<FJsonValueArray>(MoveTemp(A)); }
static FVal JStrArr(const TArray<FString>& Items)
{
	FValArr A;
	for (const FString& S : Items) A.Add(JStr(S));
	return JArr(MoveTemp(A));
}
static FVal JNull() { return MakeShared<FJsonValueNull>(); }

static FString ObjToString(const FObj& O)
{
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(O.ToSharedRef(), W);
	return Out;
}
static FString ArrToString(const FValArr& A)
{
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(A, W);
	return Out;
}
/** Numbers stay as the text the client wrote (ids echo back exactly, and a course passes through untouched). */
static bool ParseJson(const FString& Text, FVal& Out)
{
	TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(Text);
	return FJsonSerializer::Deserialize(Reader, Out, FJsonSerializer::EFlags::StoreNumbersAsStrings) && Out.IsValid();
}
static FString Utf8ToString(const uint8* Data, int32 Len)
{
	FUTF8ToTCHAR Conv((const ANSICHAR*)Data, Len);
	return FString(Conv.Length(), Conv.Get());
}
static FString A2S(const ANSICHAR* S) { return FString(UTF8_TO_TCHAR(S)); }

static bool ReadNumber(const FVal& V, double& Out)
{
	if (!V.IsValid()) return false;
	if (V->Type == EJson::Number) return V->TryGetNumber(Out);
	if (V->Type == EJson::String) return FDefaultValueHelper::ParseDouble(V->AsString().TrimStartAndEnd(), Out);
	return false;
}
static bool HasArg(const FObj& A, const TCHAR* K) { const FVal* V = A->Values.Find(K); return V && V->IsValid() && (*V)->Type != EJson::Null; }
static bool ArgNum(const FObj& A, const TCHAR* K, double& Out) { const FVal* V = A->Values.Find(K); return V && ReadNumber(*V, Out); }
static bool ArgInt(const FObj& A, const TCHAR* K, int32& Out)
{
	double D = 0;
	if (!ArgNum(A, K, D) || FMath::Abs(D) > 1.0e9) return false;
	Out = FMath::RoundToInt(D);
	return true;
}
static bool ArgBool(const FObj& A, const TCHAR* K, bool& Out)
{
	const FVal* V = A->Values.Find(K);
	if (!V || !V->IsValid()) return false;
	if ((*V)->Type == EJson::Boolean) { Out = (*V)->AsBool(); return true; }
	if ((*V)->Type == EJson::String)
	{
		const FString S = (*V)->AsString().ToLower();
		if (S == TEXT("true")) { Out = true; return true; }
		if (S == TEXT("false")) { Out = false; return true; }
	}
	return false;
}
static bool ArgString(const FObj& A, const TCHAR* K, FString& Out)
{
	const FVal* V = A->Values.Find(K);
	if (!V || !V->IsValid() || (*V)->Type != EJson::String) return false;
	Out = (*V)->AsString();
	return true;
}
/** An object argument, also accepted as a string holding JSON (LLMs sometimes send it that way). */
static bool ArgObject(const FObj& A, const TCHAR* K, FObj& Out)
{
	const FVal* V = A->Values.Find(K);
	if (!V || !V->IsValid()) return false;
	if ((*V)->Type == EJson::Object) { Out = (*V)->AsObject(); return Out.IsValid(); }
	if ((*V)->Type == EJson::String)
	{
		FVal Parsed;
		if (ParseJson((*V)->AsString(), Parsed) && Parsed->Type == EJson::Object) { Out = Parsed->AsObject(); return true; }
	}
	return false;
}
static bool ArgArray(const FObj& A, const TCHAR* K, FValArr& Out)
{
	const FVal* V = A->Values.Find(K);
	if (!V || !V->IsValid()) return false;
	if ((*V)->Type == EJson::Array) { Out = (*V)->AsArray(); return true; }
	if ((*V)->Type == EJson::String)
	{
		FVal Parsed;
		if (ParseJson((*V)->AsString(), Parsed) && Parsed->Type == EJson::Array) { Out = Parsed->AsArray(); return true; }
	}
	return false;
}

// --- Origin and Host checks -----------------------------------------------------------------------------------------
static bool AllDigits(const FString& S, int32 MaxLen)
{
	if (S.IsEmpty() || S.Len() > MaxLen) return false;
	for (const TCHAR C : S) if (C < TEXT('0') || C > TEXT('9')) return false;
	return true;
}
/** "localhost", "127.0.0.1" or "[::1]", with an optional :port. Nothing else (no user info, path, spaces or trailing dot). */
static bool LocalAuthority(const FString& InAuthority)
{
	const FString Auth = InAuthority.ToLower();
	if (Auth.IsEmpty() || Auth.Len() > 64) return false;
	FString HostPart, PortPart;
	if (Auth.StartsWith(TEXT("[")))
	{
		int32 Close = INDEX_NONE;
		if (!Auth.FindChar(TEXT(']'), Close)) return false;
		HostPart = Auth.Left(Close + 1);
		const FString Rest = Auth.Mid(Close + 1);
		if (!Rest.IsEmpty())
		{
			if (!Rest.StartsWith(TEXT(":"))) return false;
			PortPart = Rest.Mid(1);
			if (!AllDigits(PortPart, 5)) return false;
		}
	}
	else
	{
		int32 Colon = INDEX_NONE;
		if (Auth.FindChar(TEXT(':'), Colon))
		{
			HostPart = Auth.Left(Colon);
			PortPart = Auth.Mid(Colon + 1);
			if (!AllDigits(PortPart, 5)) return false;
		}
		else HostPart = Auth;
	}
	return HostPart == TEXT("localhost") || HostPart == TEXT("127.0.0.1") || HostPart == TEXT("[::1]");
}
static bool OriginAllowed(const FString& InOrigin)
{
	const FString O = InOrigin.TrimStartAndEnd().ToLower();
	FString Auth;
	if (O.StartsWith(TEXT("http://"))) Auth = O.Mid(7);
	else if (O.StartsWith(TEXT("https://"))) Auth = O.Mid(8);
	else return false;                                  // includes "null" (sandboxed frames, file://)
	return LocalAuthority(Auth);
}

// --- HTTP ------------------------------------------------------------------------------------------------------------
static const TCHAR* StatusText(int32 S)
{
	switch (S)
	{
	case 100: return TEXT("Continue");
	case 200: return TEXT("OK");
	case 202: return TEXT("Accepted");
	case 204: return TEXT("No Content");
	case 400: return TEXT("Bad Request");
	case 403: return TEXT("Forbidden");
	case 404: return TEXT("Not Found");
	case 405: return TEXT("Method Not Allowed");
	case 408: return TEXT("Request Timeout");
	case 411: return TEXT("Length Required");
	case 413: return TEXT("Payload Too Large");
	case 415: return TEXT("Unsupported Media Type");
	case 431: return TEXT("Request Header Fields Too Large");
	case 500: return TEXT("Internal Server Error");
	case 501: return TEXT("Not Implemented");
	case 505: return TEXT("HTTP Version Not Supported");
	default: return TEXT("Status");
	}
}

struct FHttpReq
{
	FString Method, Path;
	bool bHttp10 = false;
	TMap<FString, FString> H;                           // header names lower-cased
	TArray<uint8> Body;
	bool Has(const TCHAR* Name) const { return H.Contains(Name); }
	FString Get(const TCHAR* Name) const { const FString* V = H.Find(Name); return V ? *V : FString(); }
};

struct FHttpResp
{
	int32 Status = 200;
	FString ContentType;                                // empty = no body
	TArray<uint8> Body;
	TArray<TPair<FString, FString>> Headers;
	bool bClose = false;
	void SetBody(int32 InStatus, const FString& Text, const TCHAR* Type)
	{
		Status = InStatus;
		ContentType = Type;
		FTCHARToUTF8 Conv(*Text);
		Body.Reset();
		Body.Append((const uint8*)Conv.Get(), Conv.Length());
	}
	void SetJson(int32 InStatus, const FString& Json) { SetBody(InStatus, Json, TEXT("application/json")); }
	void SetError(int32 InStatus, const FString& Message)
	{
		FObj O = NewObj();
		O->SetStringField(TEXT("error"), Message);
		SetJson(InStatus, ObjToString(O));
	}
	void Add(const TCHAR* Name, const FString& Value) { Headers.Emplace(Name, Value); }
};

enum class EParse { NeedMore, Ready, Error };
struct FParseOut
{
	int32 Status = 400;
	FString Message;
	int32 Consumed = 0;
	bool bSendContinue = false;
};
enum class EChunk { Incomplete, Done, Bad, TooBig };

static EChunk DecodeChunked(const TArray<uint8>& In, int32 Start, TArray<uint8>& Body, int32& End)
{
	auto FindEol = [&In](int32 From, int32 Limit) -> int32
	{
		for (int32 i = From; i + 1 < In.Num() && i < From + Limit; ++i) if (In[i] == '\r' && In[i + 1] == '\n') return i;
		return INDEX_NONE;
	};
	int32 Pos = Start;
	for (;;)
	{
		const int32 Eol = FindEol(Pos, 40);
		if (Eol == INDEX_NONE) return (In.Num() - Pos >= 40) ? EChunk::Bad : EChunk::Incomplete;
		int64 Size = 0;
		bool bAny = false;
		for (int32 i = Pos; i < Eol; ++i)
		{
			const uint8 C = In[i];
			int32 D = 0;
			if (C >= '0' && C <= '9') D = C - '0';
			else if (C >= 'a' && C <= 'f') D = C - 'a' + 10;
			else if (C >= 'A' && C <= 'F') D = C - 'A' + 10;
			else if (C == ';') break;                    // chunk extension: ignored
			else return EChunk::Bad;
			Size = Size * 16 + D;
			bAny = true;
			if (Size > MaxBodyBytes) return EChunk::TooBig;
		}
		if (!bAny) return EChunk::Bad;
		Pos = Eol + 2;
		if (Size == 0)
		{
			for (;;)                                     // trailers, up to the empty line
			{
				const int32 TrailEol = FindEol(Pos, 4096);
				if (TrailEol == INDEX_NONE) return (In.Num() - Pos >= 4096) ? EChunk::Bad : EChunk::Incomplete;
				if (TrailEol == Pos) { End = Pos + 2; return EChunk::Done; }
				Pos = TrailEol + 2;
			}
		}
		if ((int64)Pos + Size + 2 > In.Num()) return EChunk::Incomplete;
		if ((int64)Body.Num() + Size > MaxBodyBytes) return EChunk::TooBig;
		Body.Append(In.GetData() + Pos, (int32)Size);
		if (In[Pos + Size] != '\r' || In[Pos + Size + 1] != '\n') return EChunk::Bad;
		Pos += (int32)Size + 2;
	}
}

/** Parse one request from the front of In. Strict on purpose (this is a security boundary): no bare LF, no folded or
 *  duplicate-critical headers, no Content-Length together with Transfer-Encoding. */
static EParse ParseRequest(const TArray<uint8>& In, FHttpReq& Req, FParseOut& Out)
{
	auto Bad = [&Out](int32 Status, const TCHAR* Message) { Out.Status = Status; Out.Message = Message; return EParse::Error; };
	int32 HeaderEnd = INDEX_NONE;
	const int32 Scan = FMath::Min(In.Num(), MaxHeaderBytes + 4);
	for (int32 i = 3; i < Scan; ++i)
	{
		if (In[i] == '\n' && In[i - 1] == '\r' && In[i - 2] == '\n' && In[i - 3] == '\r') { HeaderEnd = i + 1; break; }
	}
	if (HeaderEnd == INDEX_NONE) return In.Num() > MaxHeaderBytes ? Bad(431, TEXT("Request headers are too large")) : EParse::NeedMore;

	for (int32 i = 0; i < HeaderEnd; ++i) if (In[i] == 0) return Bad(400, TEXT("Malformed request"));
	const FString Head = Utf8ToString(In.GetData(), HeaderEnd - 4);
	TArray<FString> Lines;
	Head.ParseIntoArray(Lines, TEXT("\r\n"), false);
	if (Lines.Num() == 0) return Bad(400, TEXT("Empty request"));
	for (const FString& L : Lines) if (L.Contains(TEXT("\n")) || L.Contains(TEXT("\r"))) return Bad(400, TEXT("Malformed request"));

	TArray<FString> Parts;
	Lines[0].ParseIntoArray(Parts, TEXT(" "), false);
	if (Parts.Num() != 3 || Parts[0].IsEmpty() || !Parts[1].StartsWith(TEXT("/"))) return Bad(400, TEXT("Malformed request line"));
	Req.Method = Parts[0];
	if (Parts[2] == TEXT("HTTP/1.1")) Req.bHttp10 = false;
	else if (Parts[2] == TEXT("HTTP/1.0")) Req.bHttp10 = true;
	else return Bad(505, TEXT("Only HTTP/1.0 and HTTP/1.1 are supported"));
	Req.Path = Parts[1];
	int32 Cut = INDEX_NONE;
	if (Req.Path.FindChar(TEXT('?'), Cut) || Req.Path.FindChar(TEXT('#'), Cut)) Req.Path.LeftInline(Cut);

	for (int32 i = 1; i < Lines.Num(); ++i)
	{
		const FString& L = Lines[i];
		if (L.StartsWith(TEXT(" ")) || L.StartsWith(TEXT("\t"))) return Bad(400, TEXT("Folded headers are not accepted"));
		int32 Colon = INDEX_NONE;
		if (!L.FindChar(TEXT(':'), Colon) || Colon == 0) return Bad(400, TEXT("Malformed header"));
		const FString Name = L.Left(Colon);
		for (const TCHAR C : Name) if (C <= TEXT(' ') || C == TEXT(':') || C > 126) return Bad(400, TEXT("Malformed header name"));
		const FString Key = Name.ToLower();
		const FString Value = L.Mid(Colon + 1).TrimStartAndEnd();
		static const TCHAR* const Unique[] = { TEXT("host"), TEXT("content-length"), TEXT("transfer-encoding"), TEXT("origin"), TEXT("content-type"), TEXT("mcp-session-id") };
		for (const TCHAR* U : Unique) if (Key == U && Req.H.Contains(Key)) return Bad(400, TEXT("Duplicate header"));
		Req.H.Add(Key, Value);
	}

	const bool bChunked = Req.Has(TEXT("transfer-encoding"));
	if (bChunked)
	{
		if (!Req.Get(TEXT("transfer-encoding")).Equals(TEXT("chunked"), ESearchCase::IgnoreCase)) return Bad(501, TEXT("Only chunked transfer encoding is supported"));
		if (Req.Has(TEXT("content-length"))) return Bad(400, TEXT("Content-Length together with Transfer-Encoding"));
		Req.Body.Reset();
		int32 End = 0;
		switch (DecodeChunked(In, HeaderEnd, Req.Body, End))
		{
		case EChunk::Done: Out.Consumed = End; return EParse::Ready;
		case EChunk::Incomplete: Out.bSendContinue = Req.Get(TEXT("expect")).Equals(TEXT("100-continue"), ESearchCase::IgnoreCase); return EParse::NeedMore;
		case EChunk::TooBig: return Bad(413, TEXT("Request body is larger than 2 MB"));
		default: return Bad(400, TEXT("Malformed chunked body"));
		}
	}
	if (Req.Has(TEXT("content-length")))
	{
		const FString CL = Req.Get(TEXT("content-length"));
		if (!AllDigits(CL, 10)) return Bad(400, TEXT("Malformed Content-Length"));
		const int64 Len = FCString::Atoi64(*CL);
		if (Len > MaxBodyBytes) return Bad(413, TEXT("Request body is larger than 2 MB"));
		if ((int64)In.Num() < (int64)HeaderEnd + Len)
		{
			Out.bSendContinue = Req.Get(TEXT("expect")).Equals(TEXT("100-continue"), ESearchCase::IgnoreCase);
			return EParse::NeedMore;
		}
		Req.Body.Reset();
		Req.Body.Append(In.GetData() + HeaderEnd, (int32)Len);
		Out.Consumed = HeaderEnd + (int32)Len;
		return EParse::Ready;
	}
	Out.Consumed = HeaderEnd;
	return EParse::Ready;
}

static void AppendResponse(TArray<uint8>& Out, const FHttpResp& R, bool bKeepAlive)
{
	FString Head = FString::Printf(TEXT("HTTP/1.1 %d %s\r\n"), R.Status, StatusText(R.Status));
	const bool bBodyless = (R.Status == 204 || R.Status == 100);
	if (!R.ContentType.IsEmpty() && R.Body.Num() > 0) Head += FString::Printf(TEXT("Content-Type: %s\r\n"), *R.ContentType);
	if (!bBodyless) Head += FString::Printf(TEXT("Content-Length: %d\r\n"), R.Body.Num());
	Head += bKeepAlive ? TEXT("Connection: keep-alive\r\n") : TEXT("Connection: close\r\n");
	Head += TEXT("Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n");
	for (const TPair<FString, FString>& H : R.Headers) Head += FString::Printf(TEXT("%s: %s\r\n"), *H.Key, *H.Value);
	Head += TEXT("\r\n");
	FTCHARToUTF8 Conv(*Head);
	Out.Append((const uint8*)Conv.Get(), Conv.Length());
	if (!bBodyless) Out.Append(R.Body);
}

// --- sockets (macOS / Linux). Plain POSIX, because FSocket can't set SO_REUSEADDR without SO_REUSEPORT. ------------------
namespace Net
{
#if SKYMCP_SOCKETS
static void Configure(int Fd)
{
	const int Flags = fcntl(Fd, F_GETFL, 0);
	fcntl(Fd, F_SETFL, Flags | O_NONBLOCK);
	fcntl(Fd, F_SETFD, FD_CLOEXEC);
}
/** Listen on 127.0.0.1:Port and nothing else. SO_REUSEADDR (not SO_REUSEPORT): the port can be reopened straight after
 *  a stop, but a second game window can't bind it too. Returns the fd, or -1 with Err. */
static int Listen(int32 Port, FString& Err)
{
	const int Fd = ::socket(AF_INET, SOCK_STREAM, 0);
	if (Fd < 0) { Err = FString::Printf(TEXT("socket() failed: %s"), UTF8_TO_TCHAR(strerror(errno))); return -1; }
	int One = 1;
	::setsockopt(Fd, SOL_SOCKET, SO_REUSEADDR, &One, sizeof(One));
	sockaddr_in Addr;
	FMemory::Memzero(&Addr, sizeof(Addr));
	Addr.sin_family = AF_INET;
#if PLATFORM_MAC
	Addr.sin_len = sizeof(Addr);
#endif
	Addr.sin_port = htons((uint16)Port);
	Addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	if (::bind(Fd, (sockaddr*)&Addr, sizeof(Addr)) != 0)
	{
		Err = FString::Printf(TEXT("could not bind 127.0.0.1:%d (%s); is another Sky City window already using the LLM link?"), Port, UTF8_TO_TCHAR(strerror(errno)));
		::close(Fd);
		return -1;
	}
	if (::listen(Fd, 16) != 0)
	{
		Err = FString::Printf(TEXT("listen() failed: %s"), UTF8_TO_TCHAR(strerror(errno)));
		::close(Fd);
		return -1;
	}
	Configure(Fd);
	return Fd;
}
/** >= 0: a new loopback connection. -1: none waiting. -2: one was refused (not loopback), try again. */
static int Accept(int ListenFd)
{
	sockaddr_in Peer;
	socklen_t Len = sizeof(Peer);
	const int Fd = ::accept(ListenFd, (sockaddr*)&Peer, &Len);
	if (Fd < 0) return -1;
	if ((ntohl(Peer.sin_addr.s_addr) >> 24) != 127) { ::close(Fd); return -2; }
	Configure(Fd);
	int One = 1;
	::setsockopt(Fd, IPPROTO_TCP, TCP_NODELAY, &One, sizeof(One));
#ifdef SO_NOSIGPIPE
	::setsockopt(Fd, SOL_SOCKET, SO_NOSIGPIPE, &One, sizeof(One));
#endif
	return Fd;
}
/** > 0: bytes read. 0: nothing yet. -1: the peer closed or the socket failed. */
static int Read(int Fd, uint8* Buf, int32 Cap)
{
	for (;;)
	{
		const ssize_t N = ::recv(Fd, Buf, (size_t)Cap, 0);
		if (N > 0) return (int)N;
		if (N == 0) return -1;
		if (errno == EINTR) continue;
		if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
		return -1;
	}
}
/** >= 0: bytes written (0 = would block). -1: failed. */
static int Write(int Fd, const uint8* Buf, int32 Len)
{
	int Flags = 0;
#ifdef MSG_NOSIGNAL
	Flags |= MSG_NOSIGNAL;
#endif
	for (;;)
	{
		const ssize_t N = ::send(Fd, Buf, (size_t)Len, Flags);
		if (N >= 0) return (int)N;
		if (errno == EINTR) continue;
		if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
		return -1;
	}
}
static void ShutdownWrite(int Fd) { ::shutdown(Fd, SHUT_WR); }
static void Close(int Fd) { if (Fd >= 0) ::close(Fd); }
#else
static int Listen(int32, FString& Err) { Err = TEXT("The course MCP server needs macOS or Linux sockets"); return -1; }
static int Accept(int) { return -1; }
static int Read(int, uint8*, int32) { return -1; }
static int Write(int, const uint8*, int32) { return -1; }
static void ShutdownWrite(int) {}
static void Close(int) {}
#endif
}

struct FConn
{
	int Fd = -1;
	uint64 Id = 0;
	TArray<uint8> In;
	TArray<uint8> Out;
	int32 OutPos = 0;
	double LastActive = 0, RequestStart = 0, DrainUntil = 0;
	bool bCloseAfterWrite = false, bDraining = false, bPeerClosed = false, bContinueSent = false;
};

// ======================================================================================================================
// Tools
// ======================================================================================================================
struct FToolResult
{
	bool bError = false;
	FString Text;
};
static FToolResult Fail(const FString& Message) { FToolResult R; R.bError = true; R.Text = Message; return R; }
static FToolResult Done(const FObj& O) { FToolResult R; R.Text = ObjToString(O); return R; }
typedef FToolResult (*FToolFn)(ASkyCourseMode*, const FObj&);

// --- paths like pieces[6].branches[1].pieces[0] -----------------------------------------------------------------------
struct FPathTok { FString Name; int32 Index = INDEX_NONE; };

static bool TokenizePath(const FString& InPath, TArray<FPathTok>& Out, FString& Err)
{
	FString P = InPath.TrimStartAndEnd();
	if (P == TEXT("$")) P.Reset();
	else if (P.StartsWith(TEXT("$."))) P.RightChopInline(2);
	if (P.StartsWith(TEXT("course."))) P.RightChopInline(7);
	if (P.IsEmpty()) return true;
	TArray<FString> Parts;
	P.ParseIntoArray(Parts, TEXT("."), false);
	for (const FString& Part : Parts)
	{
		FPathTok T;
		int32 Open = INDEX_NONE;
		if (Part.FindChar(TEXT('['), Open))
		{
			if (!Part.EndsWith(TEXT("]")) || Open == 0) { Err = FString::Printf(TEXT("Path '%s': malformed part '%s'"), *InPath, *Part); return false; }
			const FString Num = Part.Mid(Open + 1, Part.Len() - Open - 2);
			if (!AllDigits(Num, 6)) { Err = FString::Printf(TEXT("Path '%s': '%s' needs a whole number in the brackets, like pieces[3]"), *InPath, *Part); return false; }
			T.Index = FCString::Atoi(*Num);
			T.Name = Part.Left(Open).ToLower();
		}
		else T.Name = Part.ToLower();
		if (T.Name != TEXT("pieces") && T.Name != TEXT("branches"))
		{
			Err = FString::Printf(TEXT("Path '%s': unknown part '%s'. Paths look like pieces[3] or pieces[6].branches[1].pieces[0]"), *InPath, *Part);
			return false;
		}
		Out.Add(T);
	}
	return true;
}

struct FNodeRef
{
	FObj Container;                 // the object holding the list: the course, a branch, or a split piece
	FString Field;                  // "pieces" or "branches"
	int32 Index = INDEX_NONE;       // element in Container[Field]; INDEX_NONE when the path names the whole list
	FObj Node;                      // the element itself, when Index is set
	bool bIsBranch = false;
	FString Canon;                  // the path, normalised
};

static FValArr GetList(const FObj& Container, const TCHAR* Field)
{
	const FValArr* A = nullptr;
	if (Container.IsValid() && Container->TryGetArrayField(Field, A) && A) return *A;
	return FValArr();
}

static bool WalkPath(const FObj& Root, const TArray<FPathTok>& T, const FString& InPath, FNodeRef& Out, FString& Err)
{
	Out = FNodeRef();
	Out.Container = Root;
	Out.Field = TEXT("pieces");
	Out.Canon = TEXT("pieces");
	FObj Cur = Root;
	bool bCurIsPiece = false;
	FString Canon;
	for (int32 i = 0; i < T.Num(); ++i)
	{
		const FPathTok& Tok = T[i];
		const bool bLast = (i == T.Num() - 1);
		if (Tok.Name == TEXT("pieces"))
		{
			if (bCurIsPiece) { Err = FString::Printf(TEXT("Path '%s': a piece has no 'pieces' list of its own. A split's pieces live in its branches: <split>.branches[n].pieces"), *InPath); return false; }
			Canon = Canon.IsEmpty() ? FString(TEXT("pieces")) : Canon + TEXT(".pieces");
			if (Tok.Index == INDEX_NONE)
			{
				if (!bLast) { Err = FString::Printf(TEXT("Path '%s': say which piece, like pieces[3]"), *InPath); return false; }
				Out.Container = Cur; Out.Field = TEXT("pieces"); Out.Index = INDEX_NONE; Out.Node = nullptr; Out.bIsBranch = false; Out.Canon = Canon;
				return true;
			}
			const FValArr List = GetList(Cur, TEXT("pieces"));
			if (Tok.Index >= List.Num())
			{
				Err = FString::Printf(TEXT("Path '%s': there is no %s[%d]; that list has %d piece%s%s"), *InPath, *Canon, Tok.Index, List.Num(), List.Num() == 1 ? TEXT("") : TEXT("s"),
					List.Num() > 0 ? *FString::Printf(TEXT(" (indices 0 to %d)"), List.Num() - 1) : TEXT(""));
				return false;
			}
			FObj El = List[Tok.Index].IsValid() ? List[Tok.Index]->AsObject() : nullptr;
			if (!El.IsValid()) { Err = FString::Printf(TEXT("Path '%s': %s[%d] is not a piece object"), *InPath, *Canon, Tok.Index); return false; }
			Canon += FString::Printf(TEXT("[%d]"), Tok.Index);
			Out.Container = Cur; Out.Field = TEXT("pieces"); Out.Index = Tok.Index; Out.Node = El; Out.bIsBranch = false; Out.Canon = Canon;
			Cur = El;
			bCurIsPiece = true;
		}
		else
		{
			if (!bCurIsPiece) { Err = FString::Printf(TEXT("Path '%s': 'branches' belongs to a split piece, as in pieces[6].branches[1]"), *InPath); return false; }
			if (Tok.Index == INDEX_NONE) { Err = FString::Printf(TEXT("Path '%s': say which branch, like branches[1]"), *InPath); return false; }
			const FValArr List = GetList(Cur, TEXT("branches"));
			if (Tok.Index >= List.Num())
			{
				Err = FString::Printf(TEXT("Path '%s': there is no %s.branches[%d]; this piece has %d branch%s"), *InPath, *Canon, Tok.Index, List.Num(), List.Num() == 1 ? TEXT("") : TEXT("es"));
				return false;
			}
			FObj El = List[Tok.Index].IsValid() ? List[Tok.Index]->AsObject() : nullptr;
			if (!El.IsValid()) { Err = FString::Printf(TEXT("Path '%s': %s.branches[%d] is not a branch object"), *InPath, *Canon, Tok.Index); return false; }
			Canon += FString::Printf(TEXT(".branches[%d]"), Tok.Index);
			Out.Container = Cur; Out.Field = TEXT("branches"); Out.Index = Tok.Index; Out.Node = El; Out.bIsBranch = true; Out.Canon = Canon;
			Cur = El;
			bCurIsPiece = false;
		}
	}
	return true;
}

/** A path to a list of pieces: "" or "pieces" (the main line), or "pieces[6].branches[1]" (a branch, with or without a trailing .pieces). */
static bool ResolveSeq(const FObj& Root, const FString& InPath, FNodeRef& Out, FString& Err)
{
	TArray<FPathTok> T;
	if (!TokenizePath(InPath, T, Err)) return false;
	if (!WalkPath(Root, T, InPath, Out, Err)) return false;
	if (T.Num() == 0) return true;
	if (Out.Index == INDEX_NONE) return true;                   // ended on ".pieces"
	if (Out.bIsBranch)                                          // a branch: its own list of pieces
	{
		Out.Container = Out.Node; Out.Field = TEXT("pieces"); Out.Index = INDEX_NONE; Out.Node = nullptr; Out.bIsBranch = false;
		Out.Canon += TEXT(".pieces");
		return true;
	}
	Err = FString::Printf(TEXT("Path '%s' names a single piece. For a list of pieces use '' (the main line) or a branch path such as pieces[6].branches[1]"), *InPath);
	return false;
}

/** A path to one piece or one branch. */
static bool ResolveNode(const FObj& Root, const FString& InPath, FNodeRef& Out, FString& Err)
{
	TArray<FPathTok> T;
	if (!TokenizePath(InPath, T, Err)) return false;
	if (T.Num() == 0) { Err = TEXT("Give the path of a piece, like pieces[3] or pieces[6].branches[1].pieces[0]"); return false; }
	if (!WalkPath(Root, T, InPath, Out, Err)) return false;
	if (Out.Index == INDEX_NONE) { Err = FString::Printf(TEXT("Path '%s' names a whole list. Name one piece (pieces[3]) or one branch (pieces[6].branches[1])"), *InPath); return false; }
	return true;
}

// --- reading the game ------------------------------------------------------------------------------------------------
static bool CourseToJson(ASkyCourseMode* M, FObj& Out, FString& Err)
{
	FVal V;
	if (!ParseJson(SkyCourse::Write(M->GetCourse()), V) || V->Type != EJson::Object) { Err = TEXT("Internal error: the course could not be written as JSON."); return false; }
	Out = V->AsObject();
	return true;
}

static void CollectSeqPaths(const FSkyCourse& C, int32 Seq, const FString& Path, TMap<int32, FString>& Out)
{
	if (!C.Seqs.IsValidIndex(Seq) || Out.Contains(Seq)) return;
	Out.Add(Seq, Path);
	const FSkySeq& S = C.Seqs[Seq];
	for (int32 i = 0; i < S.Pieces.Num(); ++i)
	{
		if (S.Pieces[i].Type != ESkyPiece::Split) continue;
		for (int32 b = 0; b < S.Pieces[i].Branches.Num(); ++b)
			CollectSeqPaths(C, S.Pieces[i].Branches[b].Seq, FString::Printf(TEXT("%s[%d].branches[%d].pieces"), *Path, i, b), Out);
	}
}

static FObj FrameJson(const FSkyFrame& F, int32 Lanes)
{
	FObj O = NewObj();
	O->SetField(TEXT("x"), JNum(F.P.X));
	O->SetField(TEXT("y"), JNum(F.P.Y));
	O->SetField(TEXT("z"), JNum(F.P.Z));
	O->SetField(TEXT("yaw_deg"), JNum(FMath::RadiansToDegrees(FMath::Atan2(F.F.Y, F.F.X)), 1));
	O->SetField(TEXT("pitch_deg"), JNum(FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(F.F.Z, -1.0, 1.0))), 1));
	if (Lanes > 0) O->SetField(TEXT("lanes"), JInt(Lanes));
	O->SetField(TEXT("width_m"), JNum(F.Width, 1));
	return O;
}

static FObj BoxJson(const FBox& B, bool bWithZ)
{
	FObj O = NewObj();
	O->SetField(TEXT("min_x"), JNum(B.Min.X, 1)); O->SetField(TEXT("max_x"), JNum(B.Max.X, 1));
	O->SetField(TEXT("min_y"), JNum(B.Min.Y, 1)); O->SetField(TEXT("max_y"), JNum(B.Max.Y, 1));
	if (bWithZ) { O->SetField(TEXT("min_z"), JNum(B.Min.Z, 1)); O->SetField(TEXT("max_z"), JNum(B.Max.Z, 1)); }
	return O;
}

static FString SummaryLine(ASkyCourseMode* M)
{
	const FSkyCourse& C = M->GetCourse();
	const FSkyBaked& B = M->GetBaked();
	FString S = FString::Printf(TEXT("Course '%s': %d piece%s, %.0f m, %s"), *C.Name, B.PieceCount, B.PieceCount == 1 ? TEXT("") : TEXT("s"), FMath::Abs(B.Length),
		B.bValid ? TEXT("valid") : TEXT("NOT valid"));
	if (B.Errors.Num()) S += FString::Printf(TEXT(", %d error%s"), B.Errors.Num(), B.Errors.Num() == 1 ? TEXT("") : TEXT("s"));
	if (B.Warnings.Num()) S += FString::Printf(TEXT(", %d warning%s"), B.Warnings.Num(), B.Warnings.Num() == 1 ? TEXT("") : TEXT("s"));
	return S + TEXT(".");
}

/** The facts from the bake, added to Into: valid, errors, warnings, size, gates, splits and the end frame of every list. */
static void AddFacts(ASkyCourseMode* M, const FObj& Into, bool bCompact = false)
{
	const FSkyCourse& C = M->GetCourse();
	FSkyBaked Local;
	const FSkyBaked* B = &M->GetBaked();
	const bool bHasPieces = C.Seqs.Num() > 0 && C.Seqs[0].Pieces.Num() > 0;
	if (!B->bValid && B->Errors.Num() == 0 && B->Segs.Num() == 0 && bHasPieces)    // the track hasn't baked it yet: do it here
	{
		SkyCourse::Bake(C, M->BuildArea(), Local);
		B = &Local;
	}
	Into->SetField(TEXT("valid"), JBool(B->bValid));
	Into->SetField(TEXT("errors"), JStrArr(B->Errors));
	Into->SetField(TEXT("warnings"), JStrArr(B->Warnings));
	if (!bCompact) Into->SetField(TEXT("name"), JStr(C.Name));
	Into->SetField(TEXT("laps"), JInt(C.Laps));
	Into->SetField(TEXT("piece_count"), JInt(B->PieceCount));
	Into->SetField(TEXT("lap_course"), JBool(B->bLapCourse));
	const ESkyPiece LastType = bHasPieces && C.Seqs[0].Pieces.Num() > 0 ? C.Seqs[0].Pieces.Last().Type : ESkyPiece::Count;
	const bool bHasFinish = LastType == ESkyPiece::Finish;    // a course with no finish piece still gets an implicit finish gate at its end
	const bool bClosed = LastType == ESkyPiece::Close;
	Into->SetField(TEXT("has_finish"), JBool(bHasFinish));
	Into->SetField(TEXT("length_m"), JNum(B->Length, 1));
	if (B->Bounds.IsValid && !bCompact)
	{
		FObj Bounds = NewObj();
		FObj Lo = NewObj(), Hi = NewObj();
		Lo->SetField(TEXT("x"), JNum(B->Bounds.Min.X, 1)); Lo->SetField(TEXT("y"), JNum(B->Bounds.Min.Y, 1)); Lo->SetField(TEXT("z"), JNum(B->Bounds.Min.Z, 1));
		Hi->SetField(TEXT("x"), JNum(B->Bounds.Max.X, 1)); Hi->SetField(TEXT("y"), JNum(B->Bounds.Max.Y, 1)); Hi->SetField(TEXT("z"), JNum(B->Bounds.Max.Z, 1));
		Bounds->SetField(TEXT("min"), JObj(Lo));
		Bounds->SetField(TEXT("max"), JObj(Hi));
		Into->SetField(TEXT("bounds"), JObj(Bounds));
	}
	Into->SetField(TEXT("min_z"), JNum(B->MinZ, 1));
	Into->SetField(TEXT("max_z"), JNum(B->MaxZ, 1));

	FValArr Gates;
	for (const FSkyBaked::FGate& G : B->Gates)
	{
		FObj O = FrameJson(G.At, 0);
		O->SetStringField(TEXT("type"), SkyCourse::PieceName(G.Type));
		O->SetField(TEXT("index"), JInt(G.Index));
		if (G.Type == ESkyPiece::Finish && !bHasFinish) O->SetBoolField(TEXT("implicit"), true);    // not a piece: the end of an unfinished track counts as the finish
		Gates.Add(JObj(O));
	}
	if (!bCompact) Into->SetField(TEXT("gates"), JArr(MoveTemp(Gates)));

	TMap<int32, FString> SeqPaths;
	CollectSeqPaths(C, 0, TEXT("pieces"), SeqPaths);

	FValArr Splits;
	for (const FSkyBaked::FSplitInfo& Sp : B->Splits)
	{
		const FString* Base = SeqPaths.Find(Sp.Seq);
		FObj O = FrameJson(Sp.At, 0);
		O->SetStringField(TEXT("path"), FString::Printf(TEXT("%s[%d]"), Base ? **Base : TEXT("pieces"), Sp.Piece));
		O->SetStringField(TEXT("gate"), Sp.Gate == ESkyGate::Lights ? TEXT("lights") : Sp.Gate == ESkyGate::Wall ? TEXT("wall") : TEXT("none"));
		FValArr Branches;
		if (C.Seqs.IsValidIndex(Sp.Seq) && C.Seqs[Sp.Seq].Pieces.IsValidIndex(Sp.Piece))
		{
			const FSkyPiece& P = C.Seqs[Sp.Seq].Pieces[Sp.Piece];
			for (int32 b = 0; b < P.Branches.Num(); ++b)
			{
				FObj Br = NewObj();
				Br->SetField(TEXT("branch"), JInt(b));
				Br->SetField(TEXT("lanes"), JInt(P.Branches[b].Lanes));
				Br->SetField(TEXT("angle"), JNum(P.Branches[b].Angle, 1));
				FValArr Laps;
				for (const int32 L : P.Branches[b].Laps) Laps.Add(JInt(L));
				Br->SetField(TEXT("laps"), P.Branches[b].Laps.Num() ? JArr(MoveTemp(Laps)) : JStr(TEXT("all")));
				Branches.Add(JObj(Br));
			}
		}
		O->SetField(TEXT("branches"), JArr(MoveTemp(Branches)));
		Splits.Add(JObj(O));
	}
	if (!bCompact) Into->SetField(TEXT("splits"), JArr(MoveTemp(Splits)));

	// where the next piece would start: the main line first, then every branch (add_pieces' branch_path is this path minus ".pieces")
	TArray<int32> SeqOrder;
	SeqPaths.GetKeys(SeqOrder);
	SeqOrder.Sort();
	FValArr Ends;
	for (const int32 Seq : SeqOrder)
	{
		int32 Lanes = 0;
		const FSkyFrame E = SkyCourse::EndOf(*B, C, Seq, &Lanes);
		FObj O = FrameJson(E, Lanes);
		FString Path = SeqPaths[Seq];
		O->SetStringField(TEXT("path"), Path);
		if (Seq == 0 && bClosed) O->SetStringField(TEXT("note"), TEXT("The course ends with a close piece, so it is closed. Remove the close piece (remove_pieces) before adding more."));
		if (Seq == 0 && bHasFinish) O->SetStringField(TEXT("note"), TEXT("The course ends with a finish piece, so it is finished. Remove the finish piece (remove_pieces) before adding more."));
		Ends.Add(JObj(O));
	}
	Into->SetField(TEXT("ends"), JArr(MoveTemp(Ends)));
	Into->SetField(TEXT("driving"), JBool(M->IsDriving()));
	if (!bCompact)
	{
		const FBox Area = M->BuildArea();
		if (Area.IsValid) Into->SetField(TEXT("build_area"), JObj(BoxJson(Area, false)));
		Into->SetField(TEXT("ground_z"), JNum(M->GroundZ()));
		FObj StartObj = NewObj();
		StartObj->SetField(TEXT("x"), JNum(C.Start.X)); StartObj->SetField(TEXT("y"), JNum(C.Start.Y)); StartObj->SetField(TEXT("z"), JNum(C.Start.Z)); StartObj->SetField(TEXT("yaw"), JNum(C.Yaw, 1));
		Into->SetField(TEXT("start"), JObj(StartObj));
	}

	// which branches are open on each lap (the course's "route" for that lap)
	if (C.Laps > 1 && B->Splits.Num() > 0)
	{
		FValArr Routes;
		for (int32 Lap = 1; Lap <= C.Laps; ++Lap)
		{
			FValArr Per;
			for (const FSkyBaked::FSplitInfo& Sp : B->Splits)
			{
				const FString* Base = SeqPaths.Find(Sp.Seq);
				FValArr Open;
				for (int32 b = 0; b < Sp.OpenLaps.Num(); ++b) if (Sp.OpenLaps[b].Contains(Lap)) Open.Add(JInt(b));
				FObj O = NewObj();
				O->SetStringField(TEXT("split"), FString::Printf(TEXT("%s[%d]"), Base ? **Base : TEXT("pieces"), Sp.Piece));
				O->SetField(TEXT("open_branches"), JArr(MoveTemp(Open)));
				Per.Add(JObj(O));
			}
			FObj L = NewObj();
			L->SetField(TEXT("lap"), JInt(Lap));
			L->SetField(TEXT("splits"), JArr(MoveTemp(Per)));
			Routes.Add(JObj(L));
		}
		Into->SetField(TEXT("lap_routes"), JArr(MoveTemp(Routes)));
	}
}

static FString BuildAreaText(ASkyCourseMode* M)
{
	const FBox A = M->BuildArea();
	if (!A.IsValid) return FString();
	return FString::Printf(TEXT("\nBuild area (metres, the whole course must stay inside): x %.0f to %.0f, y %.0f to %.0f."), A.Min.X, A.Max.X, A.Min.Y, A.Max.Y);
}

static FString FormatErrors(ASkyCourseMode* M, const FString& Head, const TArray<FString>& Errors)
{
	FString Out = Head;
	bool bArea = false;
	if (Errors.Num() > 0)
	{
		Out += FString::Printf(TEXT("\nErrors (%d):"), Errors.Num());
		for (int32 i = 0; i < Errors.Num() && i < 25; ++i)
		{
			Out += TEXT("\n- ") + Errors[i];
			const FString L = Errors[i].ToLower();
			if (L.Contains(TEXT("area")) || L.Contains(TEXT("outside")) || L.Contains(TEXT("bound"))) bArea = true;
		}
		if (Errors.Num() > 25) Out += FString::Printf(TEXT("\n- ... and %d more"), Errors.Num() - 25);
	}
	if (bArea && M) Out += BuildAreaText(M);
	return Out;
}

static bool RejectWhileDriving(ASkyCourseMode* M, FToolResult& Out)
{
	if (!M->IsDriving()) return false;
	Out = Fail(TEXT("A test drive or race is running, so the course can't be changed right now. Call stop_race first (the player goes back to building), then try again."));
	return true;
}

/** A short message on the player's screen, so they can follow what the LLM does (the builder shows it while building). */
static void Toast(ASkyCourseMode* M, const FString& Message, bool bBad = false)
{
	if (M) M->ShowToast(TEXT("LLM link"), Message.Left(90), bBad);
}
static FString FirstError(const TArray<FString>& Errors) { return Errors.Num() ? Errors[0] : FString(); }

/** Parse the edited course JSON and hand it to the game. Nothing changes if either step finds errors. */
static FToolResult CommitCourse(ASkyCourseMode* M, const FObj& Root, const FString& What, TFunctionRef<void(const FObj&)> Extra, const FString& FailNote = FString(), bool bCompact = false)
{
	FSkyCourse NewCourse;
	TArray<FString> Errors;
	if (!SkyCourse::Parse(ObjToString(Root), NewCourse, Errors))
	{
		Toast(M, TEXT("rejected: ") + FirstError(Errors), true);
		return Fail(FormatErrors(M, TEXT("The course was NOT changed: some settings are not valid. Fix them and call again."), Errors) + FailNote);
	}
	Errors.Reset();
	if (!M->SetCourse(NewCourse, Errors))
	{
		Toast(M, TEXT("rejected: ") + FirstError(Errors), true);
		return Fail(FormatErrors(M, TEXT("The course was NOT changed: it would not build. Fix the problems and call again."), Errors) + FailNote);
	}
	Toast(M, What);
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetStringField(TEXT("summary"), What + TEXT(" ") + SummaryLine(M));
	AddFacts(M, Out, bCompact);
	Extra(Out);
	return Done(Out);
}

// --- the tools -------------------------------------------------------------------------------------------------------
static const ANSICHAR* const WorkflowText = R"MCP(SKY CITY COURSE BUILDER: HOW TO USE THESE TOOLS

You are building a Hot Wheels-style stunt course inside Sky City, a driving game. A person is playing right now and can watch each piece appear as you add it. They will drive the course, and can race AI cars on it. Build something that is fun to drive, and tell them in plain words what you are doing.

THE WORKFLOW
1. get_player: where the player's car is, which way it faces, the build area (the box every piece must stay inside), and ground_z.
2. new_course (usually with near_player: true): a fresh course holding just the start gate and its starting grid, near the player. It replaces the course in the game, so call save_course first if the old one matters. If the player's car is outside the build area (get_player says so), the start goes to the nearest spot inside it, or the usual start spot; tell the player where. Let new_course choose the start: heights are absolute, and the build area's ground is at ground_z (about 10 m, NOT 0), so a start with z 0.3 would be buried in the ground. The reply's `start` shows what it chose.
3. add_pieces, a few at a time (3 to 10). Pieces snap end to end, so you describe shapes, never positions. Read every reply:
   - valid, errors, warnings: if a call is rejected NOTHING is changed. Errors carry a JSON path, like "pieces[7] (curve): radius 4 is below 8". Fix that piece and call again.
   - ends: where the next piece would start (x, y, z in metres, yaw in degrees, lanes) for the main line and for each split branch. Plan your next turn from it, and keep an eye on the build area.
   - length_m, min_z, max_z, bounds: how big the course is so far.
4. Finish it. A lap course ends with a close piece (a generated connector back into the start gate; it needs room to swing round, no tighter than a 15 m radius and no steeper than 35 degrees) and takes 1 to 9 laps: add the close piece first, then update_piece with path "course" and {"laps": 3}. A point-to-point course ends with a finish piece and has 1 lap. Checkpoints (up to 32) go along the way. Warnings never block a course: they are advice.
5. Tell the player what you built, save_course with a short name, and start_race when they want to drive it. get_results shows the times afterwards.

EDITING WHAT EXISTS
- get_course returns the whole course JSON plus the facts (lap_routes says which branch of each split is open on each lap). set_course takes a whole course back, to write a whole course at once.
- update_piece changes one piece in place, for example path "pieces[3]" with piece {"radius": 60}, and with path "course" it changes the course-level settings: {"laps": 3}, {"name": "..."}, {"skin": "neon"}, {"opponents": 3}, {"skill": 0.9}.
- remove_pieces takes pieces off the end (or from an index).
- Everything after an edited piece moves with it, so a change early in the course can push later pieces out of the build area or into each other. Then nothing changes and the error says where: fix the later pieces first, or rebuild with set_course.
- Paths count from 0. pieces[3] is the 4th main-line piece. A split's branches live inside it: pieces[6].branches[1] is its 2nd branch and pieces[6].branches[1].pieces[0] the first piece in that branch. Pass pieces[6].branches[1] as branch_path to add to a branch.
- Edits are refused while a race is running: call stop_race first.

GOOD HABITS
- Check the reply after every call, and build in short runs rather than all at once.
- Give a loop a straight run-up (and a booster) before it and a straight after it. Give a jump a straight approach, and a long straight after it: its landing pad is short and a fast car lands far down it.
- A split needs room, about its length + the longest branch + 60 m for the merge along the track. On 2 lanes, branches at about +24 and -24 degrees with a split length of 50 m work; +14 and -14 degrees with 30 m run into each other. End the branches heading the same way, then the merge joins them.
- A corkscrew dips a few metres below its entry deck: reach it on a raised deck (a ramp up first) or the ground check says it "sinks into the ground".
- An oval is the easy lap course: straights joined by two 180-degree curves of the same radius, both turning the same way, come back to the start line. Anything lopsided (a loop's sideways exit, a split's branches and merge, a lanes piece) moves the track sideways by a few metres, so read `ends` after it and choose the last curve's radius so the track comes back in line with the start (end y = start y when facing +x), then add close. Read `ends` again after every split before sizing the turns that follow.
- A branch that is open on laps beyond the course's laps only gives a warning until you set laps; that is expected.
- Keep long straights and wide curves for speed, and bank the fast corners.
- Use only the pieces and settings in the guide below: the limits are hard limits.
- You cannot steer the player's car. You can build, save, load, start and stop races and read the results; the player does the driving.)MCP";

static FToolResult ToolGuide(ASkyCourseMode*, const FObj&)
{
	FToolResult R;
	R.Text = A2S(WorkflowText) + TEXT("\n\n") + SkyCourse::Guide();
	return R;
}

static FToolResult ToolGetCourse(ASkyCourseMode* M, const FObj& A)
{
	bool bInclude = true;
	ArgBool(A, TEXT("include_course"), bInclude);
	FObj Out = NewObj();
	Out->SetStringField(TEXT("summary"), SummaryLine(M));
	AddFacts(M, Out);
	if (bInclude)
	{
		FObj C;
		FString Err;
		if (!CourseToJson(M, C, Err)) return Fail(Err);
		Out->SetField(TEXT("course"), JObj(C));
	}
	return Done(Out);
}

static FToolResult ToolSetCourse(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	FObj Root;
	if (!ArgObject(A, TEXT("course"), Root)) return Fail(TEXT("set_course needs a 'course' object: the course JSON (format skycity-course, see get_course_guide and the 'course' in get_course)."));
	// a missing start, or a start without z, is filled in (z = just above the build area's ground) rather than refused
	FString Filled;
	const TSharedPtr<FJsonObject>* StartPtr = nullptr;
	if (!Root->TryGetObjectField(TEXT("start"), StartPtr) || !StartPtr || !StartPtr->IsValid())
	{
		FObj Cur;
		FString Err;
		if (CourseToJson(M, Cur, Err) && Cur->TryGetObjectField(TEXT("start"), StartPtr) && StartPtr && StartPtr->IsValid())
		{
			Root->SetObjectField(TEXT("start"), *StartPtr);
			Filled = TEXT(" The course had no start, so the current start was kept.");
		}
	}
	else if (!(*StartPtr)->HasField(TEXT("z")))
	{
		(*StartPtr)->SetField(TEXT("z"), JNum(M->GroundZ() + 0.5));
		Filled = FString::Printf(TEXT(" The start had no z, so it was put at %.2f (just above the build area's ground, z %.2f)."), M->GroundZ() + 0.5, M->GroundZ());
	}
	bool bCompact = false;
	ArgBool(A, TEXT("compact"), bCompact);
	return CommitCourse(M, Root, TEXT("Course replaced.") + Filled, [](const FObj&) {}, FString(), bCompact);
}

static FToolResult ToolAddPieces(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	FValArr NewPieces;
	if (!ArgArray(A, TEXT("pieces"), NewPieces) || NewPieces.Num() == 0)
		return Fail(TEXT("add_pieces needs a non-empty 'pieces' array, for example {\"pieces\":[{\"type\":\"straight\",\"length\":40},{\"type\":\"curve\",\"angle\":90,\"radius\":40}]}."));
	if (NewPieces.Num() > MaxPiecesPerCall) return Fail(FString::Printf(TEXT("Add at most %d pieces per call (you sent %d). Add a few at a time and check the result."), MaxPiecesPerCall, NewPieces.Num()));
	for (int32 i = 0; i < NewPieces.Num(); ++i)
	{
		FString Type;
		if (!NewPieces[i].IsValid() || NewPieces[i]->Type != EJson::Object) return Fail(FString::Printf(TEXT("pieces[%d] of your call is not an object. Each piece looks like {\"type\":\"straight\",\"length\":40}."), i));
		const FObj P = NewPieces[i]->AsObject();
		if (!ArgString(P, TEXT("type"), Type)) return Fail(FString::Printf(TEXT("pieces[%d] of your call has no \"type\"."), i));
		Type = Type.TrimStartAndEnd().ToLower();
		if (SkyCourse::PieceFromName(Type) == ESkyPiece::Count)
		{
			FString Names;
			for (int32 t = 0; t < (int32)ESkyPiece::Count; ++t) Names += (t ? TEXT(", ") : TEXT("")) + FString(SkyCourse::PieceName((ESkyPiece)t));
			return Fail(FString::Printf(TEXT("pieces[%d] of your call: unknown piece type '%s'. The types are: %s."), i, *Type, *Names));
		}
		P->SetStringField(TEXT("type"), Type);
	}
	FString BranchPath;
	ArgString(A, TEXT("branch_path"), BranchPath);
	int32 Index = INDEX_NONE;
	const bool bHasIndex = HasArg(A, TEXT("index"));
	if (bHasIndex && !ArgInt(A, TEXT("index"), Index)) return Fail(TEXT("'index' must be a whole number."));

	FObj Root;
	FString Err;
	if (!CourseToJson(M, Root, Err)) return Fail(Err);
	FNodeRef Ref;
	if (!ResolveSeq(Root, BranchPath, Ref, Err)) return Fail(Err);
	FValArr List = GetList(Ref.Container, TEXT("pieces"));
	if (!bHasIndex) Index = List.Num();
	else if (Index < 0 || Index > List.Num()) return Fail(FString::Printf(TEXT("index %d is out of range: %s has %d pieces, so use 0 to %d (or leave index out to append)."), Index, *Ref.Canon, List.Num(), List.Num()));
	TArray<FString> Added;
	for (int32 i = 0; i < NewPieces.Num(); ++i)
	{
		List.Insert(NewPieces[i], Index + i);
		Added.Add(FString::Printf(TEXT("%s[%d]"), *Ref.Canon, Index + i));
	}
	Ref.Container->SetArrayField(TEXT("pieces"), List);
	const int32 Count = NewPieces.Num();
	bool bCompact = false;
	ArgBool(A, TEXT("compact"), bCompact);
	return CommitCourse(M, Root, FString::Printf(TEXT("Added %d piece%s to %s."), Count, Count == 1 ? TEXT("") : TEXT("s"), *Ref.Canon),
		[&Added](const FObj& Out) { Out->SetField(TEXT("added_paths"), JStrArr(Added)); },
		FString::Printf(TEXT("\nThe %d piece%s from this call would have been %s to %s; errors name pieces by their place in the whole course."),
			Count, Count == 1 ? TEXT("") : TEXT("s"), *Added[0], *Added.Last()), bCompact);
}

static FToolResult ToolRemovePieces(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	int32 Count = 1;
	if (HasArg(A, TEXT("count")) && !ArgInt(A, TEXT("count"), Count)) return Fail(TEXT("'count' must be a whole number."));
	if (Count < 1) return Fail(TEXT("'count' must be at least 1."));
	FString BranchPath;
	ArgString(A, TEXT("branch_path"), BranchPath);
	int32 Index = INDEX_NONE;
	const bool bHasIndex = HasArg(A, TEXT("index"));
	if (bHasIndex && !ArgInt(A, TEXT("index"), Index)) return Fail(TEXT("'index' must be a whole number."));

	FObj Root;
	FString Err;
	if (!CourseToJson(M, Root, Err)) return Fail(Err);
	FNodeRef Ref;
	if (!ResolveSeq(Root, BranchPath, Ref, Err)) return Fail(Err);
	FValArr List = GetList(Ref.Container, TEXT("pieces"));
	const int32 N = List.Num();
	int32 From = 0;
	if (bHasIndex)
	{
		if (Index < 0 || Index >= N) return Fail(FString::Printf(TEXT("index %d is out of range: %s has %d piece%s."), Index, *Ref.Canon, N, N == 1 ? TEXT("") : TEXT("s")));
		if (Index + Count > N) return Fail(FString::Printf(TEXT("Can't remove %d pieces from index %d: %s has only %d."), Count, Index, *Ref.Canon, N));
		From = Index;
	}
	else
	{
		if (Count > N) return Fail(FString::Printf(TEXT("Can't remove %d pieces: %s has only %d."), Count, *Ref.Canon, N));
		From = N - Count;
	}
	if (Ref.Container == Root && From == 0 && N > 0 && List[0].IsValid() && List[0]->Type == EJson::Object)
	{
		FString First;
		List[0]->AsObject()->TryGetStringField(TEXT("type"), First);
		if (First.Equals(TEXT("start"), ESearchCase::IgnoreCase)) return Fail(TEXT("The start gate (pieces[0]) can't be removed. Use new_course to begin again."));
	}
	List.RemoveAt(From, Count);
	Ref.Container->SetArrayField(TEXT("pieces"), List);
	bool bCompact = false;
	ArgBool(A, TEXT("compact"), bCompact);
	return CommitCourse(M, Root, FString::Printf(TEXT("Removed %d piece%s from %s."), Count, Count == 1 ? TEXT("") : TEXT("s"), *Ref.Canon), [](const FObj&) {}, FString(), bCompact);
}

static FToolResult ToolUpdatePiece(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	FString Path;
	if (!ArgString(A, TEXT("path"), Path)) return Fail(TEXT("update_piece needs a 'path' such as \"pieces[3]\", \"pieces[6].branches[1].pieces[0]\" or \"course\" (for laps, name, skin and the other course settings)."));
	FObj Patch;
	if (!ArgObject(A, TEXT("piece"), Patch)) return Fail(TEXT("update_piece needs a 'piece' object with the settings to change, for example {\"radius\": 60}."));
	FObj Root;
	FString Err;
	if (!CourseToJson(M, Root, Err)) return Fail(Err);
	const FString PathLower = Path.TrimStartAndEnd().ToLower();
	if (PathLower == TEXT("course") || PathLower == TEXT("$") || PathLower == TEXT("settings"))
	{
		// the course-level settings: name, author, start, lanes, lane_width, skin, laps, opponents, skill, catch_up (a given "start" merges with the old one)
		for (const TPair<FString, FVal>& KV : Patch->Values)
		{
			if (!KV.Value.IsValid() || KV.Value->Type == EJson::Null) { Root->RemoveField(KV.Key); continue; }
			const TSharedPtr<FJsonObject>* OldSub = nullptr;
			if (KV.Key == TEXT("start") && KV.Value->Type == EJson::Object && Root->TryGetObjectField(TEXT("start"), OldSub) && OldSub && OldSub->IsValid())
			{
				for (const TPair<FString, FVal>& SV : KV.Value->AsObject()->Values) (*OldSub)->SetField(SV.Key, SV.Value);
			}
			else Root->SetField(KV.Key, KV.Value);
		}
		bool bCompactC = false;
		ArgBool(A, TEXT("compact"), bCompactC);
		return CommitCourse(M, Root, TEXT("Course settings changed."), [](const FObj&) {}, FString(), bCompactC);
	}
	FNodeRef Ref;
	if (!ResolveNode(Root, Path, Ref, Err)) return Fail(Err);

	FString OldType, NewType;
	Ref.Node->TryGetStringField(TEXT("type"), OldType);
	const bool bHasType = ArgString(Patch, TEXT("type"), NewType);
	if (bHasType)
	{
		NewType = NewType.TrimStartAndEnd().ToLower();
		if (!Ref.bIsBranch && SkyCourse::PieceFromName(NewType) == ESkyPiece::Count) return Fail(FString::Printf(TEXT("Unknown piece type '%s'."), *NewType));
		Patch->SetStringField(TEXT("type"), NewType);
	}
	if (!Ref.bIsBranch && bHasType && !NewType.Equals(OldType, ESearchCase::IgnoreCase))
	{
		FObj Fresh = NewObj();                       // a different type is a different piece: nothing carries over
		for (const TPair<FString, FVal>& KV : Patch->Values) if (KV.Value.IsValid() && KV.Value->Type != EJson::Null) Fresh->SetField(KV.Key, KV.Value);
		FValArr List = GetList(Ref.Container, *Ref.Field);
		List[Ref.Index] = JObj(Fresh);
		Ref.Container->SetArrayField(Ref.Field, List);
	}
	else
	{
		for (const TPair<FString, FVal>& KV : Patch->Values)
		{
			if (!KV.Value.IsValid() || KV.Value->Type == EJson::Null) Ref.Node->RemoveField(KV.Key);    // null = back to the default
			else Ref.Node->SetField(KV.Key, KV.Value);
		}
	}
	bool bCompact = false;
	ArgBool(A, TEXT("compact"), bCompact);
	return CommitCourse(M, Root, FString::Printf(TEXT("Updated %s."), *Ref.Canon), [&Ref](const FObj& Out) { Out->SetStringField(TEXT("updated_path"), Ref.Canon); }, FString(), bCompact);
}

static FToolResult ToolNewCourse(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	FSkyCourse C;
	FString Text;
	if (ArgString(A, TEXT("name"), Text)) { C.Name = SkyCourse::SafeName(Text); if (C.Name.IsEmpty()) C.Name = TEXT("New Course"); }
	if (ArgString(A, TEXT("author"), Text)) C.Author = Text.Left(48).TrimStartAndEnd();
	if (HasArg(A, TEXT("lanes")))
	{
		int32 L = 0;
		if (!ArgInt(A, TEXT("lanes"), L) || L < SkyCourse::MinLanes || L > SkyCourse::MaxLanes) return Fail(TEXT("'lanes' must be a whole number from 1 to 4."));
		C.Lanes = L;
	}
	if (HasArg(A, TEXT("skin")))
	{
		if (!ArgString(A, TEXT("skin"), Text)) return Fail(TEXT("'skin' must be \"unveil\", \"classic\" or \"neon\"."));
		Text = Text.ToLower();
		if (Text == TEXT("unveil")) C.Skin = ESkySkin::Unveil;
		else if (Text == TEXT("classic")) C.Skin = ESkySkin::Classic;
		else if (Text == TEXT("neon")) C.Skin = ESkySkin::Neon;
		else return Fail(TEXT("'skin' must be \"unveil\", \"classic\" or \"neon\"."));
	}
	if (HasArg(A, TEXT("opponents")))
	{
		int32 O = 0;
		if (!ArgInt(A, TEXT("opponents"), O) || O < 0 || O > SkyCourse::MaxOpponents) return Fail(TEXT("'opponents' must be a whole number from 0 to 7."));
		C.Opponents = O;
	}
	if (HasArg(A, TEXT("skill")))
	{
		double S = 0;
		if (!ArgNum(A, TEXT("skill"), S) || S < 0.3 || S > 1.2) return Fail(TEXT("'skill' must be a number from 0.3 to 1.2."));
		C.Skill = S;
	}
	if (HasArg(A, TEXT("lane_width")))
	{
		double LW = 0;
		if (!ArgNum(A, TEXT("lane_width"), LW) || LW < SkyCourse::MinLaneWidth || LW > SkyCourse::MaxLaneWidth) return Fail(TEXT("'lane_width' must be a number from 5.5 to 11 (5.5 standard, 8 wide, 11 extra wide)."));
		C.LaneWidth = LW;
	}
	if (HasArg(A, TEXT("catch_up")) && !ArgBool(A, TEXT("catch_up"), C.bCatchUp)) return Fail(TEXT("'catch_up' must be true or false."));
	bool bExample = false;
	ArgBool(A, TEXT("example"), bExample);
	if (bExample && HasArg(A, TEXT("lane_width")) && !FMath::IsNearlyEqual(C.LaneWidth, SkyCourse::DefaultLaneWidth, 0.01))
		return Fail(TEXT("The example course is built for 8 m lanes: leave out 'lane_width' with example, or start an empty course and set the width."));

	// where the start goes: an explicit start, else ahead of the player, else the build area's usual start spot. The builder's
	// StarterCourse() clamps a wanted spot into the build area and puts it at the right height.
	double X = 0, Y = 0, Yaw = 0, Z = 0;
	FString Placed;
	FObj StartObj;
	bool bNear = false;
	ArgBool(A, TEXT("near_player"), bNear);
	ASkysterCar* Car = M->GetCar();
	if (ArgObject(A, TEXT("start"), StartObj))
	{
		if (!ArgNum(StartObj, TEXT("x"), X) || !ArgNum(StartObj, TEXT("y"), Y)) return Fail(TEXT("'start' needs numbers x and y (metres), and optionally z and yaw (degrees)."));
		ArgNum(StartObj, TEXT("yaw"), Yaw);
		if (!ArgNum(StartObj, TEXT("z"), Z)) Z = M->GroundZ() + 0.5;
		Placed = TEXT("the start you gave");
	}
	else
	{
		FVector Near = FVector::ZeroVector;
		const FVector* NearPtr = nullptr;
		if (bNear && Car)
		{
			const FVector P = SkyCourse::FromUE(Car->GetActorLocation());
			const FVector F = SkyCourse::DirToUE(Car->GetActorForwardVector());
			Yaw = FMath::RadiansToDegrees(FMath::Atan2(F.Y, F.X));
			const double H = FMath::Max(FVector2D(F.X, F.Y).Size(), 1.0e-6);
			Near = FVector(P.X + 10.0 * F.X / H, P.Y + 10.0 * F.Y / H, P.Z);
			NearPtr = &Near;
			Placed = TEXT("10 m ahead of the player's car, facing the way the car faces");
		}
		else Placed = (bNear ? TEXT("the build area's usual start spot, as the player's car isn't in the world yet") : TEXT("the build area's usual start spot"));
		const FSkyCourse Spot = M->StarterCourse(NearPtr, Yaw);
		X = Spot.Start.X; Y = Spot.Start.Y; Z = Spot.Start.Z; Yaw = Spot.Yaw;
		if (NearPtr && (FMath::Abs(X - Near.X) > 1.0 || FMath::Abs(Y - Near.Y) > 1.0))
			Placed = TEXT("the spot in the build area nearest the player's car, which is outside the area, facing the way the car faces");
	}
	C.Start = FVector(X, Y, Z);
	C.Yaw = Yaw;
	if (bExample)
	{
		FSkyCourse E = SkyCourse::Example(C.Start, C.Yaw);
		E.Name = C.Name; E.Author = C.Author; E.Lanes = C.Lanes; E.Skin = C.Skin; E.Opponents = C.Opponents; E.Skill = C.Skill; E.bCatchUp = C.bCatchUp;
		C = E;
	}
	else
	{
		C.Seqs.Reset();
		C.Seqs.Add(FSkySeq());
		C.Seqs[0].Pieces.Add(SkyCourse::DefaultPiece(ESkyPiece::Start, C.Lanes));
	}
	TArray<FString> Errors;
	if (!M->SetCourse(C, Errors))
	{
		Toast(M, TEXT("rejected: ") + FirstError(Errors), true);
		return Fail(FormatErrors(M, FString::Printf(TEXT("The new course was NOT created (the old course is still in the game). Start tried: x %.1f, y %.1f, z %.1f, yaw %.0f."), X, Y, Z, Yaw), Errors));
	}
	Toast(M, FString::Printf(TEXT("new course '%s'"), *C.Name));
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetStringField(TEXT("summary"), FString::Printf(TEXT("New course '%s' started at x %.1f, y %.1f, facing %.0f degrees: %s. %s"), *C.Name, X, Y, Yaw, *Placed, *SummaryLine(M)));
	AddFacts(M, Out);
	return Done(Out);
}

static FToolResult ToolListCourses(ASkyCourseMode* M, const FObj&)
{
	FObj Out = NewObj();
	const TArray<FString> Names = M->ListCourses();
	Out->SetField(TEXT("courses"), JStrArr(Names));
	Out->SetStringField(TEXT("current"), M->GetCourse().Name);
	Out->SetStringField(TEXT("summary"), FString::Printf(TEXT("%d saved course%s."), Names.Num(), Names.Num() == 1 ? TEXT("") : TEXT("s")));
	return Done(Out);
}

static bool FindCourseName(const TArray<FString>& Names, const FString& Name, FString& Found)
{
	for (const FString& N : Names) if (N.Equals(Name, ESearchCase::IgnoreCase)) { Found = N; return true; }
	return false;
}

static FToolResult ToolSaveCourse(ASkyCourseMode* M, const FObj& A)
{
	FString Requested;
	if (!ArgString(A, TEXT("name"), Requested) || Requested.TrimStartAndEnd().IsEmpty()) Requested = M->GetCourse().Name;
	const FString Name = SkyCourse::SafeName(Requested);
	if (Name.IsEmpty()) return Fail(TEXT("That name has no usable characters. Names use letters, digits, spaces, dashes and underscores (up to 48)."));
	bool bOverwrite = false;
	ArgBool(A, TEXT("overwrite"), bOverwrite);
	FString Existing;
	const bool bExists = FindCourseName(M->ListCourses(), Name, Existing);
	if (bExists && !bOverwrite)
		return Fail(FString::Printf(TEXT("A saved course called '%s' already exists, so nothing was saved. Pick another name, or pass overwrite: true if you mean to replace it."), *Existing));
	FString Err;
	if (!M->SaveCourse(Name, Err)) return Fail(Err.IsEmpty() ? FString(TEXT("The course could not be saved.")) : Err);
	Toast(M, FString::Printf(TEXT("saved '%s'"), *Name));
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetStringField(TEXT("name"), Name);
	Out->SetBoolField(TEXT("overwritten"), bExists);
	Out->SetStringField(TEXT("summary"), FString::Printf(TEXT("Saved course '%s'%s. The player can load it from the course menu."), *Name, bExists ? TEXT(" (replacing the earlier save)") : TEXT("")));
	return Done(Out);
}

static FToolResult ToolLoadCourse(ASkyCourseMode* M, const FObj& A)
{
	FToolResult Blocked;
	if (RejectWhileDriving(M, Blocked)) return Blocked;
	FString Requested;
	if (!ArgString(A, TEXT("name"), Requested)) return Fail(TEXT("load_course needs a 'name'. Call list_courses to see the saved courses."));
	const FString Name = SkyCourse::SafeName(Requested);
	const TArray<FString> Names = M->ListCourses();
	FString Found;
	if (Name.IsEmpty() || !FindCourseName(Names, Name, Found))
		return Fail(FString::Printf(TEXT("There is no saved course called '%s'. Saved courses: %s."), *Requested, Names.Num() ? *FString::Join(Names, TEXT(", ")) : TEXT("(none)")));
	FString Err;
	if (!M->LoadCourse(Found, Err)) return Fail(Err.IsEmpty() ? FString(TEXT("The course could not be loaded.")) : Err);
	Toast(M, FString::Printf(TEXT("loaded '%s'"), *Found));
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetStringField(TEXT("summary"), FString::Printf(TEXT("Loaded '%s'. %s"), *Found, *SummaryLine(M)));
	AddFacts(M, Out);
	FObj C;
	FString CErr;
	if (CourseToJson(M, C, CErr)) Out->SetField(TEXT("course"), JObj(C));
	return Done(Out);
}

static FToolResult ToolGetPlayer(ASkyCourseMode* M, const FObj&)
{
	ASkysterCar* Car = M->GetCar();
	if (!Car) return Fail(TEXT("The player's car isn't in the world yet."));
	const FVector P = SkyCourse::FromUE(Car->GetActorLocation());
	const FVector F = SkyCourse::DirToUE(Car->GetActorForwardVector());
	const double Yaw = FMath::RadiansToDegrees(FMath::Atan2(F.Y, F.X));
	const double Mph = Car->GetSpeedMph();
	const FBox Area = M->BuildArea();
	FObj Out = NewObj();
	Out->SetStringField(TEXT("summary"), FString::Printf(TEXT("The car is at x %.1f, y %.1f, z %.1f facing %.0f degrees, doing %.0f mph.%s"), P.X, P.Y, P.Z, Yaw, Mph,
		Area.IsValid ? (Area.Min.X <= P.X && P.X <= Area.Max.X && Area.Min.Y <= P.Y && P.Y <= Area.Max.Y ? TEXT(" It is inside the build area.") : TEXT(" It is OUTSIDE the build area.")) : TEXT("")));
	Out->SetField(TEXT("x"), JNum(P.X)); Out->SetField(TEXT("y"), JNum(P.Y)); Out->SetField(TEXT("z"), JNum(P.Z));
	Out->SetField(TEXT("heading_deg"), JNum(Yaw, 1));
	Out->SetField(TEXT("speed_mph"), JNum(Mph, 1));
	Out->SetField(TEXT("speed_mps"), JNum(Mph / 2.23694, 1));
	Out->SetStringField(TEXT("car_mode"), Car->GetMode());
	const double H = FMath::Max(FVector2D(F.X, F.Y).Size(), 1.0e-6);
	FObj Ahead = NewObj();
	Ahead->SetField(TEXT("x"), JNum(P.X + 20.0 * F.X / H)); Ahead->SetField(TEXT("y"), JNum(P.Y + 20.0 * F.Y / H));
	Out->SetField(TEXT("point_20m_ahead"), JObj(Ahead));
	if (Area.IsValid)
	{
		Out->SetField(TEXT("build_area"), JObj(BoxJson(Area, false)));
		Out->SetBoolField(TEXT("inside_build_area"), Area.Min.X <= P.X && P.X <= Area.Max.X && Area.Min.Y <= P.Y && P.Y <= Area.Max.Y);
	}
	else Out->SetStringField(TEXT("build_area"), TEXT("unbounded"));
	Out->SetField(TEXT("ground_z"), JNum(M->GroundZ()));
	{
		const FSkyCourse Spot = M->StarterCourse();
		FObj U = NewObj();
		U->SetField(TEXT("x"), JNum(Spot.Start.X)); U->SetField(TEXT("y"), JNum(Spot.Start.Y)); U->SetField(TEXT("z"), JNum(Spot.Start.Z)); U->SetField(TEXT("yaw"), JNum(Spot.Yaw, 1));
		Out->SetField(TEXT("usual_start"), JObj(U));
	}
	Out->SetBoolField(TEXT("driving"), M->IsDriving());
	Out->SetStringField(TEXT("course"), M->GetCourse().Name);
	Out->SetStringField(TEXT("frame"), TEXT("Metres and degrees in the course frame. Yaw is counter-clockwise from +x: 0 faces +x, 90 faces +y."));
	return Done(Out);
}

static FToolResult ToolStartRace(ASkyCourseMode* M, const FObj& A)
{
	const FSkyBaked& B = M->GetBaked();
	if (!B.bValid) return Fail(FormatErrors(M, TEXT("The course has errors, so it can't be raced yet."), B.Errors));
	int32 Opponents = -1;
	if (HasArg(A, TEXT("opponents")))
	{
		if (!ArgInt(A, TEXT("opponents"), Opponents) || Opponents < 0 || Opponents > SkyCourse::MaxOpponents) return Fail(TEXT("'opponents' must be a whole number from 0 to 7."));
	}
	if (HasArg(A, TEXT("skill")))
	{
		double Skill = 0;
		if (!ArgNum(A, TEXT("skill"), Skill) || Skill < 0.3 || Skill > 1.2) return Fail(TEXT("'skill' must be a number from 0.3 to 1.2."));
		TArray<FString> Errors;
		if (!M->Edit([Skill](FSkyCourse& C) { C.Skill = Skill; }, Errors)) return Fail(FormatErrors(M, TEXT("Could not set the AI skill."), Errors));
	}
	M->StartTestDrive(Opponents);
	if (!M->IsDriving()) return Fail(TEXT("The race did not start."));
	const FSkyCourse& C = M->GetCourse();
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetBoolField(TEXT("driving"), true);
	Out->SetField(TEXT("opponents"), JInt(Opponents >= 0 ? Opponents : C.Opponents));
	Out->SetField(TEXT("skill"), JNum(C.Skill));
	Out->SetField(TEXT("laps"), JInt(C.Laps));
	Out->SetStringField(TEXT("summary"), TEXT("The player's car is on the starting grid and the 3-2-1 countdown is running. The player drives; you can't steer. Poll get_results for times, and call stop_race to return to building."));
	return Done(Out);
}

static FToolResult ToolStopRace(ASkyCourseMode* M, const FObj&)
{
	const bool bWas = M->IsDriving();
	M->StopTestDrive();
	FObj Out = NewObj();
	Out->SetBoolField(TEXT("ok"), true);
	Out->SetBoolField(TEXT("was_driving"), bWas);
	Out->SetStringField(TEXT("summary"), bWas ? TEXT("The race is stopped and the player is back to building.") : TEXT("No race was running."));
	return Done(Out);
}

static FToolResult ToolGetResults(ASkyCourseMode* M, const FObj&)
{
	FObj Out = NewObj();
	ASkyCourseRace* Race = M->GetRace();
	FValArr Rows;
	if (Race)
	{
		for (const ASkyCourseRace::FResult& R : Race->GetResults())
		{
			FObj O = NewObj();
			O->SetStringField(TEXT("name"), R.Name);
			O->SetBoolField(TEXT("player"), R.bPlayer);
			O->SetField(TEXT("place"), JInt(R.Place));
			O->SetField(TEXT("lap"), JInt(R.Lap));
			O->SetBoolField(TEXT("finished"), R.bFinished);
			if (R.Time >= 0) O->SetField(TEXT("time_s"), JNum(R.Time, 3));
			FValArr Laps, Splits;
			for (const double T : R.LapTimes) Laps.Add(JNum(T, 3));
			for (const double T : R.Splits) Splits.Add(JNum(T, 3));
			O->SetField(TEXT("lap_times_s"), JArr(MoveTemp(Laps)));
			O->SetField(TEXT("splits_s"), JArr(MoveTemp(Splits)));
			Rows.Add(JObj(O));
		}
	}
	const bool bRunning = Race && Race->IsRunning();
	Out->SetBoolField(TEXT("race_running"), bRunning);
	Out->SetBoolField(TEXT("driving"), M->IsDriving());
	if (Race && Race->BestLap() >= 0) Out->SetField(TEXT("best_lap_s"), JNum(Race->BestLap(), 3));
	const int32 NumRows = Rows.Num();
	Out->SetField(TEXT("results"), JArr(MoveTemp(Rows)));
	Out->SetStringField(TEXT("summary"), Race ? (bRunning ? TEXT("A race is running; these are the live results.") : (NumRows > 0 ? TEXT("No race is running; these are the results of the last one.") : TEXT("No race is running and there are no results (the game clears them when a race stops): read them while the race runs or right after the finish."))) : TEXT("No race has been run yet."));
	return Done(Out);
}

// --- the tool table --------------------------------------------------------------------------------------------------
#define SKYMCP_PIECE_PROPS R"MCP("type":{"type":"string","enum":["start","finish","checkpoint","straight","curve","ramp","jump","loop","corkscrew","wallride","booster","lanes","split","close"]},"length":{"type":"number","description":"Metres. straight 2-300, ramp 4-150, corkscrew 20-260, wallride 15-150, booster 4-30, lanes 10-80, split 15-80."},"angle":{"type":"number","description":"curve: degrees, -270 to 270, positive turns left."},"radius":{"type":"number","description":"Metres. curve 8-300, loop 6-30."},"bank":{"type":"number","description":"curve: degrees of bank, -45 to 45."},"rise":{"type":"number","description":"ramp: metres up (+) or down (-), -60 to 60."},"gap":{"type":"number","description":"jump: open gap in metres, 4-80."},"drop":{"type":"number","description":"jump: landing pad height relative to the lip in metres, -30 to 30."},"offset":{"type":"number","description":"loop: sideways shift of the exit in metres, 0 to 4 x the course lane_width + 1 (default: the track width + 1)."},"turns":{"type":"number","description":"corkscrew: 0.5-2."},"side":{"type":"string","enum":["left","right"],"description":"wallride: which side the track twists up."},"lanes":{"type":"integer","minimum":1,"maximum":4,"description":"lanes piece: the new lane count."},"align":{"type":"string","enum":["center","left","right"],"description":"lanes piece: which side widens or narrows."},"gate":{"type":"string","enum":["lights","wall","none"],"description":"split: how the open branch is shown."},"merge_length":{"type":"number","description":"split: metres of the merge, 15-80."},"merge_lanes":{"type":"integer","minimum":1,"maximum":4,"description":"split: lane count after the merge."})MCP"
// a piece inside a split branch: the same settings (a split nested deeper is written the same way)
#define SKYMCP_LEAF_PIECE R"MCP({"type":"object","required":["type"],"properties":{)MCP" SKYMCP_PIECE_PROPS R"MCP(}})MCP"
#define SKYMCP_PIECE_SCHEMA R"MCP({"type":"object","description":"One track piece. Always has \"type\"; the other settings depend on the type (see get_course_guide).","required":["type"],"properties":{)MCP" SKYMCP_PIECE_PROPS R"MCP(,"branches":{"type":"array","minItems":2,"maxItems":4,"description":"split: 2-4 branches, each with its own pieces.","items":{"type":"object","properties":{"lanes":{"type":"integer","minimum":1,"maximum":4},"angle":{"type":"number","description":"Degrees the branch heads off at, -45 to 45."},"laps":{"type":"array","items":{"type":"integer","minimum":1},"description":"Laps this branch is open on. Leave out for every lap."},"pieces":{"type":"array","items":)MCP" SKYMCP_LEAF_PIECE R"MCP(,"description":"The branch's own pieces, same format."}}}}}})MCP"

struct FToolDef
{
	const ANSICHAR* Name;
	const ANSICHAR* Title;
	const ANSICHAR* Description;
	const ANSICHAR* Schema;
	bool bReadOnly, bDestructive, bIdempotent, bNeedsMode;
	FToolFn Fn;
};

static const FToolDef GTools[] =
{
	{ "get_course_guide", "Read the course-building guide",
	  "Read this first. Returns the guide to building courses in Sky City: how these tools fit together, the course JSON format, every track piece with its settings and hard limits, and tips for courses that are fun to drive. It changes nothing. Call it once at the start of a session.",
	  R"MCP({"type":"object","properties":{}})MCP", true, false, true, false, &ToolGuide },

	{ "get_player", "Where the player's car is",
	  "Where the player's car is right now, in the same coordinates courses use (x, y, z in metres; heading in degrees counter-clockwise from +x, like a course's start yaw), its speed, the build area (the box every piece of a course must stay inside), ground_z (the ground height there: heights are absolute) and the usual_start spot. Use it to place a course near the player (new_course with near_player does it for you; if the car is outside the build area the start goes to the nearest spot inside it).",
	  R"MCP({"type":"object","properties":{}})MCP", true, false, true, true, &ToolGetPlayer },

	{ "new_course", "Start a new course",
	  "Start a new course, replacing the one in the game (it is not saved: call save_course first if the player might want the old one). The new course holds just the start gate and its 30 m starting grid, ready for add_pieces. With near_player true the start goes a few metres ahead of the player's car, facing the way the car faces, on the ground there. Or give an exact start {x, y, yaw}. With neither, the start goes at the build area's usual start spot. All settings are optional. Course-level settings that need more than a start gate (laps above 1) are set later with set_course. The reply has the same facts as get_course, including where to continue building (ends).",
	  R"MCP({"type":"object","properties":{"name":{"type":"string","description":"Course name: letters, digits, spaces, dashes and underscores, up to 48 characters. It becomes the file name when saved."},"near_player":{"type":"boolean","description":"Put the start just ahead of the player's car, facing its heading. Default false."},"start":{"type":"object","description":"Exact start in metres and degrees. Overrides near_player.","properties":{"x":{"type":"number"},"y":{"type":"number"},"z":{"type":"number","description":"Deck height at the start. Leave out to sit on the ground there."},"yaw":{"type":"number","description":"Degrees counter-clockwise from +x: 0 faces +x, 90 faces +y."}},"required":["x","y"]},"lanes":{"type":"integer","minimum":1,"maximum":4,"description":"Lanes at the start. Default 2."},"lane_width":{"type":"number","enum":[5.5,8,11],"description":"Metres per lane for the whole course: 5.5 standard, 8 wide, 11 extra wide. Default 8."},"catch_up":{"type":"boolean","description":"AI rubber band: a car far ahead eases off, one far behind pushes (never the player). Default true."},"skin":{"type":"string","enum":["unveil","classic","neon"],"description":"How the track looks. Default unveil."},"opponents":{"type":"integer","minimum":0,"maximum":7,"description":"Default number of AI opponents."},"skill":{"type":"number","minimum":0.3,"maximum":1.2,"description":"AI skill."},"author":{"type":"string"},"example":{"type":"boolean","description":"Start from the short example course instead of an empty start gate. Default false."}}})MCP",
	  false, true, false, true, &ToolNewCourse },

	{ "add_pieces", "Add track pieces",
	  "Add track pieces, in order, to the end of the main line (or to a split's branch with branch_path). Each piece starts exactly where the previous one ended, facing the same way, at the same height and lane count, so you describe shapes, never positions. The whole course is checked and built in the game straight away. The reply says valid or not, lists errors with JSON paths, and gives `ends`: where the next piece would start for the main line and every branch. If anything is wrong NOTHING is added. Add 3 to 10 pieces at a time, read the reply, and plan from `ends`. A piece looks like {\"type\":\"straight\",\"length\":60}; get_course_guide lists every type and its limits. A split carries its branches: {\"type\":\"split\",\"gate\":\"lights\",\"branches\":[{\"lanes\":2,\"angle\":12,\"laps\":[1,3],\"pieces\":[{\"type\":\"straight\",\"length\":80}]},{\"lanes\":2,\"angle\":-12,\"pieces\":[{\"type\":\"straight\",\"length\":80}]}]}. Add the branches' pieces inside the split, or add to a branch later with branch_path.",
	  R"MCP({"type":"object","required":["pieces"],"properties":{"pieces":{"type":"array","minItems":1,"maxItems":100,"description":"The pieces to add, in order.","items":)MCP" SKYMCP_PIECE_SCHEMA R"MCP(},"branch_path":{"type":"string","description":"Add to a split's branch instead of the main line, e.g. \"pieces[6].branches[1]\". Leave out for the main line."},"index":{"type":"integer","minimum":0,"description":"Insert before this position in the list instead of appending at the end. Later pieces shift along."},"compact":{"type":"boolean","description":"Leave the repeated facts (gates, splits, bounds, start, build area) out of the reply: shorter. Default false."}}})MCP",
	  false, false, false, true, &ToolAddPieces },

	{ "remove_pieces", "Remove track pieces",
	  "Remove pieces from the end of the main line (or of a branch with branch_path), `count` at a time (default 1). With `index`, remove `count` pieces starting at that position instead. The whole course is checked again; if the result would be broken, nothing changes. The start gate (pieces[0]) can't be removed: use new_course. Removing a split removes its branches with it.",
	  R"MCP({"type":"object","properties":{"count":{"type":"integer","minimum":1,"description":"How many pieces to remove. Default 1."},"branch_path":{"type":"string","description":"Remove from a split's branch instead of the main line, e.g. \"pieces[6].branches[1]\"."},"index":{"type":"integer","minimum":0,"description":"Start removing at this position instead of from the end."},"compact":{"type":"boolean","description":"Leave the repeated facts (gates, splits, bounds, start, build area) out of the reply: shorter. Default false."}}})MCP",
	  false, true, false, true, &ToolRemovePieces },

	{ "update_piece", "Change one piece",
	  "Change one piece, one split branch, or the course settings in place. `path` says which: \"pieces[3]\" is the 4th piece of the main line, \"pieces[6].branches[1].pieces[0]\" the first piece of the 2nd branch of the split at pieces[6]. `piece` holds only the settings to change, for example {\"radius\": 60}; null removes a setting (back to its default); a different `type` replaces the piece. A branch path such as \"pieces[6].branches[1]\" changes that branch's lanes, angle or laps, and the path \"course\" changes the course-level settings: laps, name, author, lanes, lane_width, catch_up, skin, opponents, skill, start (a lap course needs its close piece before laps goes above 1). Everything after the piece moves with it, so a change early in the course can push later pieces out of the build area: then nothing changes and the error says where. The reply has the same facts as add_pieces.",
	  R"MCP({"type":"object","required":["path","piece"],"properties":{"path":{"type":"string","description":"JSON path of the piece or branch, counting from 0, e.g. \"pieces[3]\" or \"pieces[6].branches[1].pieces[0]\"; or \"course\" for laps, name, skin, opponents, skill, lane_width (5.5, 8 or 11), catch_up."},"piece":{"type":"object","description":"The settings to change, e.g. {\"radius\": 60} or {\"lanes\": 3}. null removes a setting."},"compact":{"type":"boolean","description":"Leave the repeated facts (gates, splits, bounds, start, build area) out of the reply: shorter. Default false."}}})MCP",
	  false, true, true, true, &ToolUpdatePiece },

	{ "set_course", "Replace the whole course",
	  "Replace the whole course with the given course JSON (the format of `course` in get_course; get_course_guide describes it). Use it to write a whole course at once; for course-level settings alone (laps, name, skin, opponents, skill) update_piece with path \"course\" is shorter. start.z is an absolute height: leave it out and it is put just above the build area's ground. If the course has any error nothing changes and the reply lists every error with its JSON path. Not saved until you call save_course.",
	  R"MCP({"type":"object","required":["course"],"properties":{"course":{"type":"object","description":"The complete course: {\"format\":\"skycity-course\",\"version\":2,\"name\":...,\"start\":{x,y,z,yaw},\"lanes\":2,\"lane_width\":8,\"skin\":\"unveil\",\"laps\":1,\"opponents\":0,\"skill\":0.8,\"catch_up\":true,\"pieces\":[...]}. A version 1 file without lane_width has 5.5 m lanes."},"compact":{"type":"boolean","description":"Leave the repeated facts (gates, splits, bounds, start, build area) out of the reply: shorter. Default false."}}})MCP",
	  false, true, true, true, &ToolSetCourse },

	{ "get_course", "Read the current course",
	  "The course as it is in the game right now: the full course JSON plus facts from the game's check and build. valid, errors, warnings, length_m, bounds, min_z and max_z, ground_z (the height of the ground in the build area; deck heights are absolute), gates (start, checkpoints, finish), splits with their branches, lap_routes (which branches are open on each lap), and `ends`: for the main line (path \"pieces\") and every split branch (path \"pieces[6].branches[1].pieces\") the frame where the next piece would start (x, y, z, yaw_deg, pitch_deg, lanes). Also the start, build_area and whether a race is running. Set include_course false for just the facts (smaller).",
	  R"MCP({"type":"object","properties":{"include_course":{"type":"boolean","description":"Include the whole course JSON. Default true."}}})MCP",
	  true, false, true, true, &ToolGetCourse },

	{ "list_courses", "List saved courses",
	  "The names of the saved courses (the ones in the player's courses folder), and the name of the course in the game now.",
	  R"MCP({"type":"object","properties":{}})MCP", true, false, true, true, &ToolListCourses },

	{ "save_course", "Save the current course",
	  "Save the course in the game under a name (letters, digits, spaces, dashes and underscores; anything else is dropped). Leave the name out to use the course's own name. It will not replace an existing save unless you pass overwrite: true. The player can load it later from the course menu, and share the file.",
	  R"MCP({"type":"object","properties":{"name":{"type":"string","description":"Name to save as. Default: the course's name."},"overwrite":{"type":"boolean","description":"Replace a saved course of the same name. Default false."}}})MCP",
	  false, false, true, true, &ToolSaveCourse },

	{ "load_course", "Load a saved course",
	  "Load a saved course into the game, replacing the course there (save_course first if it matters). Use list_courses to see the names. The reply has the course and the same facts as get_course.",
	  R"MCP({"type":"object","required":["name"],"properties":{"name":{"type":"string","description":"The saved course's name, from list_courses."}}})MCP",
	  false, true, true, true, &ToolLoadCourse },

	{ "start_race", "Start a race on this course",
	  "Start a test drive or race on the current course: the player's car goes on the starting grid behind the start gate (with AI opponents beside it, if any), a 3-2-1 countdown runs, and then the PLAYER drives; you can't steer the car. The course must be valid. Edits are refused while the race runs: call stop_race to go back to building, and get_results for times. opponents (0-7) and skill (0.3-1.2) override the course's defaults.",
	  R"MCP({"type":"object","properties":{"opponents":{"type":"integer","minimum":0,"maximum":7,"description":"AI opponents. Default: the course's setting."},"skill":{"type":"number","minimum":0.3,"maximum":1.2,"description":"AI skill. Default: the course's setting."}}})MCP",
	  false, false, false, true, &ToolStartRace },

	{ "stop_race", "Stop the race",
	  "Stop the test drive or race and put the player back in the builder. Does nothing if no race is running.",
	  R"MCP({"type":"object","properties":{}})MCP", false, false, true, true, &ToolStopRace },

	{ "get_results", "Race results",
	  "Lap times, split times and places for the current or last race: for the player and each AI opponent. Also says whether a race is running.",
	  R"MCP({"type":"object","properties":{}})MCP", true, false, true, true, &ToolGetResults },
};

static const FToolDef* FindTool(const FString& Name)
{
	for (const FToolDef& T : GTools) if (Name.Equals(A2S(T.Name), ESearchCase::CaseSensitive)) return &T;
	return nullptr;
}

static FString GameVersion()
{
	// Project Settings > Description > Project Version (DefaultGame.ini); "0.1.0" is the first public release
	FString V;
	GConfig->GetString(TEXT("/Script/EngineSettings.GeneralProjectSettings"), TEXT("ProjectVersion"), V, GGameIni);
	V.TrimStartAndEndInline();
	return V.IsEmpty() ? FString(TEXT("0.1.0")) : V;
}

static const ANSICHAR* const InstructionsText =
	"Sky City Course Builder: build Hot Wheels-style driving courses inside the running game while the player watches. "
	"Call get_course_guide first: it explains the tools, the course format and every track piece with its limits. "
	"Then get_player, new_course (near_player), add_pieces a few at a time (read each reply), save_course, start_race. "
	"These tools only touch courses; they cannot reach anything else on the computer.";

}   // namespace SkyMcp

// ======================================================================================================================
// The server
// ======================================================================================================================
using namespace SkyMcp;

struct FSkyCourseMcp::FState
{
	int32 Port = SkyCourse::McpPort;
	int ListenFd = -1;
	FTSTicker::FDelegateHandle TickHandle;
	TWeakObjectPtr<ASkyCourseMode> Director;       // the Course Builder this server belongs to
	bool bHadMode = false;
	TArray<TUniquePtr<FConn>> Conns;
	TMap<FString, double> Sessions;
	TSet<FString> EndedSessions;
	uint64 NextConnId = 1;
	uint32 RoundRobin = 0;
	int32 Budget = 0;
	FObj ToolsListCache;
	FString LastClient;          // clientInfo.name of the last initialize
	double LastClientT = 0;      // FPlatformTime::Seconds() of the last request from a client

	bool Open(FString& Err)
	{
		ListenFd = Net::Listen(Port, Err);
		return ListenFd >= 0;
	}

	void Shutdown()
	{
		if (TickHandle.IsValid()) { FTSTicker::RemoveTicker(TickHandle); TickHandle.Reset(); }
		for (TUniquePtr<FConn>& C : Conns) Net::Close(C->Fd);
		Conns.Reset();
		if (ListenFd >= 0) { Net::Close(ListenFd); ListenFd = -1; }
		Sessions.Reset();
	}

	bool OwnerGone() const
	{
		if (!bHadMode) return false;
		ASkyCourseMode* M = Director.Get();
		if (!M || !IsValid(M) || M->IsActorBeingDestroyed()) return true;
		const UWorld* World = M->GetWorld();
		return !World || World->bIsTearingDown;
	}

	// --- the per-frame pump ---
	bool Tick(float)
	{
		if (ListenFd < 0) return false;
		if (OwnerGone())
		{
			UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: the Course Builder is gone, closing port %d"), Port);
			Shutdown();
			return false;
		}
		const double Now = FPlatformTime::Seconds();
		for (int32 i = 0; i < 4; ++i)
		{
			const int Fd = Net::Accept(ListenFd);
			if (Fd == -1) break;
			if (Fd < 0) continue;
			if (Conns.Num() >= MaxConnections) { Net::Close(Fd); continue; }
			TUniquePtr<FConn> C = MakeUnique<FConn>();
			C->Fd = Fd;
			C->Id = NextConnId++;
			C->LastActive = Now;
			Conns.Add(MoveTemp(C));
		}
		Budget = MaxRequestsPerTick;
		const int32 N = Conns.Num();
		TArray<int32> Dead;
		for (int32 k = 0; k < N; ++k)
		{
			const int32 i = (int32)((RoundRobin + (uint32)k) % (uint32)N);
			if (!Service(*Conns[i], Now)) Dead.Add(i);
		}
		RoundRobin++;
		Dead.Sort();
		for (int32 d = Dead.Num() - 1; d >= 0; --d)
		{
			Net::Close(Conns[Dead[d]]->Fd);
			Conns.RemoveAt(Dead[d]);
		}
		return ListenFd >= 0;
	}

	/** Push queued output. False if the socket failed. */
	bool Flush(FConn& C, double Now)
	{
		while (C.OutPos < C.Out.Num())
		{
			const int W = Net::Write(C.Fd, C.Out.GetData() + C.OutPos, C.Out.Num() - C.OutPos);
			if (W < 0) return false;
			if (W == 0) break;
			C.OutPos += W;
			C.LastActive = Now;
		}
		if (C.OutPos >= C.Out.Num())
		{
			C.Out.Reset();
			C.OutPos = 0;
			if (C.bCloseAfterWrite && !C.bDraining)
			{
				Net::ShutdownWrite(C.Fd);                       // FIN after the answer; then read and discard until the client leaves
				C.bDraining = true;
				C.DrainUntil = Now + DrainSeconds;
			}
		}
		return true;
	}

	void Reply(FConn& C, const FHttpResp& R, bool bKeepAlive, double Now)
	{
		const bool bKeep = bKeepAlive && !R.bClose;
		AppendResponse(C.Out, R, bKeep);
		if (!bKeep) C.bCloseAfterWrite = true;
		if (R.Status >= 400) UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: answered %d %s"), R.Status, StatusText(R.Status));
	}

	/** One connection's turn. False = close it. */
	bool Service(FConn& C, double Now)
	{
		if (!Flush(C, Now)) return false;
		if (C.OutPos < C.Out.Num()) return (Now - C.LastActive) < WriteSeconds;

		// read whatever has arrived
		uint8 Buf[16384];
		const int32 MaxReads = C.bDraining ? 256 : 16;       // 256 KB a tick normally; a client being turned away may still be sending 2 MB
		for (int32 k = 0; k < MaxReads; ++k)
		{
			const int R = Net::Read(C.Fd, Buf, sizeof(Buf));
			if (R == 0) break;
			if (R < 0) { C.bPeerClosed = true; break; }
			C.LastActive = Now;
			if (C.bDraining) continue;                            // discard
			if (C.In.Num() == 0) C.RequestStart = Now;
			if (C.In.Num() + R > MaxBodyBytes + MaxHeaderBytes + 65536)
			{
				FHttpResp E; E.bClose = true; E.SetError(413, TEXT("Request is larger than 2 MB"));
				Reply(C, E, false, Now);
				C.In.Reset();
				return Flush(C, Now);
			}
			C.In.Append(Buf, R);
		}
		if (C.bDraining) return !C.bPeerClosed && Now < C.DrainUntil;

		// run complete requests, as many as this tick's budget allows
		while (Budget > 0 && C.In.Num() > 0 && C.OutPos >= C.Out.Num() && !C.bCloseAfterWrite)
		{
			FHttpReq Req;
			FParseOut P;
			const EParse Parsed = ParseRequest(C.In, Req, P);
			if (Parsed == EParse::NeedMore)
			{
				if (P.bSendContinue && !C.bContinueSent)
				{
					static const char Continue100[] = "HTTP/1.1 100 Continue\r\n\r\n";
					C.Out.Append((const uint8*)Continue100, sizeof(Continue100) - 1);
					C.bContinueSent = true;
				}
				break;
			}
			if (Parsed == EParse::Error)
			{
				FHttpResp E; E.bClose = true; E.SetError(P.Status, P.Message);
				Reply(C, E, false, Now);
				C.In.Reset();
				break;
			}
			--Budget;
			FHttpResp Resp;
			HandleRequest(Req, Resp);
			const FString Conn = Req.Get(TEXT("connection")).ToLower();
			const bool bKeepAlive = Req.bHttp10 ? Conn.Contains(TEXT("keep-alive")) : !Conn.Contains(TEXT("close"));
			Reply(C, Resp, bKeepAlive, Now);
			C.In.RemoveAt(0, P.Consumed, EAllowShrinking::No);
			C.bContinueSent = false;
			if (!Flush(C, Now)) return false;
		}
		if (!Flush(C, Now)) return false;
		if (C.OutPos < C.Out.Num()) return true;
		if (C.bDraining) return true;

		if (C.bPeerClosed && C.Out.Num() == 0 && (C.In.Num() == 0 || Budget > 0)) return false;     // nothing more is coming, or what's left is a partial request
		if (C.In.Num() > 0 && !C.bCloseAfterWrite && (Now - C.RequestStart) > RequestSeconds)
		{
			FHttpResp E; E.bClose = true; E.SetError(408, TEXT("The request did not arrive in time"));
			Reply(C, E, false, Now);
			C.In.Reset();
			return Flush(C, Now);
		}
		if (C.In.Num() == 0 && (Now - C.LastActive) > IdleSeconds) return false;
		return true;
	}

	// --- HTTP routing ---
	void HandleRequest(const FHttpReq& Req, FHttpResp& Resp)
	{
		const bool bHasOrigin = Req.Has(TEXT("origin"));
		const FString Origin = Req.Get(TEXT("origin"));
		if (bHasOrigin && !OriginAllowed(Origin))
		{
			UE_LOG(LogSkyMcp, Warning, TEXT("Course MCP: refused a request from Origin '%s'"), *Origin.Left(80));
			Resp.SetError(403, TEXT("Forbidden: this server only accepts requests from localhost"));
			Resp.bClose = true;
			return;
		}
		if (!Req.bHttp10 || Req.Has(TEXT("host")))
		{
			if (!Req.Has(TEXT("host")) || !LocalAuthority(Req.Get(TEXT("host"))))
			{
				UE_LOG(LogSkyMcp, Warning, TEXT("Course MCP: refused a request with Host '%s'"), *Req.Get(TEXT("host")).Left(80));
				Resp.SetError(403, TEXT("Forbidden: use http://127.0.0.1 or http://localhost to reach this server"));
				Resp.bClose = true;
				return;
			}
		}
		if (bHasOrigin)                                       // only local origins get here: let a local web page read the answers
		{
			Resp.Add(TEXT("Access-Control-Allow-Origin"), Origin.TrimStartAndEnd());
			Resp.Add(TEXT("Access-Control-Expose-Headers"), TEXT("Mcp-Session-Id"));
			Resp.Add(TEXT("Vary"), TEXT("Origin"));
		}
		if (Req.Path != TEXT("/mcp") && Req.Path != TEXT("/mcp/"))
		{
			Resp.SetError(404, TEXT("Not found. The MCP endpoint is /mcp"));
			return;
		}
		if (Req.Method == TEXT("OPTIONS"))
		{
			Resp.Status = 204;
			Resp.Add(TEXT("Allow"), TEXT("POST, DELETE, OPTIONS"));
			if (bHasOrigin)
			{
				Resp.Add(TEXT("Access-Control-Allow-Methods"), TEXT("POST, DELETE, OPTIONS"));
				Resp.Add(TEXT("Access-Control-Allow-Headers"), TEXT("Content-Type, Accept, Authorization, Mcp-Session-Id, Mcp-Protocol-Version, Last-Event-ID"));
				Resp.Add(TEXT("Access-Control-Max-Age"), TEXT("600"));
			}
			return;
		}
		if (Req.Method == TEXT("DELETE"))
		{
			const FString Id = Req.Get(TEXT("mcp-session-id"));
			if (Id.IsEmpty()) { Resp.SetError(400, TEXT("DELETE needs an Mcp-Session-Id header")); return; }
			Sessions.Remove(Id);
			EndedSessions.Add(Id);
			if (EndedSessions.Num() > 64) EndedSessions.Reset();
			Resp.Status = 200;
			return;
		}
		if (Req.Method != TEXT("POST"))
		{
			// GET would open a server-to-client SSE stream; this server has none (JSON responses only)
			Resp.SetError(405, TEXT("This server does not offer an SSE stream. POST JSON-RPC messages to /mcp."));
			Resp.Add(TEXT("Allow"), TEXT("POST, DELETE, OPTIONS"));
			return;
		}
		HandlePost(Req, Resp);
	}

	void HandlePost(const FHttpReq& Req, FHttpResp& Resp)
	{
		if (!Req.Has(TEXT("content-length")) && !Req.Has(TEXT("transfer-encoding"))) { Resp.SetError(411, TEXT("POST needs a Content-Length")); return; }
		const FString Type = Req.Get(TEXT("content-type")).ToLower();
		if (!Type.StartsWith(TEXT("application/json"))) { Resp.SetError(415, TEXT("Content-Type must be application/json")); return; }
		const FString Version = Req.Get(TEXT("mcp-protocol-version"));
		if (!Version.IsEmpty())
		{
			bool bKnown = false;
			for (const TCHAR* P : Protocols) if (Version == P) bKnown = true;
			if (!bKnown)
			{
				Resp.SetJson(400, ObjToString(RpcError(nullptr, -32600, FString::Printf(TEXT("Unsupported MCP-Protocol-Version '%s'. This server speaks 2025-06-18 and 2025-03-26."), *Version.Left(40)))));
				return;
			}
		}
		const FString SessionId = Req.Get(TEXT("mcp-session-id"));
		if (!SessionId.IsEmpty() && EndedSessions.Contains(SessionId))
		{
			Resp.SetJson(404, ObjToString(RpcError(nullptr, -32001, TEXT("Session ended. Send a new initialize request without Mcp-Session-Id."))));
			return;
		}
		FVal Body;
		if (Req.Body.Num() == 0 || !ParseJson(Utf8ToString(Req.Body.GetData(), Req.Body.Num()), Body))
		{
			Resp.SetJson(400, ObjToString(RpcError(nullptr, -32700, TEXT("Parse error: the body is not valid JSON"))));
			return;
		}
		FString NewSession;
		if (Body->Type == EJson::Array)
		{
			const FValArr& Items = Body->AsArray();
			if (Items.Num() == 0) { Resp.SetJson(400, ObjToString(RpcError(nullptr, -32600, TEXT("Invalid Request: empty batch")))); return; }
			FValArr Out;
			for (const FVal& Item : Items)
			{
				const FObj R = ProcessMessage(Item, true, NewSession);
				if (R.IsValid()) Out.Add(JObj(R));
			}
			if (Out.Num() == 0) { Resp.Status = 202; return; }
			Resp.SetJson(200, ArrToString(Out));
		}
		else if (Body->Type == EJson::Object)
		{
			const FObj R = ProcessMessage(Body, false, NewSession);
			if (!R.IsValid()) { Resp.Status = 202; return; }       // a notification, or a reply to us: accepted, no body
			Resp.SetJson(200, ObjToString(R));
		}
		else
		{
			Resp.SetJson(400, ObjToString(RpcError(nullptr, -32600, TEXT("Invalid Request: expected a JSON-RPC object or batch"))));
			return;
		}
		if (!NewSession.IsEmpty()) Resp.Add(TEXT("Mcp-Session-Id"), NewSession);
	}

	// --- JSON-RPC ---
	static FObj RpcError(const FVal& Id, int32 Code, const FString& Message)
	{
		FObj E = NewObj();
		E->SetField(TEXT("code"), JInt(Code));
		E->SetStringField(TEXT("message"), Message);
		FObj R = NewObj();
		R->SetStringField(TEXT("jsonrpc"), TEXT("2.0"));
		R->SetField(TEXT("id"), Id.IsValid() ? Id : JNull());
		R->SetField(TEXT("error"), JObj(E));
		return R;
	}
	static FObj RpcResult(const FVal& Id, const FObj& Result)
	{
		FObj R = NewObj();
		R->SetStringField(TEXT("jsonrpc"), TEXT("2.0"));
		R->SetField(TEXT("id"), Id.IsValid() ? Id : JNull());
		R->SetField(TEXT("result"), JObj(Result));
		return R;
	}

	/** The response object, or null when there is nothing to send back (a notification, or a reply to a request we never made). */
	FObj ProcessMessage(const FVal& Msg, bool bInBatch, FString& OutSession)
	{
		if (!Msg.IsValid() || Msg->Type != EJson::Object) return RpcError(nullptr, -32600, TEXT("Invalid Request: expected a JSON-RPC object"));
		const FObj O = Msg->AsObject();
		FString Method;
		const bool bMethod = O->TryGetStringField(TEXT("method"), Method);
		const FVal* IdPtr = O->Values.Find(TEXT("id"));
		const bool bHasId = IdPtr && IdPtr->IsValid() && ((*IdPtr)->Type == EJson::String || (*IdPtr)->Type == EJson::Number);
		const FVal Id = bHasId ? *IdPtr : FVal();
		if (!bMethod)
		{
			if (O->HasField(TEXT("result")) || O->HasField(TEXT("error"))) return nullptr;
			return RpcError(Id, -32600, TEXT("Invalid Request: no method"));
		}
		FObj Params = NewObj();
		const TSharedPtr<FJsonObject>* ParamsPtr = nullptr;
		if (O->TryGetObjectField(TEXT("params"), ParamsPtr) && ParamsPtr && ParamsPtr->IsValid()) Params = *ParamsPtr;

		if (!bHasId)
		{
			UE_LOG(LogSkyMcp, Verbose, TEXT("Course MCP: notification %s"), *Method);
			return nullptr;                                      // notifications/initialized, notifications/cancelled, ...
		}
		if (Method == TEXT("initialize"))
		{
			if (bInBatch) return RpcError(Id, -32600, TEXT("initialize must not be part of a batch"));
			return DoInitialize(Id, Params, OutSession);
		}
		if (Method == TEXT("ping")) return RpcResult(Id, NewObj());
		if (Method == TEXT("tools/list")) return RpcResult(Id, ToolsList());
		if (Method == TEXT("tools/call")) { LastClientT = FPlatformTime::Seconds(); return DoToolCall(Id, Params); }
		return RpcError(Id, -32601, FString::Printf(TEXT("Method not found: %s"), *Method.Left(80)));
	}

	FObj DoInitialize(const FVal& Id, const FObj& Params, FString& OutSession)
	{
		FString Requested;
		Params->TryGetStringField(TEXT("protocolVersion"), Requested);
		FString Negotiated = LatestProtocol;
		for (const TCHAR* P : Protocols) if (Requested == P) Negotiated = Requested;
		FString Client;
		const TSharedPtr<FJsonObject>* Info = nullptr;
		if (Params->TryGetObjectField(TEXT("clientInfo"), Info) && Info)
		{
			FString N, V;
			(*Info)->TryGetStringField(TEXT("name"), N);
			(*Info)->TryGetStringField(TEXT("version"), V);
			Client = (N + TEXT(" ") + V).Left(80);
			LastClient = N.Left(40);
		}
		LastClientT = FPlatformTime::Seconds();
		OutSession = FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphensLower);
		if (Sessions.Num() >= MaxSessions)
		{
			FString Oldest;
			double OldestT = TNumericLimits<double>::Max();
			for (const TPair<FString, double>& S : Sessions) if (S.Value < OldestT) { OldestT = S.Value; Oldest = S.Key; }
			Sessions.Remove(Oldest);
		}
		Sessions.Add(OutSession, FPlatformTime::Seconds());
		UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: initialize from %s (asked for %s, using %s)"), *Client, *Requested, *Negotiated);

		FObj Result = NewObj();
		Result->SetStringField(TEXT("protocolVersion"), Negotiated);
		FObj Tools = NewObj();
		Tools->SetBoolField(TEXT("listChanged"), false);
		FObj Caps = NewObj();
		Caps->SetField(TEXT("tools"), JObj(Tools));
		Result->SetField(TEXT("capabilities"), JObj(Caps));
		FObj Server = NewObj();
		Server->SetStringField(TEXT("name"), ServerName);
		Server->SetStringField(TEXT("title"), TEXT("Sky City Course Builder"));
		Server->SetStringField(TEXT("version"), GameVersion());
		Result->SetField(TEXT("serverInfo"), JObj(Server));
		Result->SetStringField(TEXT("instructions"), A2S(InstructionsText));
		return RpcResult(Id, Result);
	}

	FObj ToolsList()
	{
		if (!ToolsListCache.IsValid())
		{
			FValArr Arr;
			for (const FToolDef& T : GTools)
			{
				FObj O = NewObj();
				O->SetStringField(TEXT("name"), A2S(T.Name));
				O->SetStringField(TEXT("title"), A2S(T.Title));
				O->SetStringField(TEXT("description"), A2S(T.Description));
				FVal Schema;
				if (!ParseJson(A2S(T.Schema), Schema))
				{
					UE_LOG(LogSkyMcp, Error, TEXT("Course MCP: the input schema of %s is not valid JSON"), *A2S(T.Name));
					FObj Empty = NewObj();
					Empty->SetStringField(TEXT("type"), TEXT("object"));
					Schema = JObj(Empty);
				}
				O->SetField(TEXT("inputSchema"), Schema);
				FObj Ann = NewObj();
				Ann->SetStringField(TEXT("title"), A2S(T.Title));
				Ann->SetBoolField(TEXT("readOnlyHint"), T.bReadOnly);
				Ann->SetBoolField(TEXT("destructiveHint"), T.bDestructive);
				Ann->SetBoolField(TEXT("idempotentHint"), T.bIdempotent);
				Ann->SetBoolField(TEXT("openWorldHint"), false);
				O->SetField(TEXT("annotations"), JObj(Ann));
				Arr.Add(JObj(O));
			}
			ToolsListCache = NewObj();
			ToolsListCache->SetArrayField(TEXT("tools"), Arr);
		}
		return ToolsListCache;
	}

	FObj DoToolCall(const FVal& Id, const FObj& Params)
	{
		FString Name;
		if (!Params->TryGetStringField(TEXT("name"), Name)) return RpcError(Id, -32602, TEXT("tools/call needs a tool name"));
		const FToolDef* Def = FindTool(Name);
		if (!Def) return RpcError(Id, -32602, FString::Printf(TEXT("Unknown tool: %s"), *Name.Left(60)));
		FObj Args = NewObj();
		const FVal* ArgsPtr = Params->Values.Find(TEXT("arguments"));
		if (ArgsPtr && ArgsPtr->IsValid() && (*ArgsPtr)->Type == EJson::Object) Args = (*ArgsPtr)->AsObject();

		const double T0 = FPlatformTime::Seconds();
		FToolResult R;
		ASkyCourseMode* M = Director.Get();
		if (!M && Def->bNeedsMode) R = Fail(TEXT("The Course Builder isn't running in this game session. Open the Course Builder from the Garage (Menu), then try again."));
		else R = Def->Fn(M, Args);
		const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
		UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: %s -> %s (%.0f ms)"), *Name, R.bError ? TEXT("error") : TEXT("ok"), Ms);

		FObj Block = NewObj();
		Block->SetStringField(TEXT("type"), TEXT("text"));
		Block->SetStringField(TEXT("text"), R.Text);
		FValArr Content;
		Content.Add(JObj(Block));
		FObj Result = NewObj();
		Result->SetField(TEXT("content"), JArr(MoveTemp(Content)));
		Result->SetBoolField(TEXT("isError"), R.bError);
		return RpcResult(Id, Result);
	}
};

// ======================================================================================================================
// FSkyCourseMcp
// ======================================================================================================================
FSkyCourseMcp::FSkyCourseMcp(ASkyCourseMode* InMode) : Mode(InMode) {}
FSkyCourseMcp::~FSkyCourseMcp() { Stop(); }

bool FSkyCourseMcp::Start(int32 Port)
{
	if (IsRunning()) return true;
	TSharedPtr<FState> S = MakeShared<FState>();
	S->Port = Port;
	S->Director = Mode;
	S->bHadMode = Mode.IsValid();
	FString Err;
	if (!S->Open(Err))
	{
		UE_LOG(LogSkyMcp, Warning, TEXT("Course MCP: not started: %s"), *Err);
		return false;
	}
	State = S;
	TWeakPtr<FState> Weak = S;
	S->TickHandle = FTSTicker::GetCoreTicker().AddTicker(TEXT("SkyCourseMcp"), 0.0f, [Weak](float Dt)
	{
		const TSharedPtr<FState> Pinned = Weak.Pin();
		return Pinned.IsValid() && Pinned->Tick(Dt);
	});
	UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: listening on http://127.0.0.1:%d/mcp (loopback only)"), Port);
	return true;
}

void FSkyCourseMcp::Stop()
{
	if (!State.IsValid()) return;
	const int32 Port = State->Port;
	const bool bWasOpen = State->ListenFd >= 0;
	State->Shutdown();
	State.Reset();
	if (bWasOpen) UE_LOG(LogSkyMcp, Log, TEXT("Course MCP: stopped, port %d closed"), Port);
}

bool FSkyCourseMcp::IsRunning() const { return State.IsValid() && State->ListenFd >= 0; }
FString FSkyCourseMcp::ClientName() const { return State.IsValid() ? State->LastClient : FString(); }
double FSkyCourseMcp::SecondsSinceClient() const { return State.IsValid() && State->LastClientT > 0 ? FPlatformTime::Seconds() - State->LastClientT : 1e9; }

FString FSkyCourseMcp::Url() const
{
	return FString::Printf(TEXT("http://127.0.0.1:%d/mcp"), State.IsValid() ? State->Port : SkyCourse::McpPort);
}

// ======================================================================================================================
// Console command for tests (not in shipping builds): SkyCourse.Mcp 1|0 [port]
// Finds or spawns the Course Builder director in the current world and runs the server on it, so the transport can be
// tested from editor Python with no menu. The real switch is ASkyCourseMode::SetMcpEnabled.
// ======================================================================================================================
#if !UE_BUILD_SHIPPING
static TSharedPtr<FSkyCourseMcp> GTestMcp;
static bool GTestMcpHooked = false;

static FAutoConsoleCommandWithWorldAndArgs GSkyCourseMcpCmd(TEXT("SkyCourse.Mcp"),
	TEXT("SkyCourse.Mcp 1|0 [port]: start or stop the course MCP server on the Course Builder in this world (spawning one if the world has none). For tests."),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
	{
		if (!GTestMcpHooked)
		{
			GTestMcpHooked = true;
			FCoreDelegates::OnEnginePreExit.AddLambda([]() { GTestMcp.Reset(); });
		}
		const bool bOn = Args.Num() == 0 || Args[0] != TEXT("0");
		if (!bOn)
		{
			GTestMcp.Reset();
			UE_LOG(LogSkyMcp, Log, TEXT("SkyCourse.Mcp 0: stopped"));
			return;
		}
		ASkyCourseMode* Mode = World ? ASkyCourseMode::Get(World) : nullptr;
		if (!Mode && World)
		{
			FActorSpawnParameters P;
			P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			Mode = World->SpawnActor<ASkyCourseMode>(FVector::ZeroVector, FRotator::ZeroRotator, P);
		}
		const int32 Port = Args.Num() > 1 ? FCString::Atoi(*Args[1]) : SkyCourse::McpPort;
		GTestMcp = MakeShared<FSkyCourseMcp>(Mode);
		if (!GTestMcp->Start(Port)) GTestMcp.Reset();
		UE_LOG(LogSkyMcp, Log, TEXT("SkyCourse.Mcp 1: %s"), GTestMcp.IsValid() ? *GTestMcp->Url() : TEXT("did not start"));
	}));
#endif
