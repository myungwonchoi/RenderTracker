#include "maxon/system_process.h"
#include "render_tracker.h"
#include "c4d_symbols.h"
#include "lib_takesystem.h"
#include "lib_token.h"
#include <iostream>
#include <time.h>
#include <vector>
#include <cstdlib>

namespace cinema {

Bool RegisterRenderTracker()
{
    return RegisterVideoPostPlugin(ID_RENDER_TRACKER, "RenderTracker (Cinema4D)"_s, 0, RenderNotifierVideoPost::Alloc, "vprendertracker"_s, 0, 0);
}

Bool RenderNotifierVideoPost::Init(GeListNode* node, Bool isCloneInit)
{
    _currentFrame = 0;
    _totalFrames  = 1;
    _isFinished   = false;
    _stopThread   = false;
    _currentFrameTime = ""_s;
    return true;
}

void RenderNotifierVideoPost::Free(GeListNode* node)
{
    StopTimerThread();

    // 만약 렌더링이 시작되었는데(start_ts > 0) 정상적으로 종료 기록이 써지지 않았다면( !isFinished )
    if (_renderStartTs > 0.0 && !_isFinished)
    {
        Float64 now = GeGetTimer() / 1000.0;
        Float64 elapsedSeconds = now - _renderStartTime;
        Float64 avgDuration = (_completedFramesCount > 0) ? _totalFrameDuration / _completedFramesCount : 0.0;

        WriteStatusJson(elapsedSeconds, -1.0, avgDuration, 0.0, 0.0, (Float64)time(NULL), _frameNumber);
        _isFinished = true;
    }
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

String RenderNotifierVideoPost::ExtractJsonString(const String& jsonStr, const String& key)
{
    std::string sJson = ToStdString(jsonStr);
    std::string sKey  = "\"" + ToStdString(key) + "\"";

    size_t pos = 0;
    while ((pos = sJson.find(sKey, pos)) != std::string::npos)
    {
        int braceDepth = 0, bracketDepth = 0;
        bool inString = false;
        for (size_t i = 0; i < pos; ++i) {
            if (sJson[i] == '"' && (i == 0 || sJson[i-1] != '\\')) inString = !inString;
            if (!inString) {
                if      (sJson[i] == '{') braceDepth++;
                else if (sJson[i] == '}') braceDepth--;
                else if (sJson[i] == '[') bracketDepth++;
                else if (sJson[i] == ']') bracketDepth--;
            }
        }

        if (braceDepth == 1 && bracketDepth == 0)
        {
            pos += sKey.length();
            std::string restStr  = sJson.substr(pos);
            size_t colonPos = restStr.find(":");
            if (colonPos != std::string::npos)
            {
                std::string afterColon = restStr.substr(colonPos + 1);
                size_t startQuote = afterColon.find("\"");
                if (startQuote != std::string::npos)
                {
                    std::string afterStartQuote = afterColon.substr(startQuote + 1);
                    size_t endQuote = 0;
                    bool escaped = false;
                    while (endQuote < afterStartQuote.length()) {
                        if      (afterStartQuote[endQuote] == '\\') escaped = !escaped;
                        else if (afterStartQuote[endQuote] == '"' && !escaped) break;
                        else escaped = false;
                        endQuote++;
                    }
                    if (endQuote < afterStartQuote.length())
                        return String(afterStartQuote.substr(0, endQuote).c_str(), STRINGENCODING::UTF8);
                }
            }
        }
        else { pos += sKey.length(); }
    }
    return String();
}

bool RenderNotifierVideoPost::ExtractJsonBool(const String& jsonStr, const String& key)
{
    std::string sJson = ToStdString(jsonStr);
    std::string sKey  = "\"" + ToStdString(key) + "\"";
    size_t pos = sJson.find(sKey);
    if (pos != std::string::npos) {
        pos += sKey.length();
        std::string after = sJson.substr(sJson.find(":", pos) + 1);
        if (after.find("true") != std::string::npos) return true;
    }
    return false;
}

String RenderNotifierVideoPost::ReplaceString(String str, const String& from, const String& to)
{
    std::string s = ToStdString(str), sf = ToStdString(from), st = ToStdString(to);
    if (sf.empty()) return str;
    size_t p = 0;
    while ((p = s.find(sf, p)) != std::string::npos) { s.replace(p, sf.length(), st); p += st.length(); }
    return String(s.c_str(), STRINGENCODING::UTF8);
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
    return String(res.c_str());
}

static std::string FmtTimestamp(Float64 ts)
{
    if (ts <= 0) return "";
    time_t t = (time_t)ts;
    struct tm* ti = localtime(&t);
    char buf[64];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", ti);
    return std::string(buf);
}

static String FormatDuration(Float64 seconds)
{
    if (seconds < 0) seconds = 0;
    Int32 s = (Int32)seconds;
    Int32 m = s / 60;
    Int32 h = m / 60;
    s %= 60;
    m %= 60;

    char buf[32];
    snprintf(buf, sizeof(buf), "%02d:%02d:%02d", h, m, s);
    return String(buf);
}

// -----------------------------------------------------------------------------
// Records status.json in three sections: init, update, and end.
//   init   : Metadata decided once at the start of rendering.
//   update : Progress data updated every frame.
//   end    : Rendering end time (-1 while in progress).
// Python app detects new rendering via change in init.start_ts.
// -----------------------------------------------------------------------------
void RenderNotifierVideoPost::WriteStatusJson(
    Float64 elapsedSeconds,
    Float64 remainingSeconds,
    Float64 avgFrameDuration,
    Float64 lastFrameDuration,
    Float64 currentFrameDuration,
    Float64 endTs,
    Int32 frameNumber)
{
    std::lock_guard<std::mutex> lock(_statusMutex);

    std::string startTimeStr = FmtTimestamp(_renderStartTs);
    std::string endTimeStr   = FmtTimestamp(endTs);

    char jsonBuf[8192];
    snprintf(jsonBuf, sizeof(jsonBuf),
        "{\n"
        "  \"start\": {\n"
        "    \"start_ts\": %.2f,\n"
        "    \"start_time\": \"%s\",\n"
        "    \"c4d_pid\": %lu,\n"
        "    \"doc_name\": \"%s\",\n"
        "    \"take_name\": \"%s\",\n"
        "    \"render_setting\": \"%s\",\n"
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
        "    \"elapsed_seconds\": %.2f,\n"
        "    \"remaining_seconds\": %.2f,\n"
        "    \"avg_frame_duration\": %.2f,\n"
        "    \"last_frame_duration\": %.2f,\n"
        "    \"current_frame_duration\": %.2f,\n"
        "    \"field_current_frame_time\": \"%s\"\n"
        "  },\n"
        "  \"end\": {\n"
        "    \"end_ts\": %.2f,\n"
        "    \"end_time\": \"%s\"\n"
        "  }\n"
        "}",
        _renderStartTs, startTimeStr.c_str(),
        (unsigned long)maxon::SystemProcessInterface::GetCurrentProcessId(),
        ToStdString(_docName).c_str(),
        ToStdString(_takeName).c_str(),
        ToStdString(_renderSettingName).c_str(),
        _resX, _resY,
        _startFrame, _endFrame, _totalFrames,
        ToStdString(_outputPath).c_str(),
        ToStdString(_softwareName).c_str(),
        ToStdString(_rendererName).c_str(),
        ToStdString(EscapeJson(_firstFrameImagePath)).c_str(),
        ToStdString(EscapeJson(_lastFrameImagePath)).c_str(),
        // update
        _currentFrame,
        frameNumber,
        elapsedSeconds, remainingSeconds,
        avgFrameDuration, lastFrameDuration, currentFrameDuration,
        ToStdString(_currentFrameTime).c_str(),
        // end
        endTs, endTimeStr.c_str()
    );

    // Ensure the history directory exists in %APPDATA%\RenderTracker\history
    Filename historyDir;
    const char* appDataEnv = std::getenv("APPDATA");
    if (appDataEnv)
    {
        Filename baseDir = Filename(String(appDataEnv)) + "RenderTracker"_s;
        if (!GeFExist(baseDir)) GeFCreateDir(baseDir);
        
        historyDir = baseDir + "history"_s;
        if (!GeFExist(historyDir)) GeFCreateDir(historyDir);
    }
    else
    {
        // Fallback to plugin directory if APPDATA is not found
        historyDir = GeGetPluginPath() + "history"_s;
        if (!GeFExist(historyDir)) GeFCreateDir(historyDir);
    }

    Filename historyPath = historyDir + Filename(_statusFileName);
    AutoAlloc<BaseFile> file;
    if (file && file->Open(historyPath, FILEOPEN::WRITE, FILEDIALOG::NONE, BYTEORDER::V_INTEL, MACTYPE_CINEMA, MACCREATOR_CINEMA))
    {
        std::string utf8(jsonBuf);
        file->WriteBytes((void*)utf8.c_str(), (Int)utf8.length());
        file->Close();
    }
}

// -----------------------------------------------------------------------------
// Calculates the actual output path of the current frame (including tokens and sequence numbers).
// -----------------------------------------------------------------------------
String RenderNotifierVideoPost::CalculateOutputPath(VideoPostStruct* vps)
{
    if (!vps || !vps->doc || !vps->render) return ""_s;
    
    RenderData* rd = vps->doc->GetActiveRenderData();
    if (!rd) return ""_s;

    BaseContainer* dataPtr = rd->GetDataInstance();
    if (!dataPtr) return ""_s;
    const BaseContainer& data = *dataPtr;
    
    // Check if saving is enabled
    if (!data.GetBool(RDATA_SAVEIMAGE)) return ""_s;

    Filename fn = data.GetFilename(RDATA_PATH);
    String srcPath = fn.GetString();
    if (!srcPath.IsPopulated()) return ""_s;

    // 1. Resolve tokens first ($prj, $take, etc.)
    BaseTake* currentTake = nullptr;
    if (vps->doc->GetTakeData()) currentTake = vps->doc->GetTakeData()->GetCurrentTake();

    // Use FilenameConvertTokens for better path handling
    RenderPathData rpData(vps->doc, rd, &data, currentTake, (Int32)_frameNumber);
    Filename resolvedFile = FilenameConvertTokens(Filename(srcPath), &rpData);
    
    // 2. Handle frame number suffix if no frame-related tokens were used in the path
    // Cinema 4D automatically appends a suffix if no naming tokens are present.
    if (!srcPath.FindFirst("$frame"_s, nullptr) && !srcPath.FindFirst("$f"_s, nullptr))
    {
        Int32 seq = data.GetInt32(RDATA_FRAMESEQUENCE);
        if (seq != RDATA_FRAMESEQUENCE_CURRENTFRAME)
        {
            Int32 nameFormat = data.GetInt32(RDATA_NAMEFORMAT);
            String suffix = ""_s;
            char buf[32];
            
            // Format suffix according to RDATA_NAMEFORMAT
            switch (nameFormat)
            {
                case 0: snprintf(buf, sizeof(buf), "%04d", (int)_frameNumber); suffix = String(buf); break;
                case 1: snprintf(buf, sizeof(buf), "_%04d", (int)_frameNumber); suffix = String(buf); break;
                case 2: snprintf(buf, sizeof(buf), ".%04d", (int)_frameNumber); suffix = String(buf); break;
                case 3: snprintf(buf, sizeof(buf), "%03d", (int)_frameNumber); suffix = String(buf); break;
                case 4: snprintf(buf, sizeof(buf), "_%03d", (int)_frameNumber); suffix = String(buf); break;
                case 5: snprintf(buf, sizeof(buf), ".%03d", (int)_frameNumber); suffix = String(buf); break;
                default: break;
            }
            
            if (suffix.IsPopulated())
            {
                String fileStr = resolvedFile.GetFileString();
                resolvedFile.SetFile(Filename(fileStr + suffix));
            }
        }
    }

    // 3. Append extension if missing (Cinema 4D adds it automatically)
    if (resolvedFile.GetSuffix() == ""_s)
    {
        Int32 filter = data.GetInt32(RDATA_FORMAT);
        resolvedFile = GeFilterSetSuffix(resolvedFile, filter);
    }

    return resolvedFile.GetString();
}

void RenderNotifierVideoPost::SaveLastFrameThumbnail(BaseBitmap* sourceBmp)
{
    // No longer saved directly in C++, only path information is updated (Zero-overhead).
}

// -----------------------------------------------------------------------------
// Execute: Core function called by C4D for each rendering event.
// -----------------------------------------------------------------------------
RENDERRESULT RenderNotifierVideoPost::Execute(BaseVideoPost* node, VideoPostStruct* vps)
{
    if (!vps || !node) return RENDERRESULT::OK;
    BaseContainer* data = node->GetDataInstance();
    if (!data) return RENDERRESULT::OK;

    // -- (1) Rendering Sequence Events ------------------------------------------
    if (vps->vp == VIDEOPOSTCALL::FRAMESEQUENCE)
    {
        if (vps->open)  // Rendering started
        {
            // Initialize progress variables
            _currentFrame         = 0;
            _firstFrameImagePath  = ""_s;
            _lastFrameImagePath   = ""_s;
            _totalFrames          = 1;
            _renderStartTime      = GeGetTimer() / 1000.0;
            _renderStartTs        = (Float64)time(NULL);  // Unix timestamp for Python new render detection
            _lastFrameTime        = _renderStartTime;
            _totalFrameDuration   = 0.0;
            _completedFramesCount = 0;
            _frameStartTime       = _renderStartTime;
            _frameNumber          = 0;
            _currentFrameTime     = ""_s;
            _isFinished           = false;
            _stopThread           = false;

            // Generate unique JSON filename for each render: Render_YYYYMMDD_HHMMSS.json
            {
                time_t now_t = (time_t)_renderStartTs;
                struct tm* ti = localtime(&now_t);
                char nameBuf[64];
                strftime(nameBuf, sizeof(nameBuf), "Render_%Y%m%d_%H%M%S.json", ti);
                _statusFileName = String(nameBuf);
            }

            // Document name and current take name
            if (vps->doc)
            {
                _docName = vps->doc->GetDocumentName().GetString();

                // Collect current active take name
                TakeData* takeData = vps->doc->GetTakeData();
                if (takeData)
                {
                    BaseTake* currentTake = takeData->GetCurrentTake();
                    if (currentTake)
                        _takeName = currentTake->GetName();
                    else
                        _takeName = "Main"_s;
                }
                else
                {
                    _takeName = "Main"_s;
                }
            }

            // Read resolution/frame range/output path from render settings
            if (vps->render)
            {
                BaseContainer renderData = vps->render->GetRenderData();
                _renderSettingName = "My Render Setting"_s;
                if (vps->doc) {
                    RenderData* rd = vps->doc->GetActiveRenderData();
                    if (rd) _renderSettingName = rd->GetName();
                }
                _resX = renderData.GetInt32(RDATA_XRES);
                _resY = renderData.GetInt32(RDATA_YRES);

                Int32 frameFrom = renderData.GetTime(RDATA_FRAMEFROM).GetFrame(vps->fps);
                Int32 frameTo   = renderData.GetTime(RDATA_FRAMETO).GetFrame(vps->fps);
                Int32 frameStep = renderData.GetInt32(RDATA_FRAMESTEP);
                if (frameStep <= 0) frameStep = 1;

                _startFrame = frameFrom;
                _endFrame   = frameTo;
                if (frameTo > frameFrom) _totalFrames = ((frameTo - frameFrom) / frameStep) + 1;

                _outputPath = EscapeJson(renderData.GetFilename(RDATA_PATH).GetString());
                
                // Extract only the directory path (remove filename)
                Filename fn = renderData.GetFilename(RDATA_PATH);
                _outputPath = EscapeJson(fn.GetDirectory().GetString());

                // Software and Renderer info
                _softwareName = "Cinema 4D"_s;

                Int32 engineId = renderData.GetInt32(RDATA_RENDERENGINE);
                switch (engineId)
                {
                    case RDATA_RENDERENGINE_STANDARD:        _rendererName = "Standard"_s; break;
                    case RDATA_RENDERENGINE_PHYSICAL:        _rendererName = "Physical"_s; break;
                    case RDATA_RENDERENGINE_REDSHIFT:        _rendererName = "Redshift"_s; break;
                    case 1029525:                            _rendererName = "Octane"_s; break;
                    case RDATA_RENDERENGINE_PREVIEWHARDWARE: _rendererName = "Viewport Renderer"_s; break;
                    default:                                 _rendererName = _renderSettingName; break;
                }
            }

            // -- [INIT] Record status.json: fixed info like start time, resolution, path --
            WriteStatusJson(0.0, -1.0, 0.0, 0.0, 0.0, -1.0, 0);

            // Start real-time update thread
            if (_timerThread.joinable()) StopTimerThread();
            _stopThread = false;
            _timerThread = std::thread(&RenderNotifierVideoPost::TimerLoop, this);
        }
        else  // Rendering finished (normal completion or user cancel)
        {
            StopTimerThread();

            Float64 now            = GeGetTimer() / 1000.0;
            Float64 elapsedSeconds = now - _renderStartTime;

            Float64 avgDuration = (_completedFramesCount > 0)
                ? _totalFrameDuration / _completedFramesCount : 0.0;

            // -- [END] Record status.json: include end time ----------------------
            WriteStatusJson(
                elapsedSeconds, -1.0, avgDuration, 
                0.0, 0.0, 
                (Float64)time(NULL),   // end_ts
                _frameNumber
            );
            _isFinished = true;
        }
    }
    // -- (2) Single Frame Render Event (called for each frame) ------------------
    else if (vps->vp == VIDEOPOSTCALL::RENDER)
    {
        if (vps->open)
        {
            Float64 now = GeGetTimer() / 1000.0;
            Float64 lastInterval = 0.0;

            if (_currentFrame > 0)
            {
                lastInterval = now - _lastFrameTime;
            }
            _lastFrameTime = now;
            _frameStartTime = now;
            _currentFrame++;
            _frameNumber = vps->time.GetFrame(vps->fps);
            _currentFrameTime = "00:00:00"_s;

            Float64 avgDuration = (_completedFramesCount > 0)
                ? _totalFrameDuration / _completedFramesCount : 0.0;

            Float64 elapsedSeconds   = now - _renderStartTime;
            Float64 remainingSeconds = (_totalFrames - _completedFramesCount) * avgDuration;

            // -- [UPDATE] Record status.json: frame progress -----------------
            WriteStatusJson(
                elapsedSeconds, remainingSeconds,
                avgDuration, lastInterval,
                0.0, // current_frame_duration (starting...)
                -1.0,  // end_ts: -1 while in progress
                _frameNumber
            );
        }
        else // Frame finished (vps->open == false)
        {
            // [Zero-overhead] Calculate actual output path and update
            _lastFrameImagePath = CalculateOutputPath(vps);

            if (_currentFrame == 1) _firstFrameImagePath = _lastFrameImagePath;

            Float64 now = GeGetTimer() / 1000.0;
            Float64 currentFrameActiveDuration = now - _frameStartTime;

            _totalFrameDuration += currentFrameActiveDuration;
            _completedFramesCount++;

            Float64 avgDuration = (_completedFramesCount > 0)
                ? _totalFrameDuration / _completedFramesCount : 0.0;

            Float64 elapsedSeconds   = now - _renderStartTime;
            Float64 remainingSeconds = (_totalFrames - _completedFramesCount) * avgDuration;

            _currentFrameTime = FormatDuration(currentFrameActiveDuration);

            WriteStatusJson(
                elapsedSeconds, remainingSeconds,
                avgDuration, 0.0,
                currentFrameActiveDuration,
                -1.0,
                _frameNumber
            );
        }
    }

    return RENDERRESULT::OK;
}

void RenderNotifierVideoPost::TimerLoop()
{
    while (!_stopThread)
    {
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        if (_stopThread) break;

        // Calculate and write current progress
        if (_renderStartTs > 0.0 && !_isFinished)
        {
            Float64 now = GeGetTimer() / 1000.0;
            Float64 elapsedSeconds = now - _renderStartTime;
            
            // Current frame elapsed
            Float64 currentFrameActiveDuration = now - _frameStartTime;
            
            // Average calculation including current partial frame
            Float64 avgDuration = (_totalFrameDuration + currentFrameActiveDuration) / (_completedFramesCount + 1);
            
            // Remaining calculation (Total frames * average) - Already elapsed
            Float64 remainingSeconds = (_totalFrames * avgDuration) - elapsedSeconds;
            if (remainingSeconds < 0.0) remainingSeconds = 0.0;

            _currentFrameTime = FormatDuration(currentFrameActiveDuration);

            WriteStatusJson(elapsedSeconds, remainingSeconds, avgDuration, 0.0, currentFrameActiveDuration, -1.0, _frameNumber);
        }
    }
}

void RenderNotifierVideoPost::StopTimerThread()
{
    _stopThread = true;
    if (_timerThread.joinable())
    {
        _timerThread.join();
    }
}

} // namespace cinema
