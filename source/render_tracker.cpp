#include "maxon/system_process.h"
#include "render_tracker.h"
#include "c4d_symbols.h"
#include "lib_takesystem.h"
#include "lib_token.h"
#include <iostream>
#include <time.h>
#include <vector>
#include <winsock2.h>
#pragma comment(lib, "ws2_32.lib")

namespace cinema {

Bool RegisterRenderTracker()
{
    return RegisterVideoPostPlugin(ID_RENDER_TRACKER, "RenderTracker (Cinema4D)"_s, 0, RenderNotifierVideoPost::Alloc, "vprendertracker"_s, 0, 0);
}

Bool RenderNotifierVideoPost::Init(GeListNode* node, Bool isCloneInit)
{
    _isFinished   = false;
    _totalFrameDuration = 0.0;
    _completedFramesCount = 0;

    // Winsock initialize
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return false;

    return true;
}

void RenderNotifierVideoPost::Free(GeListNode* node)
{
    if (_renderStartTs > 0.0 && !_isFinished)
    {
        SendRenderStatus(_lastFrameTime - _frameStartTime, _frameStartTime, _lastFrameImagePath, (Float64)time(NULL), _frameNumber, "STOP");
        _isFinished = true;
    }
    WSACleanup();
}

Bool RenderNotifierVideoPost::GetDDescription(const GeListNode* node, Description* description, DESCFLAGS_DESC& flags) const
{
    if (!description->LoadDescription("vprendernotifier"_s)) return false;
    flags |= DESCFLAGS_DESC::LOADED;
    return SUPER::GetDDescription(node, description, flags);
}

static std::string ToStdString(const String& str)
{
    if (!str.IsPopulated()) return "";
    char* cstr = str.GetCStringCopy(STRINGENCODING::UTF8);
    if (!cstr) return "";
    std::string res(cstr);
    DeleteMem(cstr);
    return res;
}

static String EscapeJson(const String& str)
{
    std::string s = ToStdString(str);
    if (s.empty()) return str;
    std::string res;
    for (char c : s) {
        if      (c == '\\') res += "\\\\";
        else if (c == '"')  res += "\\\"";
        else if (c == '\n') res += "\\n";
        else res += c;
    }
    return String(res.c_str(), STRINGENCODING::UTF8);
}

void RenderNotifierVideoPost::SendRenderStatus(
    Float64 lastFrameDuration,
    Float64 currentFrameStartTs,
    const String& lastRenderedImagePath,
    Float64 endTs,
    Int32 frameNumber,
    const std::string& event)
{
    char jsonBuf[2048];
    snprintf(jsonBuf, sizeof(jsonBuf),
        "{\n"
        "  \"event\": \"%s\",\n"
        "  \"start\": {\n"
        "    \"start_ts\": %.2f,\n"
        "    \"dcc_pid\": %lu,\n"
        "    \"doc_name\": \"%s\",\n"
        "    \"take_name\": null,\n"
        "    \"render_setting\": null,\n"
        "    \"res_x\": %d,\n"
        "    \"res_y\": %d,\n"
        "    \"start_frame\": %d,\n"
        "    \"end_frame\": %d,\n"
        "    \"total_frames\": %d,\n"
        "    \"output_path\": \"%s\",\n"
        "    \"software\": \"%s\",\n"
        "    \"renderer\": \"%s\",\n"
        "    \"first_frame_path\": \"%s\",\n"
        "    \"last_frame_path\": \"%s\"\n"
        "  },\n"
        "  \"update\": {\n"
        "    \"rendered_frames\": %d,\n"
        "    \"current_frame\": %d,\n"
        "    \"last_frame_duration\": %.2f,\n"
        "    \"current_frame_start_ts\": %.2f,\n"
        "    \"last_rendered_image_path\": \"%s\"\n"
        "  },\n"
        "  \"end\": {\n"
        "    \"end_ts\": %.2f\n"
        "  }\n"
        "}",
        event.c_str(),
        _renderStartTs, 
        (unsigned long)maxon::SystemProcessInterface::GetCurrentProcessId(),
        ToStdString(_docName).c_str(),
        _resX, _resY,
        _startFrame, _endFrame, _totalFrames,
        ToStdString(_outputPath).c_str(),
        ToStdString(_softwareName).c_str(),
        ToStdString(_rendererName).c_str(),
        ToStdString(EscapeJson(_firstFrameImagePath)).c_str(),
        ToStdString(EscapeJson(_lastFrameImagePath)).c_str(),
        _completedFramesCount,
        frameNumber,
        lastFrameDuration,
        currentFrameStartTs,
        ToStdString(EscapeJson(lastRenderedImagePath)).c_str(),
        endTs
    );
    SendStatusSocket(std::string(jsonBuf));
}

void RenderNotifierVideoPost::SendStatusSocket(const std::string& message)
{
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return;

    sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(50000); 
    serverAddr.sin_addr.s_addr = inet_addr("127.0.0.1");

    DWORD timeout = 200; 
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (char*)&timeout, sizeof(timeout));
    if (connect(sock, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) != SOCKET_ERROR)
    {
        send(sock, message.c_str(), (int)message.length(), 0);
    }
    closesocket(sock);
}

