#!/bin/bash
# T3 run B -- restart consistency at the production 20-node layout.
#
# A is T4, already run continuously 2024-01-01 -> 2026-01-01. A is READ ONLY
# here: every restart dependency is COPIED out of A's run directory, never
# symlinked and never written to. B restarting through a symlink into A's
# directory would put A's baseline one accident away from being modified, and A
# is the thing B is being compared against.
#
# Restarting from another case's checkpoint needs four things right, each of
# which fails differently (see the borrowing-a-restart notes):
#
#  1. rpointer and the CIME submit check want B's OWN case name.
#  2. elm.r stores the names of its companions internally. locfnhr names the
#     rh0/rh1 pair and locfnh names the history files still being appended to --
#     here the 2024-02-01 h0/h1, which span Feb 2024 to Jan 2025, so a restart
#     at 2025-01-01 reopens them to add January. Those must be present under
#     A's case name or the run dies in GETFIL.
#  3. cpl.r stores the case name in seq_infodata_case_name and the driver
#     checks it. Renaming the file is not enough; the field is rewritten.
#  4. env_run.xml has been seen truncated by case.submit, so it is backed up.
#
# The executable is A's, unmodified: create_clone --keepexe, md5 asserted.
#
#   ./setup_t3_restart.sh          # create, stage, verify. Does NOT submit.

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs

A=20260908_seus_4km_fut_t4_n20
B=20260908_seus_4km_fut_t3_restart
ARUN=$OUTROOT/$A/run
ABLD=$OUTROOT/$A/bld
BROOT=$BASE/e3sm_cases/$B
BRUN=$OUTROOT/$B/run
EXPECT_MD5=e8b487b04a27adfd8f683359dfd73df5
FLAGS='--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'

say() { printf '\n=== %s ===\n' "$*"; }

say "0. A must be intact and its exe the expected one"
[[ -f $ARUN/$A.elm.r.2025-01-01-00000.nc ]] || { echo "A's 2025 restart missing" >&2; exit 1; }
GOT=$(md5sum $ABLD/e3sm.exe | cut -d' ' -f1)
[[ "$GOT" == "$EXPECT_MD5" ]] || { echo "A exe md5 $GOT != $EXPECT_MD5" >&2; exit 1; }
echo "A exe md5 $GOT  (as expected)"

say "1. clone A with --keepexe"
[[ -d $BROOT ]] && { echo "$BROOT exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $BROOT --clone $BASE/e3sm_cases/$A \
    --cime-output-root $OUTROOT --keepexe
cd $BROOT

say "2. repoint RUNDIR first (--keepexe aims it at A's run dir)"
./xmlchange RUNDIR=$BRUN
RD=$(./xmlquery RUNDIR --value); EX=$(./xmlquery EXEROOT --value)
[[ "$RD" == "$ARUN" ]] && { echo "FATAL: RUNDIR still A's run dir" >&2; exit 1; }
[[ "$EX" == "$ABLD" ]] || { echo "FATAL: EXEROOT is not A's build" >&2; exit 1; }
mkdir -p "$BRUN"
echo "RUNDIR  = $RD"
echo "EXEROOT = $EX"

say "3. case.setup (a --keepexe clone has no .case.run), then restore"
./case.setup
./xmlchange BUILD_COMPLETE=TRUE
./xmlchange --id BATCH_COMMAND_FLAGS --val "$FLAGS"
./xmlchange JOB_WALLCLOCK_TIME=01:00:00
./xmlchange PRERUN_SCRIPT=$HARNESS/cases/t4_prerun.sh
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake

say "4. stage the restart dependencies -- COPIES out of A, A untouched"
cp -n $ARUN/$A.elm.r.2025-01-01-00000.nc   $BRUN/$B.elm.r.2025-01-01-00000.nc
cp -n $ARUN/$A.cpl.r.2025-01-01-00000.nc   $BRUN/$B.cpl.r.2025-01-01-00000.nc
# named by A because elm.r's locfnhr points at them
cp -n $ARUN/$A.elm.rh0.2025-01-01-00000.nc $BRUN/
cp -n $ARUN/$A.elm.rh1.2025-01-01-00000.nc $BRUN/
# named by A because elm.r's locfnh points at them; still open for appending
cp -n $ARUN/$A.elm.h0.2024-02-01-00000.nc  $BRUN/
cp -n $ARUN/$A.elm.h1.2024-02-01-00000.nc  $BRUN/
ls -l $BRUN | awk '{printf "%14s  %s\n", $5, $9}'

say "5. rewrite the case name inside B's cpl.r"
python3 $HARNESS/tools/rewrite_cplr_casename.py $BRUN/$B.cpl.r.2025-01-01-00000.nc $B

say "6. rpointer files name B's restart"
printf './%s.elm.r.2025-01-01-00000.nc\n' $B > $BRUN/rpointer.lnd
printf '%s.cpl.r.2025-01-01-00000.nc\n'   $B > $BRUN/rpointer.drv
cat $BRUN/rpointer.lnd $BRUN/rpointer.drv

say "7. one model year, continue from the checkpoint"
cp env_run.xml env_run.xml.bak_ok
./xmlchange CONTINUE_RUN=TRUE
./xmlchange STOP_OPTION=nyears,STOP_N=1,REST_OPTION=nyears,REST_N=1,RESUBMIT=0
./xmlquery CONTINUE_RUN,STOP_OPTION,STOP_N,REST_OPTION,REST_N,RESUBMIT,DEBUG,NTASKS_LND,MAX_MPITASKS_PER_NODE --value | tail -1

say "8. inputs must be byte-identical to A"
diff <(grep -vE '^\s*$' user_nl_elm) <(grep -vE '^\s*$' $BASE/e3sm_cases/$A/user_nl_elm) \
  && echo "user_nl_elm identical to A" || echo "^^ DIFFERS -- stop"
echo -n "SourceMods overrides: "; ls SourceMods/src.elm/ | grep -v README | wc -l

say "9. preview_run"
./preview_run 2>&1 | grep -A2 'SUBMIT CMD'
echo
echo "NOT submitted. Run sbatch --test-only and then ./case.submit."
