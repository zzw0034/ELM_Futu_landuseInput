#!/bin/bash
# T1c -- the continuous control for T1b.
#
# T1b ran 2024-01-01 to 01-04 in two legs with a restart at 01-03. T1c runs the
# same three days from the same A3 initial condition without stopping. The pair
# is what turns "the restart resets the phase of two forcing variables" from an
# index observation into a number.
#
# T1b HYPOTHESISED that FSDS and PRECTmms are bumped forward one 3-hour record
# at a segment boundary, on the grounds that they trail the other five in
# continuous integration while the restart initialiser gives all seven the same
# pair. That hypothesis is why this case exists, and running it DISPROVED it:
# T1b and T1c are bit-identical, and the index comparison behind the hypothesis
# had aligned leg 1's last step against leg 2's first step, an hour apart. See
# docs/T1C_RESULTS.md. The header is left describing the hypothesis because
# that is what the case was built to test.
#
# --keepexe deliberately: the executable must not be a variable in a
# continuous-versus-segmented comparison. It also means RUNDIR arrives pointing
# at T1b's run directory (guide 14.3), which would overwrite the very outputs
# being compared against, so it is repointed before anything else and checked.
#
#   ./setup_t1c_continuous.sh

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
CASE=20260908_seus_4km_fut_a3ic_cont
CASEROOT=$BASE/e3sm_cases/$CASE
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
CLONE_FROM=$BASE/e3sm_cases/20260908_seus_4km_fut_a3ic_ssp370
T1B_RUN=$OUTROOT/20260908_seus_4km_fut_a3ic_ssp370/run

say() { printf '\n=== %s ===\n' "$*"; }

say "1. clone T1b WITH --keepexe (identical binary)"
[[ -d $CASEROOT ]] && { echo "$CASEROOT exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $CASEROOT --clone $CLONE_FROM \
    --cime-output-root $OUTROOT --keepexe
cd $CASEROOT

say "2. repoint RUNDIR immediately -- --keepexe aims it at T1b's run dir"
./xmlchange RUNDIR=$OUTROOT/$CASE/run
RD=$(./xmlquery RUNDIR --value)
EX=$(./xmlquery EXEROOT --value)
echo "RUNDIR  = $RD"
echo "EXEROOT = $EX"
[[ "$RD" == "$T1B_RUN" ]] && { echo "FATAL: RUNDIR still points at T1b" >&2; exit 1; }
[[ "$EX" == "$OUTROOT/20260908_seus_4km_fut_a3ic_ssp370/bld" ]] \
  || { echo "FATAL: EXEROOT is not T1b's build" >&2; exit 1; }
echo "exe md5: $(md5sum $EX/e3sm.exe | cut -d' ' -f1)   (T1b: 799bc60960aad9b10421e70d8bea6faa)"
mkdir -p "$RD"

say "2b. case.setup -- a --keepexe clone has no .case.run and no job definitions"
# create_clone --keepexe skips case.setup, so env_batch.xml has zero <job>
# entries and case.submit dies with "Do not know about batch job case.run".
# case.setup then re-renders the batch settings and strips -DCPL_BYPASS from
# cmake_macros (guide 4, 9), so both are put back afterwards. The macro does
# not affect THIS run -- BUILD_COMPLETE stays TRUE and T1b's exe is reused --
# but leaving it absent would silently produce a non-CPL_BYPASS binary if
# anyone ever rebuilds this case.
./case.setup
./xmlchange BUILD_COMPLETE=TRUE
./xmlchange --id BATCH_COMMAND_FLAGS --val '--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'
./xmlchange JOB_WALLCLOCK_TIME=02:00:00
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
./preview_namelists >/dev/null 2>&1 || true

say "3. three days, continuous, restart daily so the artifacts match T1b"
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2024-01-01,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=ndays,STOP_N=3,REST_OPTION=ndays,REST_N=1,RESUBMIT=0
./xmlchange BUILD_COMPLETE=TRUE
./xmlquery RUN_TYPE,RUN_STARTDATE,CONTINUE_RUN,STOP_OPTION,STOP_N,REST_N,RESUBMIT --value | tail -1

say "4. inputs must be byte-identical to T1b"
diff <(grep -vE '^\s*$' user_nl_elm) <(grep -vE '^\s*$' $CLONE_FROM/user_nl_elm.leg1_snapshot 2>/dev/null || grep -vE '^\s*$' $CLONE_FROM/user_nl_elm) \
  && echo "user_nl_elm identical to T1b" || echo "^^ DIFFERS -- inspect before submitting"

say "5. preview_run must show all four Slurm flags, then submit"
./preview_run 2>&1 | grep -A2 'SUBMIT CMD'
cp env_run.xml env_run.xml.bak_ok
./case.submit
