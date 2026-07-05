cmake_minimum_required(VERSION 3.16)
project(gcrt LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(gcrt STATIC
    src/os.cpp
    src/dvd.cpp
    src/pad.cpp
    src/vi.cpp
    src/gx.cpp
    src/gx_texture.cpp
    src/memory.cpp
    src/dol.cpp
    src/ppc_bridge.cpp
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

add_executable(gcrt_memory_test tests/memory_test.cpp)
target_link_libraries(gcrt_memory_test PRIVATE gcrt)
add_test(NAME memory COMMAND gcrt_memory_test)

# Cross-language check: if python3 is available, build a DOL with the gcport
# tool and load it through the runtime loader in the same test run.
find_program(PYTHON3 python3)
if(PYTHON3)
    set(GENERATED_DOL "${CMAKE_CURRENT_BINARY_DIR}/generated.dol")
    add_test(NAME gen_dol COMMAND ${PYTHON3}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_dol.py" "${GENERATED_DOL}")
    add_test(NAME memory_external COMMAND gcrt_memory_test "${GENERATED_DOL}")
    set_tests_properties(memory_external PROPERTIES DEPENDS gen_dol)

    # Recompile a PPC program to C at build time, compile it into the bridge
    # integration test, and run it against a real gcrt::Memory.
    set(GENERATED_RECOMP "${CMAKE_CURRENT_BINARY_DIR}/recomp_program.c")
    add_custom_command(
        OUTPUT ${GENERATED_RECOMP}
        COMMAND ${PYTHON3}
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_recomp.py"
            ${GENERATED_RECOMP}
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_recomp.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/gcport/ppc/recompile.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/gcport/ppc/decode.py"
        COMMENT "Recompiling PPC test program to C")
    add_executable(gcrt_ppc_bridge_test
        tests/ppc_bridge_test.cpp ${GENERATED_RECOMP})
    target_link_libraries(gcrt_ppc_bridge_test PRIVATE gcrt)
    add_test(NAME ppc_bridge COMMAND gcrt_ppc_bridge_test)

    # Whole-program recompilation: multi-function program with dispatch.
    set(GENERATED_PROGRAM "${CMAKE_CURRENT_BINARY_DIR}/recomp_multi.c")
    add_custom_command(
        OUTPUT ${GENERATED_PROGRAM}
        COMMAND ${PYTHON3}
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_program.py"
            ${GENERATED_PROGRAM}
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/make_program.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/gcport/ppc/recompile.py"
                "${CMAKE_CURRENT_SOURCE_DIR}/../tools/gcport/ppc/decode.py"
        COMMENT "Recompiling multi-function PPC program to C")
    add_executable(gcrt_ppc_program_test
        tests/ppc_program_test.cpp ${GENERATED_PROGRAM})
    target_link_libraries(gcrt_ppc_program_test PRIVATE gcrt)
    add_test(NAME ppc_program COMMAND gcrt_ppc_program_test)

    # Guard: the committed ppc_runtime.h must match the recompiler's output.
    add_test(NAME ppc_header_drift COMMAND ${PYTHON3}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/check_header.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/include/gcrt/ppc_runtime.h")
endif()

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