String RenderNotifierVideoPost::CalculateOutputPath(VideoPostStruct* vps)
{
    if (!vps || !vps->doc || !vps->render) return ""_s;
    RenderData* rd = vps->doc->GetActiveRenderData();
    if (!rd) return ""_s;
    BaseContainer* dataPtr = rd->GetDataInstance();
    if (!dataPtr || !dataPtr->GetBool(RDATA_SAVEIMAGE)) return ""_s;
    
    Filename fn = dataPtr->GetFilename(RDATA_PATH);
    String srcPath = fn.GetString();
    if (!srcPath.IsPopulated()) return ""_s;

    BaseTake* currentTake = (vps->doc->GetTakeData()) ? vps->doc->GetTakeData()->GetCurrentTake() : nullptr;
    RenderPathData rpData(vps->doc, rd, dataPtr, currentTake, (Int32)_frameNumber);
    Filename resolvedFile = FilenameConvertTokens(Filename(srcPath), &rpData);
    
    if (!srcPath.FindFirst("$frame"_s, nullptr) && !srcPath.FindFirst("$f"_s, nullptr))
    {
        if (dataPtr->GetInt32(RDATA_FRAMESEQUENCE) != RDATA_FRAMESEQUENCE_CURRENTFRAME)
        {
            Int32 nameFormat = dataPtr->GetInt32(RDATA_NAMEFORMAT);
            String suffix = ""_s; char buf[32];
            switch (nameFormat)
            {
                case 0: snprintf(buf, sizeof(buf), "%04d", (int)_frameNumber); suffix = String(buf); break;
                case 1: snprintf(buf, sizeof(buf), "_%04d", (int)_frameNumber); suffix = String(buf); break;
                case 2: snprintf(buf, sizeof(buf), ".%04d", (int)_frameNumber); suffix = String(buf); break;
                case 3: snprintf(buf, sizeof(buf), "%03d", (int)_frameNumber); suffix = String(buf); break;
                case 4: snprintf(buf, sizeof(buf), "_%03d", (int)_frameNumber); suffix = String(buf); break;
                case 5: snprintf(buf, sizeof(buf), ".%03d", (int)_frameNumber); suffix = String(buf); break;
            }
            if (suffix.IsPopulated()) {
                String fileStr = resolvedFile.GetFileString();
                resolvedFile.SetFile(Filename(fileStr + suffix));
            }
        }
    }
    if (resolvedFile.GetSuffix() == ""_s) resolvedFile = GeFilterSetSuffix(resolvedFile, dataPtr->GetInt32(RDATA_FORMAT));
    return resolvedFile.GetString();
}

