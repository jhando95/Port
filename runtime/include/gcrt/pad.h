// PAD service: GameCube controller input.
#pragma once

#include <cstdint>

namespace gcrt {

// Button bits match the GameCube SDK PADStatus layout.
enum PadButton : uint16_t {
    PAD_BUTTON_LEFT = 0x0001,
    PAD_BUTTON_RIGHT = 0x0002,
    PAD_BUTTON_DOWN = 0x0004,
    PAD_BUTTON_UP = 0x0008,
    PAD_TRIGGER_Z = 0x0010,
    PAD_TRIGGER_R = 0x0020,
    PAD_TRIGGER_L = 0x0040,
    PAD_BUTTON_A = 0x0100,
    PAD_BUTTON_B = 0x0200,
    PAD_BUTTON_X = 0x0400,
    PAD_BUTTON_Y = 0x0800,
    PAD_BUTTON_START = 0x1000,
};

struct PADStatus {
    uint16_t button = 0;
    int8_t stickX = 0, stickY = 0;
    int8_t substickX = 0, substickY = 0;
    uint8_t triggerLeft = 0, triggerRight = 0;
    uint8_t analogA = 0, analogB = 0;
    int8_t err = 0;  // PAD_ERR_NONE / PAD_ERR_NO_CONTROLLER
};

constexpr int8_t PAD_ERR_NONE = 0;
constexpr int8_t PAD_ERR_NO_CONTROLLER = -1;
constexpr int kPadChannels = 4;

bool PADInit();
// Fills all four channels from the HAL input backend.
uint32_t PADRead(PADStatus status[kPadChannels]);

}  // namespace gcrt
