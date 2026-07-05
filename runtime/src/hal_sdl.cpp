#include "gcrt/hal_sdl.h"

#include <SDL.h>

#include <chrono>
#include <cstdio>
#include <stdexcept>
#include <thread>

#include "gcrt/pad.h"

namespace gcrt {
namespace {

SDL_GameController* g_controllers[4] = {};

void refreshControllers() {
    int slot = 0;
    for (int i = 0; i < SDL_NumJoysticks() && slot < 4; ++i) {
        if (!SDL_IsGameController(i)) continue;
        if (!g_controllers[slot]) {
            g_controllers[slot] = SDL_GameControllerOpen(i);
        }
        ++slot;
    }
}

int8_t axisToStick(Sint16 value) {
    return static_cast<int8_t>(value / 328);  // SDL ±32767 → GC ±~100
}

void readController(SDL_GameController* pad, PadInput* out) {
    out->connected = true;
    uint16_t buttons = 0;
    auto pressed = [&](SDL_GameControllerButton b) {
        return SDL_GameControllerGetButton(pad, b) != 0;
    };
    if (pressed(SDL_CONTROLLER_BUTTON_A)) buttons |= PAD_BUTTON_A;
    if (pressed(SDL_CONTROLLER_BUTTON_B)) buttons |= PAD_BUTTON_B;
    if (pressed(SDL_CONTROLLER_BUTTON_X)) buttons |= PAD_BUTTON_X;
    if (pressed(SDL_CONTROLLER_BUTTON_Y)) buttons |= PAD_BUTTON_Y;
    if (pressed(SDL_CONTROLLER_BUTTON_START)) buttons |= PAD_BUTTON_START;
    if (pressed(SDL_CONTROLLER_BUTTON_DPAD_UP)) buttons |= PAD_BUTTON_UP;
    if (pressed(SDL_CONTROLLER_BUTTON_DPAD_DOWN)) buttons |= PAD_BUTTON_DOWN;
    if (pressed(SDL_CONTROLLER_BUTTON_DPAD_LEFT)) buttons |= PAD_BUTTON_LEFT;
    if (pressed(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) buttons |= PAD_BUTTON_RIGHT;
    if (pressed(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)) buttons |= PAD_TRIGGER_Z;

    auto axis = [&](SDL_GameControllerAxis a) {
        return SDL_GameControllerGetAxis(pad, a);
    };
    out->stick_x = axisToStick(axis(SDL_CONTROLLER_AXIS_LEFTX));
    out->stick_y = static_cast<int8_t>(-axisToStick(axis(SDL_CONTROLLER_AXIS_LEFTY)));
    out->substick_x = axisToStick(axis(SDL_CONTROLLER_AXIS_RIGHTX));
    out->substick_y =
        static_cast<int8_t>(-axisToStick(axis(SDL_CONTROLLER_AXIS_RIGHTY)));
    out->trigger_l =
        static_cast<uint8_t>(axis(SDL_CONTROLLER_AXIS_TRIGGERLEFT) >> 7);
    out->trigger_r =
        static_cast<uint8_t>(axis(SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >> 7);
    if (out->trigger_l > 200) buttons |= PAD_TRIGGER_L;
    if (out->trigger_r > 200) buttons |= PAD_TRIGGER_R;
    out->buttons = buttons;
}

void readKeyboard(PadInput* out) {
    const Uint8* keys = SDL_GetKeyboardState(nullptr);
    uint16_t buttons = 0;
    if (keys[SDL_SCANCODE_X]) buttons |= PAD_BUTTON_A;
    if (keys[SDL_SCANCODE_Z]) buttons |= PAD_BUTTON_B;
    if (keys[SDL_SCANCODE_S]) buttons |= PAD_BUTTON_X;
    if (keys[SDL_SCANCODE_D]) buttons |= PAD_BUTTON_Y;
    if (keys[SDL_SCANCODE_RETURN]) buttons |= PAD_BUTTON_START;
    if (keys[SDL_SCANCODE_C]) buttons |= PAD_TRIGGER_Z;
    if (keys[SDL_SCANCODE_Q]) { buttons |= PAD_TRIGGER_L; out->trigger_l = 255; }
    if (keys[SDL_SCANCODE_W]) { buttons |= PAD_TRIGGER_R; out->trigger_r = 255; }
    int x = 0, y = 0;
    if (keys[SDL_SCANCODE_LEFT]) x -= 100;
    if (keys[SDL_SCANCODE_RIGHT]) x += 100;
    if (keys[SDL_SCANCODE_DOWN]) y -= 100;
    if (keys[SDL_SCANCODE_UP]) y += 100;
    if (buttons || x || y) out->connected = true;
    out->buttons |= buttons;
    out->stick_x = static_cast<int8_t>(x);
    out->stick_y = static_cast<int8_t>(y);
}

}  // namespace

SdlHal::SdlHal(const Options& options) {
    Uint32 flags = SDL_INIT_GAMECONTROLLER;
    if (!options.headless) flags |= SDL_INIT_VIDEO;
    if (SDL_Init(flags) != 0) {
        throw std::runtime_error(std::string("SDL_Init failed: ") +
                                 SDL_GetError());
    }
    if (!options.headless) {
        window_ = SDL_CreateWindow(
            options.window_title, SDL_WINDOWPOS_CENTERED,
            SDL_WINDOWPOS_CENTERED, options.width, options.height,
            SDL_WINDOW_RESIZABLE);
        if (!window_) {
            SDL_Quit();
            throw std::runtime_error(std::string("SDL_CreateWindow failed: ") +
                                     SDL_GetError());
        }
    }
    refreshControllers();
}

SdlHal::~SdlHal() {
    for (auto*& pad : g_controllers) {
        if (pad) SDL_GameControllerClose(pad);
        pad = nullptr;
    }
    if (window_) SDL_DestroyWindow(window_);
    SDL_Quit();
}

uint64_t SdlHal::nowNs() {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count());
}

void SdlHal::sleepNs(uint64_t ns) {
    std::this_thread::sleep_for(std::chrono::nanoseconds(ns));
}

void SdlHal::pollInput(PadInput out[4]) {
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT ||
            (event.type == SDL_KEYDOWN &&
             event.key.keysym.scancode == SDL_SCANCODE_ESCAPE)) {
            quit_requested_ = true;
        }
        if (event.type == SDL_CONTROLLERDEVICEADDED) refreshControllers();
    }
    for (int i = 0; i < 4; ++i) {
        out[i] = PadInput{};
        if (g_controllers[i]) readController(g_controllers[i], &out[i]);
    }
    // keyboard overlays pad 0 so the runtime is usable with no controller
    readKeyboard(&out[0]);
}

void SdlHal::log(const char* message) {
    std::fprintf(stderr, "%s\n", message);
}

}  // namespace gcrt
