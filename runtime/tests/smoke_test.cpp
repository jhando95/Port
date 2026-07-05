// Boots the runtime against a synthetic asset tree and exercises every
// subsystem the way a recompiled game's main loop would.
#include <cassert>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>

#include "gcrt/dvd.h"
#include "gcrt/os.h"
#include "gcrt/pad.h"
#include "gcrt/vi.h"

namespace fs = std::filesystem;
using namespace gcrt;

namespace {

int g_failures = 0;

#define CHECK(cond)                                                     \
    do {                                                                \
        if (!(cond)) {                                                  \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, \
                         #cond);                                        \
            ++g_failures;                                               \
        }                                                               \
    } while (0)

uint32_t g_retraces_seen = 0;
void onRetrace(uint32_t count) { g_retraces_seen = count; }

}  // namespace

int main() {
    // --- synthetic asset tree -------------------------------------------
    fs::path root = fs::temp_directory_path() / "gcrt_smoke_assets";
    fs::remove_all(root);
    fs::create_directories(root / "Course");
    const std::string luigi = "luigi circuit archive payload";
    std::ofstream(root / "Course" / "Luigi.arc", std::ios::binary) << luigi;
    std::ofstream(root / "opening.bnr", std::ios::binary) << "banner";

    // --- OS ----------------------------------------------------------------
    NullHal hal;
    RuntimeConfig config;
    config.hal = &hal;
    std::string root_str = root.string();
    config.asset_root = root_str.c_str();
    OSInit(config);
    OSReport("gcrt smoke test booting (asset root %s)", root_str.c_str());

    uint64_t t0 = OSGetTime();
    CHECK(OSGetTime() >= t0);

    void* block = OSAllocFromArenaLo(0x1000, 32);
    CHECK(block != nullptr);
    CHECK(reinterpret_cast<uintptr_t>(block) % 32 == 0);
    std::memset(block, 0xAA, 0x1000);
    CHECK(OSGetArenaLo() > block);
    CHECK(OSGetArenaLo() < OSGetArenaHi());

    // --- DVD -----------------------------------------------------------------
    DVDInit();
    CHECK(DVDEntryExists("/Course/Luigi.arc"));
    CHECK(DVDEntryExists("course/luigi.arc"));  // case-insensitive like the FST
    CHECK(!DVDEntryExists("/Course/Missing.arc"));
    CHECK(!DVDEntryExists("/../escape"));

    DVDFileInfo file;
    CHECK(DVDOpen("/Course/Luigi.arc", &file));
    CHECK(file.length == luigi.size());
    char buffer[64] = {};
    int32_t read = DVDRead(&file, buffer, static_cast<int32_t>(file.length), 0);
    CHECK(read == static_cast<int32_t>(luigi.size()));
    CHECK(luigi == std::string(buffer, static_cast<size_t>(read)));
    // partial read at offset, like streaming audio does
    read = DVDRead(&file, buffer, 7, 6);
    CHECK(read == 7);
    CHECK(std::string(buffer, 7) == "circuit");
    CHECK(DVDClose(&file));

    bool async_fired = false;
    static bool* fired_ptr;
    fired_ptr = &async_fired;
    CHECK(DVDOpen("opening.bnr", &file));
    DVDReadAsync(
        &file, buffer, 6, 0,
        +[](int32_t result, DVDFileInfo*) { *fired_ptr = result == 6; });
    CHECK(async_fired);
    CHECK(DVDClose(&file));

    // --- PAD -------------------------------------------------------------
    CHECK(PADInit());
    PADStatus pads[kPadChannels];
    uint32_t mask = PADRead(pads);
    CHECK(mask == 0);  // NullHal has no controllers
    CHECK(pads[0].err == PAD_ERR_NO_CONTROLLER);

    // --- VI: a 10-frame "game loop" -------------------------------------
    VIInit();
    VISetFrameRateForTesting(0);  // no real-time pacing in CI
    VISetPostRetraceCallback(onRetrace);
    for (int frame = 0; frame < 10; ++frame) {
        PADRead(pads);
        VIWaitForRetrace();
    }
    CHECK(VIGetRetraceCount() == 10);
    CHECK(g_retraces_seen == 10);

    OSShutdown();
    fs::remove_all(root);

    if (g_failures == 0) {
        std::printf("gcrt smoke test: all checks passed\n");
        return 0;
    }
    std::fprintf(stderr, "gcrt smoke test: %d failure(s)\n", g_failures);
    return 1;
}
