cmake_minimum_required(VERSION 3.16)
project(live_infinita_audio_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(live-infinita-audio-native src/main.cpp)
target_compile_options(live-infinita-audio-native PRIVATE -O3 -DNDEBUG -Wall -Wextra -Wpedantic)
target_link_libraries(live-infinita-audio-native PRIVATE pthread)
