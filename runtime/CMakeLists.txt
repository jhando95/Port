cmake_minimum_required(VERSION 3.16)
project(gcrt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(gcrt STATIC
    src/os.cpp
    src/dvd.cpp
    src/pad.cpp
    src/vi.cpp
    src/hal_null.cpp
)
target_include_directories(gcrt PUBLIC include)
target_compile_options(gcrt PRIVATE -Wall -Wextra)

enable_testing()
add_executable(gcrt_smoke_test tests/smoke_test.cpp)
target_link_libraries(gcrt_smoke_test PRIVATE gcrt)
add_test(NAME smoke COMMAND gcrt_smoke_test)
