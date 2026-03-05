#include "c4d.h"
#include "render_tracker.h"
#include <string>

namespace cinema {

// Forward declaration of the plugin registration function.
Bool RegisterRenderTracker();
void CheckAndAddRenderNotifier(BaseDocument* doc);

// PluginStart() is called once when Cinema 4D is started.
// This is where we register our plugin with the C4D system.
Bool PluginStart()
{
    // Inform C4D that this VideoPost plugin exists.
    if (!RegisterRenderTracker())
        return false; 

    return true; 
}

// PluginEnd() is called when Cinema 4D is shutting down.
// Clean up any memory or temporary files used by the plugin here.
void PluginEnd()
{
}

// PluginMessage() allows the plugin to listen to and react to various events (messages)
// triggered within Cinema 4D.
Bool PluginMessage(Int32 id, void* data)
{
    switch (id)
    {
        // Message sent when system initialization is finished.
        case C4DPL_INIT_SYS:
            // Initialize global resources (strings, etc.) at this point.
            if (!g_resource.Init())
                return false;
            return true;

        case C4DMSG_PRIORITY:
            return true;

        case C4DPL_PROGRAM_STARTED:
        case C4DPL_BUILDMENU:
        {
            static Float64 lastCheckTime = 0.0;
            Float64 now = GeGetTimer() / 1000.0;
            
            // Limit checks to once every second to avoid overhead
            if (now - lastCheckTime > 1.0)
            {
                BaseDocument* doc = GetActiveDocument();
                if (doc) CheckAndAddRenderNotifier(doc);
                lastCheckTime = now;
            }
            return true;
        }
    }
    return false;
}

void CheckAndAddRenderNotifier(BaseDocument* doc)
{
    if (!doc) return;

    RenderData* rd = doc->GetActiveRenderData();
    if (!rd) return;

    // Check if RenderTracker is already added
    BaseVideoPost* vp = rd->GetFirstVideoPost();
    bool found = false;
    while (vp)
    {
        if (vp->GetType() == ID_RENDER_TRACKER)
        {
            found = true;
            break;
        }
        vp = vp->GetNext();
    }

    // If not found, add it
    if (!found)
    {
        BaseVideoPost* newVP = BaseVideoPost::Alloc(ID_RENDER_TRACKER);
        if (newVP)
        {
            rd->InsertVideoPost(newVP);
            EventAdd();
        }
    }
}

} // namespace cinema
