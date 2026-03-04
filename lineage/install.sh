#!/usr/bin/env bash
set -euo pipefail

LINEAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${LINEAGE_ROOT}/bin/lineage" install "$@"
