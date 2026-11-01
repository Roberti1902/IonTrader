cmake_minimum_required(VERSION 3.20...4.2)
project(ioncore LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)
find_package(OpenMP REQUIRED)

nanobind_add_module(ioncore NOMINSIZE ioncore.cpp)
target_link_libraries(ioncore PRIVATE OpenMP::OpenMP_CXX)
if(MSVC)
  target_compile_options(ioncore PRIVATE /O2 /arch:AVX2 /fp:fast)
endif()

install(TARGETS ioncore LIBRARY DESTINATION .)
