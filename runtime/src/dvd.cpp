#include "gcrt/dvd.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <filesystem>
#include <string>

#include "gcrt/os.h"

namespace fs = std::filesystem;

namespace gcrt {
namespace {

fs::path g_root;

// Resolve a GC-style path against the asset tree. Exact match first, then a
// per-component case-insensitive fallback (FST lookups ignore case).
bool resolvePath(const char* gc_path, fs::path* out) {
    std::string p = gc_path ? gc_path : "";
    while (!p.empty() && p.front() == '/') p.erase(p.begin());

    fs::path current = g_root;
    std::string component;
    auto descend = [&](const std::string& name) -> bool {
        fs::path exact = current / name;
        if (fs::exists(exact)) {
            current = exact;
            return true;
        }
        if (!fs::is_directory(current)) return false;
        for (const auto& entry : fs::directory_iterator(current)) {
            std::string candidate = entry.path().filename().string();
            if (candidate.size() == name.size() &&
                std::equal(candidate.begin(), candidate.end(), name.begin(),
                           [](char a, char b) {
                               return std::tolower(static_cast<unsigned char>(a)) ==
                                      std::tolower(static_cast<unsigned char>(b));
                           })) {
                current = entry.path();
                return true;
            }
        }
        return false;
    };

    for (char c : p) {
        if (c == '/') {
            if (!component.empty() && !descend(component)) return false;
            component.clear();
        } else {
            component.push_back(c);
        }
    }
    if (!component.empty() && !descend(component)) return false;

    // keep lookups inside the asset root
    auto canonical = fs::weakly_canonical(current);
    auto root_canonical = fs::weakly_canonical(g_root);
    auto mismatch = std::mismatch(root_canonical.begin(), root_canonical.end(),
                                  canonical.begin(), canonical.end());
    if (mismatch.first != root_canonical.end()) return false;

    *out = current;
    return true;
}

}  // namespace

void DVDInit() {
    const char* root = OSAssetRoot();
    if (!root) {
        OSReport("DVDInit: no asset_root configured; DVD reads will fail");
        g_root.clear();
        return;
    }
    g_root = root;
    if (!fs::is_directory(g_root)) {
        OSReport("DVDInit: asset root '%s' is not a directory", root);
    }
}

bool DVDEntryExists(const char* path) {
    fs::path resolved;
    return !g_root.empty() && resolvePath(path, &resolved);
}

bool DVDOpen(const char* path, DVDFileInfo* file_info) {
    if (!file_info || g_root.empty()) return false;
    fs::path resolved;
    if (!resolvePath(path, &resolved) || !fs::is_regular_file(resolved)) {
        return false;
    }
    std::FILE* handle = std::fopen(resolved.string().c_str(), "rb");
    if (!handle) return false;
    file_info->length = static_cast<uint32_t>(fs::file_size(resolved));
    file_info->impl = handle;
    file_info->callback = nullptr;
    return true;
}

bool DVDClose(DVDFileInfo* file_info) {
    if (!file_info || !file_info->impl) return false;
    std::fclose(static_cast<std::FILE*>(file_info->impl));
    file_info->impl = nullptr;
    return true;
}

int32_t DVDRead(DVDFileInfo* file_info, void* buffer, int32_t length,
                int32_t offset) {
    if (!file_info || !file_info->impl || length < 0 || offset < 0) return -1;
    auto* handle = static_cast<std::FILE*>(file_info->impl);
    if (std::fseek(handle, offset, SEEK_SET) != 0) return -1;
    size_t read = std::fread(buffer, 1, static_cast<size_t>(length), handle);
    return static_cast<int32_t>(read);
}

int32_t DVDReadAsync(DVDFileInfo* file_info, void* buffer, int32_t length,
                     int32_t offset, DVDCallback callback) {
    int32_t result = DVDRead(file_info, buffer, length, offset);
    if (callback) callback(result, file_info);
    return result >= 0 ? 1 : -1;
}

}  // namespace gcrt