RENDERRESULT RenderNotifierVideoPost::Execute(BaseVideoPost* node, VideoPostStruct* vps)
{
    if (!vps || !node) return RENDERRESULT::OK;

    if (vps->vp == VIDEOPOSTCALL::FRAMESEQUENCE)
    {
        if (vps->open)  // START
        {
            _firstFrameImagePath  = ""_s;
            _lastFrameImagePath   = ""_s;
            _renderStartTime      = GeGetTimer() / 1000.0;
            _renderStartTs        = (Float64)time(NULL); 
            _lastFrameTime        = _renderStartTime;
            _totalFrameDuration   = 0.0;
            _completedFramesCount = 0;
            _frameStartTime       = _renderStartTime;
            _frameNumber          = 0;
            _isFinished           = false;

            if (vps->doc) _docName = vps->doc->GetDocumentName().GetString();
            if (vps->render)
            {
                BaseContainer renderData = vps->render->GetRenderData();
                _resX = renderData.GetInt32(RDATA_XRES);
                _resY = renderData.GetInt32(RDATA_YRES);

                Int32 frameFrom = renderData.GetTime(RDATA_FRAMEFROM).GetFrame(vps->fps);
                Int32 frameTo   = renderData.GetTime(RDATA_FRAMETO).GetFrame(vps->fps);
                Int32 frameStep = renderData.GetInt32(RDATA_FRAMESTEP);
                if (frameStep <= 0) frameStep = 1;

                _startFrame = frameFrom;
                _endFrame   = frameTo;
                _totalFrames = (frameTo >= frameFrom) ? ((frameTo - frameFrom) / frameStep) + 1 : 1;
                _outputPath = EscapeJson(renderData.GetFilename(RDATA_PATH).GetDirectory().GetString());
                _softwareName = "Cinema 4D"_s;

                Int32 engineId = renderData.GetInt32(RDATA_RENDERENGINE);
                switch (engineId)
                {
                    case RDATA_RENDERENGINE_STANDARD: _rendererName = "Standard"_s; break;
                    case RDATA_RENDERENGINE_PHYSICAL: _rendererName = "Physical"_s; break;
                    case RDATA_RENDERENGINE_REDSHIFT: _rendererName = "Redshift"_s; break;
                    case 1029525:                     _rendererName = "Octane"_s; break;
                    default:                          _rendererName = "Standard"_s; break;
                }
            }
            SendRenderStatus(0.0, _frameStartTime, ""_s, -1.0, _startFrame, "START");
        }
        else  // FINISH
        {
            SendRenderStatus(_lastFrameTime - _frameStartTime, _frameStartTime, _lastFrameImagePath, (Float64)time(NULL), _frameNumber, "FINISH");
            _isFinished = true;
        }
    }
    else if (vps->vp == VIDEOPOSTCALL::RENDER)
    {
        if (vps->open) // FRAME PRE
        {
            Float64 now = GeGetTimer() / 1000.0;
            Float64 lastInterval = (_completedFramesCount > 0) ? now - _lastFrameTime : 0.0;
            _lastFrameTime = now;
            _frameStartTime = now;
            _frameNumber = vps->time.GetFrame(vps->fps);
            SendRenderStatus(lastInterval, _frameStartTime, _lastFrameImagePath, -1.0, _frameNumber, "PROGRESS");
        }
        else // FRAME POST
        {
            _lastFrameImagePath = CalculateOutputPath(vps);
            if (_completedFramesCount == 0) _firstFrameImagePath = _lastFrameImagePath;

            Float64 now = GeGetTimer() / 1000.0;
            Float64 duration = now - _frameStartTime;
            _totalFrameDuration += duration;
            _completedFramesCount++;
            SendRenderStatus(duration, _frameStartTime, _lastFrameImagePath, -1.0, _frameNumber, "PROGRESS");
        }
    }
    return RENDERRESULT::OK;
}

} // namespace cinema
