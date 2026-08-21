#!/bin/bash
#SBATCH -J lu_to_classic
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=48g
#SBATCH -t 04:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

# Rewrite the four production SSP landuse.timeseries files from NETCDF4+zlib
# into the classic NETCDF3_64BIT_OFFSET container the historical file uses.
# This is a container change only -- it does NOT re-run the generation
# pipeline (submit_landuse_future*.sbatch), which could produce numerically
# different output for files that downstream work has already used.
#
# Two phases, and phase B only starts if every file cleared phase A:
#   A  convert to <name>.classic-tmp and verify tmp vs original
#   B  original -> <name>.nc4-orig, tmp -> <name>, verify again
#
# The .nc4-orig originals are deliberately left on disk. Deleting them is a
# separate, explicit decision.

set -euo pipefail
ROOT=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
cd "$ROOT"
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
QA=/projects/hpcl-cli185/proj-shared/zw5/SEUS_halfdeg/qa/check_format_equivalence.py
PROC=$ROOT/outputs/processed
SCENARIOS=(SSP1_RCP19 SSP2_RCP45 SSP3_RCP70 SSP5_RCP85)

stem() { echo "$PROC/landuse.timeseries_SEUS_1_24deg_nlcd2elm_$1_simyr2024-2100.nc"; }

# check_classic_rebuild.py is the gate: it requires every value byte-identical
# and every structural difference to be one of the two intended ones. Its exit
# status is what the job stands or falls on.
#
# check_format_equivalence.py runs alongside as an independent second opinion,
# but its exit status is not usable directly and its output has to be read
# rather than trusted, for two reasons:
#   * it reports the intended _FillValue removal as a plain FAIL, having no
#     notion of an intended change;
#   * its value test is np.array_equal, which returns False for two arrays
#     identical down to the bit if either holds a NaN. These files are
#     documented as NaN-free, so that check is expected to PASS here -- but it
#     is not the thing being relied on. check_classic_rebuild.py compares raw
#     bytes and prints the NaN count per variable, so a spurious failure here
#     would be visible as such rather than mistaken for a real one.
# So: require its FAIL set to be a subset of those two known names, and let the
# byte-level check decide.
verify() {
    local a=$1 b=$2 tag=$3

    echo "-- check_classic_rebuild.py (authoritative) --"
    "$PY" scripts/check_classic_rebuild.py --a "$a" --b "$b"

    echo "-- check_format_equivalence.py (second opinion) --"
    local out
    out=$("$PY" "$QA" --a "$a" --b "$b" 2>&1) || true
    echo "$out"
    local unexpected
    unexpected=$(printf '%s\n' "$out" \
        | grep '\[FAIL\]' \
        | grep -vE 'variable attributes identical|all [0-9]+ variables bitwise identical' \
        || true)
    if [ -n "$unexpected" ]; then
        echo "FATAL($tag): unexpected failing check(s) from the second opinion:"
        echo "$unexpected"
        exit 1
    fi
    echo "VERIFIED($tag)"
}

echo "==================== phase A: convert and verify ===================="
for SC in "${SCENARIOS[@]}"; do
    SRC=$(stem "$SC")
    TMP=$SRC.classic-tmp
    echo "-------------------- $SC --------------------"
    if [ ! -s "$SRC" ]; then echo "FATAL: missing $SRC"; exit 1; fi
    if [ -e "$TMP" ]; then echo "FATAL: $TMP already exists"; exit 1; fi
    "$PY" scripts/to_classic_netcdf.py --src "$SRC" --dst "$TMP"
    ls -lh "$SRC" "$TMP"
    verify "$SRC" "$TMP" "A/$SC"
done

echo
echo "==================== phase B: swap and re-verify ===================="
for SC in "${SCENARIOS[@]}"; do
    SRC=$(stem "$SC")
    TMP=$SRC.classic-tmp
    KEEP=$SRC.nc4-orig
    echo "-------------------- $SC --------------------"
    if [ -e "$KEEP" ]; then echo "FATAL: $KEEP already exists"; exit 1; fi
    mv -n "$SRC" "$KEEP"
    mv -n "$TMP" "$SRC"
    # mv -n is a silent no-op on an existing target, so confirm the swap
    # actually happened rather than trusting its exit status.
    if [ -e "$TMP" ] || [ ! -s "$KEEP" ] || [ ! -s "$SRC" ]; then
        echo "FATAL: swap did not complete for $SC"; exit 1
    fi
    ls -lh "$KEEP" "$SRC"
    verify "$KEEP" "$SRC" "B/$SC"
done

echo
echo "==================== done ===================="
ls -lh "$PROC"/landuse.timeseries_*
