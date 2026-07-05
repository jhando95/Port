#include "gcrt/pad.h"

#include "gcrt/hal.h"
#include "gcrt/os.h"

namespace gcrt {

bool PADInit() { return true; }

uint32_t PADRead(PADStatus status[kPadChannels]) {
    PadInput raw[kPadChannels];
    OSHal().pollInput(raw);
    uint32_t connected_mask = 0;
    for (int i = 0; i < kPadChannels; ++i) {
        status[i] = PADStatus{};
        if (!raw[i].connected) {
            status[i].err = PAD_ERR_NO_CONTROLLER;
            continue;
        }
        status[i].button = raw[i].buttons;
        status[i].stickX = raw[i].stick_x;
        status[i].stickY = raw[i].stick_y;
        status[i].substickX = raw[i].substick_x;
        status[i].substickY = raw[i].substick_y;
        status[i].triggerLeft = raw[i].trigger_l;
        status[i].triggerRight = raw[i].trigger_r;
        status[i].err = PAD_ERR_NONE;
        connected_mask |= 1u << i;
    }
    return connected_mask;
}

}  // namespace gcrt
