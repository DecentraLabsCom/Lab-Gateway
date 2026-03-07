cmake_minimum_required(VERSION 3.20)

project(decentralabs_proxy_runtime VERSION 0.1.0 LANGUAGES CXX)

add_library(
  decentralabs_proxy_core
  STATIC
  src/protocol.cpp
  src/runtime_config.cpp
  src/session_state.cpp
)

target_compile_features(decentralabs_proxy_core PUBLIC cxx_std_17)

target_include_directories(
  decentralabs_proxy_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_options(
  decentralabs_proxy_core
  PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /permissive->
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -Wpedantic>
)

set_target_properties(
  decentralabs_proxy_core
  PROPERTIES
    OUTPUT_NAME "decentralabs_proxy_core"
)
