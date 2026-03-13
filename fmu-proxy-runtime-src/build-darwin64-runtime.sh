#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_dir="$script_dir/build-darwin64"
runtime_output="$repo_root/fmu-proxy-runtime/binaries/darwin64/decentralabs_proxy.dylib"

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required to build the darwin64 FMU proxy runtime." >&2
  exit 1
fi

openssl_root="${OPENSSL_ROOT_DIR:-}"
if [[ -z "$openssl_root" ]]; then
  if command -v brew >/dev/null 2>&1; then
    openssl_root="$(brew --prefix openssl@3 2>/dev/null || true)"
  fi
fi

if [[ -z "$openssl_root" || ! -d "$openssl_root" ]]; then
  echo "OpenSSL 3 was not found. Install it first, for example with: brew install openssl@3" >&2
  exit 1
fi

cmake -S "$script_dir" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release -DOPENSSL_ROOT_DIR="$openssl_root"
cmake --build "$build_dir" -j

if [[ "${1:-}" == "--promote" ]]; then
  mkdir -p "$(dirname "$runtime_output")"
  cp "$build_dir/libdecentralabs_proxy.dylib" "$runtime_output"
  ls -l "$runtime_output"
fi

