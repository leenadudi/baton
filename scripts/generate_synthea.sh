#!/usr/bin/env bash
# Generate Synthea FHIR bundles into dataset/synthea/.
# Usage: scripts/generate_synthea.sh [patient_count]   (default: 20)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNTHEA_DIR="$REPO_ROOT/.synthea"
OUT_DIR="$REPO_ROOT/dataset/synthea"
COUNT="${1:-20}"

if [ ! -d "$SYNTHEA_DIR" ]; then
    git clone --depth 1 https://github.com/synthetichealth/synthea "$SYNTHEA_DIR"
fi

cd "$SYNTHEA_DIR"
./run_synthea -p "$COUNT" -s 42 Massachusetts

mkdir -p "$OUT_DIR"
cp output/fhir/*.json "$OUT_DIR/"
echo "Copied $(ls "$OUT_DIR"/*.json | wc -l) bundles to $OUT_DIR"
