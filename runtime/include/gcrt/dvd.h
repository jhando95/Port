// DVD service: the GameCube's async disc-read API mapped onto an extracted
// asset directory (the files/ tree produced by `gcport iso extract`).
// Reads are synchronous under the hood for now; the async callback flavor
// dispatches immediately, which satisfies the SDK contract.
#pragma once

#include <cstdint>

namespace gcrt {

struct DVDFileInfo;
using DVDCallback = void (*)(int32_t result, DVDFileInfo* file_info);

struct DVDFileInfo {
    uint32_t length = 0;
    void* impl = nullptr;  // opaque host file handle
    DVDCallback callback = nullptr;
};

// Root comes from RuntimeConfig::asset_root at OSInit time.
void DVDInit();

// Paths use GameCube convention: '/' separated, relative to filesystem root,
// leading '/' optional, case-insensitive resolution (FST semantics).
bool DVDOpen(const char* path, DVDFileInfo* file_info);
bool DVDClose(DVDFileInfo* file_info);

// Returns bytes read, or a negative value on error. offset is within the file.
int32_t DVDRead(DVDFileInfo* file_info, void* buffer, int32_t length,
                int32_t offset);
int32_t DVDReadAsync(DVDFileInfo* file_info, void* buffer, int32_t length,
                     int32_t offset, DVDCallback callback);

// True if the path exists in the asset tree (file or directory).
bool DVDEntryExists(const char* path);

}  // namespace gcrt
