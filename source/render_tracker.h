#pragma once

#include "c4d.h"
#include <string>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>

#define ID_RENDER_TRACKER 1067644 

namespace cinema {

class RenderNotifierVideoPost : public VideoPostData
{
    INSTANCEOF(RenderNotifierVideoPost, VideoPostData)

public:
    virtual Bool Init(GeListNode* node, Bool isCloneInit) override;
    virtual RENDERRESULT Execute(BaseVideoPost* node, VideoPostStruct* vps) override;
    virtual Bool GetDDescription(const GeListNode* node, Description* description, DESCFLAGS_DESC& flags) const override;
    virtual void Free(GeListNode* node) override;
    virtual VIDEOPOSTINFO GetRenderInfo(BaseVideoPost* node) override { return VIDEOPOSTINFO::NONE; }
    static NodeData* Alloc() { return NewObjClear(RenderNotifierVideoPost); }

    virtual ~RenderNotifierVideoPost() { StopTimerThread(); }

private:
    String ExtractJsonString(const String& jsonStr, const String& key);
    bool ExtractJsonBool(const String& jsonStr, const String& key);
    String ReplaceString(String str, const String& from, const String& to);
    void SaveLastFrameThumbnail(BaseBitmap* sourceBmp);
    String CalculateOutputPath(VideoPostStruct* vps);

    // Records render data in status.json with 3 sections (init/update/end).
    void WriteStatusJson(Float64 elapsedSeconds,
                         Float64 remainingSeconds,
                         Float64 avgFrameDuration,
                         Float64 lastFrameDuration,
                         Float64 currentFrameDuration,
                         Float64 endTs,
                         Int32 frameNumber);

    void TimerLoop();
    void StopTimerThread();

    // Render progress tracking
    std::atomic<bool> _isFinished{ false };
    std::atomic<bool> _stopThread{ false };
    std::thread       _timerThread;
    mutable std::mutex _statusMutex;

    Int32   _currentFrame = 0; // Number of frames rendered count
    Int32   _frameNumber  = 0; // Actual timeline frame number
    Int32   _totalFrames  = 1;
    Float64 _renderStartTime    = 0.0; // Based on GeGetTimer (internal elapsed calculation)
    Float64 _renderStartTs      = 0.0; // Unix timestamp (for Python detecting new render)
    Float64 _lastFrameTime      = 0.0;
    Float64 _frameStartTime     = 0.0;
    Float64 _totalFrameDuration = 0.0;
    Int32   _completedFramesCount = 0;
    String  _currentFrameTime;

    // Rendering metadata
    String _docName;
    String _takeName;
    String _renderSettingName;
    String _softwareName;
    String _rendererName;
    Int32  _resX = 1920;
    Int32  _resY = 1080;
    Int32  _startFrame = 0;
    Int32  _endFrame   = 0;
    String _outputPath;
    String _statusFileName;  // Unique JSON filename per render (Render_YYYYMMDD_HHMMSS.json)
    String _lastFrameImagePath;
    String _firstFrameImagePath;
    Float  _lastThumbTime = 0.0;
    Int32  _lastThumbFrame = -1;
};

} // namespace cinema
