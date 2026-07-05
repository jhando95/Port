// Hardware abstraction layer: everything platform-facing goes through Hal so
// the runtime builds headlessly (NullHal) and gains an SDL backend later
// without touching subsystem code.
#pragma once

#include <cstdint>

namespace gcrt {

struct PadInput {
    uint16_t buttons = 0;
    int8_t stick_x = 0, stick_y = 0;
    int8_t substick_x = 0, substick_y = 0;
    uint8_t trigger_l = 0, trigger_r = 0;
    bool connected = false;
};

class Hal {
public:
    virtual ~Hal() = default;
    virtual uint64_t nowNs() = 0;              // monotonic
    virtual void sleepNs(uint64_t ns) = 0;
    virtual void pollInput(PadInput out[4]) = 0;
    virtual void log(const char* message) = 0;
};

// Headless backend: real clock, no-op sleep-capable, no controllers, stderr log.
class NullHal final : public Hal {
public:
    explicit NullHal(bool real_sleep = false) : real_sleep_(real_sleep) {}
    uint64_t nowNs() override;
    void sleepNs(uint64_t ns) override;
    void pollInput(PadInput out[4]) override;
    void log(const char* message) override;

private:
    bool real_sleep_;
};

}  // namespace gcrt
