cmake_minimum_required(VERSION 3.20)

project(decentralabs_proxy_runtime VERSION 0.1.0 LANGUAGES CXX)

add_library(
  decentralabs_proxy_core
  STATIC
  src/gateway_client.cpp
  src/json.cpp
  src/model_description.cpp
  src/protocol.cpp
  src/runtime.cpp
  src/runtime_config.cpp
  src/session_state.cpp
  src/transport.cpp
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

target_compile_definitions(
  decentralabs_proxy_core
  PRIVATE
    $<$<PLATFORM_ID:Windows>:_WIN32_WINNT=0x0603>
)

target_link_libraries(
  decentralabs_proxy_core
  PUBLIC
    $<$<PLATFORM_ID:Windows>:winhttp>
)

set_target_properties(
  decentralabs_proxy_core
  PROPERTIES
    OUTPUT_NAME "decentralabs_proxy_core"
)

add_library(
  decentralabs_proxy
  SHARED
  src/fmi2_exports.cpp
  src/fmi3_exports.cpp
)

target_compile_features(decentralabs_proxy PUBLIC cxx_std_17)

target_include_directories(
  decentralabs_proxy
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(
  decentralabs_proxy
  PRIVATE
    decentralabs_proxy_core
)

set_target_properties(
  decentralabs_proxy
  PROPERTIES
    OUTPUT_NAME "decentralabs_proxy"
)
