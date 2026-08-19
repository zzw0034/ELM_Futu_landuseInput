#!/bin/bash
# One-off: copy the 4-scenario, 7-variable TESSFA2 future cpl_bypass output
# (28 files, ~96GiB each, produced by convertTESSFA2bypass/) from /scratch
# (purged periodically) to its durable canonical location under
# world-shared/e3sm/inputdata, which is what metdata_bypass needs to point
# at for the actual model runs. Run 2026-08-19 as Slurm job 465730 via
# sync_to_worldshared.sbatch.
#
# Does not use --delete: existing files at DEST with the same scenario name
# (there were already 4 ssp585 files there from an earlier, independently
# validated run) are overwritten by rsync's normal same-path behavior, not
# wiped first. New-pipeline output was already verified byte-identical to
# the old pipeline's for every variable checked, so overwriting was
# considered safe.
set -euo pipefail
SRC=/scratch/hpcl-cli185/zw5/future_clim
DEST=/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim

mkdir -p "$DEST"
PIDS=()
for s in ssp119 ssp245 ssp370 ssp585; do
    mkdir -p "$DEST/$s"
    echo "=== starting $s: $SRC/$s -> $DEST/$s ($(date)) ==="
    rsync -av --info=progress2 "$SRC/$s/" "$DEST/$s/" \
        > "/tmp/rsync_${s}.log" 2>&1 &
    PIDS+=($!)
done

FAIL=0
for i in "${!PIDS[@]}"; do
    s=(ssp119 ssp245 ssp370 ssp585)
    if wait "${PIDS[$i]}"; then
        echo "=== ${s[$i]} DONE ($(date)) ==="
    else
        echo "=== ${s[$i]} FAILED ($(date)) ==="
        FAIL=1
    fi
done

echo
echo "=== size check ==="
for s in ssp119 ssp245 ssp370 ssp585; do
    src_sz=$(du -sb "$SRC/$s" | cut -f1)
    dst_sz=$(du -sb "$DEST/$s" | cut -f1)
    echo "$s: src=$src_sz dst=$dst_sz $([ "$src_sz" = "$dst_sz" ] && echo MATCH || echo MISMATCH)"
done

if [ $FAIL -eq 0 ]; then
    echo "ALL 4 SCENARIOS SYNCED OK"
else
    echo "SOME SCENARIOS FAILED -- check /tmp/rsync_*.log"
    exit 1
fi
