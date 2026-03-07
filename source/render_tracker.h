#pragma once

#include "c4d.h"
#include <string>

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

    virtual ~RenderNotifierVideoPost() { }

private:
    String CalculateOutputPath(VideoPostStruct* vps);

    // Sends render status to Python monitor via socket.
    void SendRenderStatus(Float64 lastFrameDuration,
                          Float64 currentFrameStartTs,
                          const String& lastRenderedImagePath,
                          Float64 endTs,
                          Int32 frameNumber,
                          const std::string& event = "PROGRESS");

    void SendStatusSocket(const std::string& message);

    // Render progress tracking
    Bool    _isFinished = false;
    Int32   _frameNumber  = 0;
    Int32   _totalFrames  = 1;
    Float64 _renderStartTime    = 0.0;
    Float64 _renderStartTs      = 0.0;
    Float64 _lastFrameTime      = 0.0;
    Float64 _frameStartTime     = 0.0;
    Float64 _totalFrameDuration = 0.0;
    Int32   _completedFramesCount = 0;

    // Rendering metadata (Minimal required)
    String _docName;
    String _softwareName;
    String _rendererName;
    Int32  _resX = 0;
    Int32  _resY = 0;
    Int32  _startFrame = 0;
    Int32  _endFrame   = 0;
    String _outputPath;
    String _lastFrameImagePath;
    String _firstFrameImagePath;
};

} // namespace cinema
