#!/bin/bash
# T2 -- 4 km future end-of-record test, 2100-12-29 -> 2101-01-01.
#
# Independent CASEROOT and RUNDIR: T1's outputs are evidence and must not be
# overwritten. Cloned from T1 WITHOUT --keepexe, because the diagnostic
# SourceMods changed (metvars removed from every block but DIAG_INIT) and the
# executable has to be rebuilt to pick that up.
#
# What T2 is for: T1 proved the start of the record. Bounds checking in T1
# proves only that the paths its 49 timesteps executed were in range; it says
# nothing about 2100. The guard that matters at the end of the record
# (fc2a4f2be1) has only ever been exercised in the historical configuration, at
# 0.5deg, where npf=6. At 4km npf=3 and FSDS/PRECTmms advance on a different
# phase from the other five, so which variable reaches timelen first, and on
# which timestep, is not transferable from that test.
#
# finidat is still the old 2024 restart. The three check_*_consistency switches
# are off, so a 2024 initial state can start a 2100 clock -- the same device the
# historical run uses to start a 1850 clock from a year-0441 spinup restart.
# Nothing here is a science result; only the driver index path is under test.
#
# Deliberately NOT asserted in advance: whether the hold guard fires, whether an
# import happens at yr=2101, which indices satisfy the wrap condition. Those are
# what the run is supposed to report. Predicting them and then checking the
# prediction would just be checking the prediction.
#
#   ./setup_t2_end2100.sh            # create, configure, build
#   SKIP_BUILD=1 ./setup_t2_end2100.sh

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
CASE=20260906_seus_4km_fut_end2100
CASEROOT=$BASE/e3sm_cases/$CASE
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
PINNED=0be814f868
CLONE_FROM=$BASE/e3sm_cases/20260905_seus_4km_fut_t0_ssp370
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs

say() { printf '\n=== %s ===\n' "$*"; }

say "0. reader source must still match the pinned commit"
cd $SRC
F=components/elm/src/cpl/lnd_import_export.F90
if ! git diff --quiet $PINNED HEAD -- $F || ! git diff --quiet -- $F; then
  echo "$F differs from $PINNED. Refusing to build." >&2; exit 1
fi
echo "$F matches $PINNED (HEAD $(git rev-parse --short=10 HEAD))"

say "1. clone from T1, independent build and rundir"
[[ -d $CASEROOT ]] && { echo "$CASEROOT exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $CASEROOT --clone $CLONE_FROM --cime-output-root $OUTROOT
cd $CASEROOT
./xmlchange RUNDIR=$OUTROOT/$CASE/run,EXEROOT=$OUTROOT/$CASE/bld
./xmlquery RUNDIR,EXEROOT --value

say "2. DEBUG + case.setup --reset, then re-apply both macro edits"
./xmlchange DEBUG=TRUE
./case.setup --reset
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
sed -i 's/ -ffpe-trap=invalid,zero,overflow//' cmake_macros/gnu.cmake
grep -n CPPDEFS cmake_macros/universal.cmake
echo "ffpe-trap remaining: $(grep -c 'ffpe-trap' cmake_macros/gnu.cmake || true)"

say "3. diagnostic SourceMods, window on the end of the record"
mkdir -p SourceMods/src.elm
git -C $SRC show $PINNED:$F > /tmp/lie_$PINNED.F90
python3 $HARNESS/sourcemods/make_diag_sourcemod.py \
    --src /tmp/lie_$PINNED.F90 \
    --out SourceMods/src.elm/lnd_import_export.F90 \
    --first-n 24 \
    --window 21001229-21010101
# metvars must appear only in DIAG_INIT; anywhere else it is uninitialised
echo "metvars refs in DIAG blocks: $(grep -c "trim(metvars" SourceMods/src.elm/lnd_import_export.F90)"

say "4. dates: three model days ending exactly at 2101-01-01"
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2100-12-29,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=ndays,STOP_N=3,REST_OPTION=ndays,REST_N=3,RESUBMIT=0
./xmlchange JOB_WALLCLOCK_TIME=02:00:00
# hist_mfilt has to cover 3 days of hourly output
sed -i 's/^ hist_mfilt = .*/ hist_mfilt = 72/' user_nl_elm
grep -E 'hist_mfilt|hist_nhtfrq|hist_empty|hist_fincl1' user_nl_elm

say "5. verify the inputs came across unchanged from T1"
grep -E 'finidat|flanduse_timeseries|metdata_type|metdata_bypass|co2_file|stream_fldfilename_ndep' user_nl_elm \
  | sed 's|/projects/hpcl-cli185/||'

say "6. build"
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  cat > build_t2.sbatch <<EOF
#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p parallel
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 32
#SBATCH --mem=64g
#SBATCH --time=01:00:00
#SBATCH -J bld_t2
#SBATCH -o $CASEROOT/build_t2.%j.out
cd $CASEROOT && ./case.build
EOF
  sbatch build_t2.sbatch
fi

say "done -- check before submitting"
echo "  ./preview_run"
echo "  zgrep -l CPL_BYPASS $OUTROOT/$CASE/bld/e3sm.bldlog.*"
