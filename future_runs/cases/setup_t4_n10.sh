#!/bin/bash
# T4 second layout: 1280 tasks / 10 nodes, sharing the 20-node case's binary.
# Run only AFTER the 20-node build has finished.
set -euo pipefail
BASE=/projects/hpcl-cli185/proj-shared/zw5
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs
CASE20=20260908_seus_4km_fut_t4_n20
CASE10=20260908_seus_4km_fut_t4_n10
FLAGS='--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'
say() { printf '\n=== %s ===\n' "$*"; }

say "0. the 20-node build must exist"
EX20=$OUTROOT/$CASE20/bld
[[ -x $EX20/e3sm.exe ]] || { echo "no e3sm.exe in $EX20" >&2; exit 1; }
echo "exe md5: $(md5sum $EX20/e3sm.exe | cut -d' ' -f1)"

say "1. clone with --keepexe (one binary for both layouts)"
[[ -d $BASE/e3sm_cases/$CASE10 ]] && { echo "exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $BASE/e3sm_cases/$CASE10 --clone $BASE/e3sm_cases/$CASE20 \
    --cime-output-root $OUTROOT --keepexe
cd $BASE/e3sm_cases/$CASE10

say "2. repoint RUNDIR before anything else (--keepexe aims it at the source case)"
./xmlchange RUNDIR=$OUTROOT/$CASE10/run
RD=$(./xmlquery RUNDIR --value); EX=$(./xmlquery EXEROOT --value)
[[ "$RD" == "$OUTROOT/$CASE20/run" ]] && { echo "FATAL: RUNDIR still the 20-node run dir" >&2; exit 1; }
[[ "$EX" == "$EX20" ]] || { echo "FATAL: EXEROOT is not the 20-node build" >&2; exit 1; }
mkdir -p "$RD"

say "3. PE layout 1280 / 10 nodes, then case.setup and restore what it re-renders"
for c in ATM LND ICE OCN CPL GLC ROF WAV ESP IAC; do
  ./xmlchange NTASKS_$c=1280,NTHRDS_$c=1 >/dev/null
done
./xmlchange MAX_MPITASKS_PER_NODE=128,MAX_TASKS_PER_NODE=128
./case.setup --reset
./xmlchange BUILD_COMPLETE=TRUE
./xmlchange --id BATCH_COMMAND_FLAGS --val "$FLAGS"
./xmlchange JOB_WALLCLOCK_TIME=06:00:00
./xmlchange PRERUN_SCRIPT=$HARNESS/cases/t4_prerun.sh
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake

say "4. inputs and history must be identical to the 20-node case"
diff <(grep -vE '^\s*$' user_nl_elm) <(grep -vE '^\s*$' $BASE/e3sm_cases/$CASE20/user_nl_elm) \
  && echo "user_nl_elm identical" || echo "^^ DIFFERS -- stop and inspect"
./xmlquery RUNDIR,EXEROOT,BUILD_COMPLETE,NTASKS_LND,STOP_N,REST_N,RUN_STARTDATE --value | tail -1
./preview_run 2>&1 | grep -A2 'SUBMIT CMD'
echo
echo "NOT submitted."
