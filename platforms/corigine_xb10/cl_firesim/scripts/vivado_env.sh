#!/bin/bash

# Source an optional Vivado settings script and require the exact tool release
# supported by the Corigine XB10 port. This file is sourced by
# build-bitstream.sh and intentionally performs no work on its own.
firesim_xb10_activate_vivado() {
    local settings_path="${1:-}"
    local expected_version="${2:-2025.1}"
    local version_output
    local version_line
    local actual_version
    local vivado_path

    if [ -n "$settings_path" ]; then
        if [ ! -r "$settings_path" ]; then
            echo "ERROR: Vivado settings script is not readable: $settings_path" >&2
            return 1
        fi
        # The settings file is an explicit build-recipe input.
        # shellcheck disable=SC1090
        source "$settings_path"
    fi

    if ! vivado_path="$(command -v vivado)"; then
        echo "ERROR: vivado is not on PATH; configure --vivado-settings" >&2
        return 1
    fi

    if ! version_output="$(vivado -version 2>&1)"; then
        echo "ERROR: failed to query Vivado at $vivado_path" >&2
        echo "$version_output" >&2
        return 1
    fi
    version_line="${version_output%%$'\n'*}"
    if [[ "$version_line" =~ ^vivado[[:space:]]v([^[:space:]]+) ]]; then
        actual_version="${BASH_REMATCH[1]}"
    else
        echo "ERROR: unrecognized Vivado version output: $version_line" >&2
        return 1
    fi

    if [ "$actual_version" != "$expected_version" ]; then
        echo "ERROR: Corigine XB10 requires Vivado $expected_version, found $actual_version at $vivado_path" >&2
        return 1
    fi

    echo "Using Vivado $actual_version at $vivado_path"
}
