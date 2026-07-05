cmake_minimum_required(VERSION 3.16)
project(gcrt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(gcrt STATIC
    src/os.cpp
    src/dvd.cpp
    src/pad.cpp
    src/vi.cpp
    src/gx.cpp
    src/gx_texture.cpp
    src/hal_null.cpp
)
target_include_directories(gcrt PUBLIC include)
target_compile_options(gcrt PRIVATE -Wall -Wextra)

option(GCRT_WITH_SDL "Build the SDL2 HAL backend" ON)
if(GCRT_WITH_SDL)
    find_package(SDL2 QUIET)
    if(SDL2_FOUND)
        target_sources(gcrt PRIVATE src/hal_sdl.cpp)
        target_compile_definitions(gcrt PUBLIC GCRT_HAS_SDL=1)
        if(TARGET SDL2::SDL2)
            target_link_libraries(gcrt PUBLIC SDL2::SDL2)
        else()
            target_include_directories(gcrt PUBLIC ${SDL2_INCLUDE_DIRS})
            target_link_libraries(gcrt PUBLIC ${SDL2_LIBRARIES})
        endif()
        message(STATUS "gcrt: SDL2 backend enabled (${SDL2_VERSION})")
    else()
        message(STATUS "gcrt: SDL2 not found, building headless only")
    endif()
endif()

enable_testing()
add_executable(gcrt_smoke_test tests/smoke_test.cpp)
target_link_libraries(gcrt_smoke_test PRIVATE gcrt)
add_test(NAME smoke COMMAND gcrt_smoke_test)

add_executable(gcrt_gx_test tests/gx_test.cpp)
target_link_libraries(gcrt_gx_test PRIVATE gcrt)
add_test(NAME gx COMMAND gcrt_gx_test)

add_executable(gcrt_gx_texture_test tests/gx_texture_test.cpp)
target_link_libraries(gcrt_gx_texture_test PRIVATE gcrt)
add_test(NAME gx_texture COMMAND gcrt_gx_texture_test)

if(SDL2_FOUND)
    add_executable(gcrt_sdl_hal_test tests/sdl_hal_test.cpp)
    target_link_libraries(gcrt_sdl_hal_test PRIVATE gcrt)
    add_test(NAME sdl_hal COMMAND gcrt_sdl_hal_test)

    add_executable(hello_triangle demo/hello_triangle.cpp)
    target_link_libraries(hello_triangle PRIVATE gcrt)
    add_test(NAME demo_headless COMMAND hello_triangle)
    set_tests_properties(demo_headless PROPERTIES
        ENVIRONMENT "SDL_VIDEODRIVER=dummy;GCRT_DEMO_FRAMES=60")
endif()
