#!/bin/bash
# T4 -- 10 vs 20 node calibration, PRODUCTION build and PRODUCTION output.
#
# Everything T1/T1b/T1c used is unsuitable for this measurement and is
# deliberately undone: DEBUG=TRUE at -O0 is not the speed the production runs
# will see, the diagnostic SourceMods add log I/O per timestep, and the
# restricted hourly history is not the output volume that has to be written.
#
# The two layouts share ONE executable. E3SM's PE layout is a runtime property
# and NTASKS does not enter the build (guide 4.1), so the 10-node case clones
# the 20-node case with --keepexe. The binary therefore cannot account for a
# throughput or memory difference between layouts.
#
#   ./setup_t4_calibration.sh            # create both, build, do NOT submit
#   SKIP_BUILD=1 ./setup_t4_calibration.sh
#
# It never submits. Submission is a separate reviewed step.

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
PINNED=0be814f868
CLONE_FROM=$BASE/e3sm_cases/20260908_seus_4km_fut_a3ic_ssp370   # T1b: correct inputs
PROD=$BASE/e3sm_cases/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs

CASE20=20260908_seus_4km_fut_t4_n20
CASE10=20260908_seus_4km_fut_t4_n10
FLAGS='--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'

say() { printf '\n=== %s ===\n' "$*"; }

say "0. pinned reader source"
cd $SRC
F=components/elm/src/cpl/lnd_import_export.F90
git diff --quiet $PINNED HEAD -- $F && git diff --quiet -- $F \
  || { echo "$F differs from $PINNED; refusing" >&2; exit 1; }
echo "$F matches $PINNED (HEAD $(git rev-parse --short=10 HEAD))"

# ---------------------------------------------------------------- 20 nodes
say "1. create $CASE20 (2560 tasks / 20 nodes), production build"
[[ -d $BASE/e3sm_cases/$CASE20 ]] && { echo "exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $BASE/e3sm_cases/$CASE20 --clone $CLONE_FROM \
    --cime-output-root $OUTROOT
cd $BASE/e3sm_cases/$CASE20
./xmlchange RUNDIR=$OUTROOT/$CASE20/run,EXEROOT=$OUTROOT/$CASE20/bld

say "2. production build: DEBUG off, diagnostic SourceMods removed"
rm -f SourceMods/src.elm/lnd_import_export.F90
ls SourceMods/src.elm/ | grep -v README || echo "  SourceMods/src.elm: only README (correct)"
./xmlchange DEBUG=FALSE
for c in ATM LND ICE OCN CPL GLC ROF WAV ESP IAC; do
  ./xmlchange NTASKS_$c=2560,NTHRDS_$c=1 >/dev/null
done
./xmlchange MAX_MPITASKS_PER_NODE=128,MAX_TASKS_PER_NODE=128
./case.setup --reset
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
grep -n CPPDEFS cmake_macros/universal.cmake
echo "ffpe-trap present (expected, DEBUG unused): $(grep -c 'ffpe-trap' cmake_macros/gnu.cmake || true)"

say "3. production history and run interval"
python3 - "$PWD/user_nl_elm" "$PROD/user_nl_elm" <<'PYEOF'
import re, sys
mine, prod = sys.argv[1], sys.argv[2]
t = open(mine).read()
# drop the T1 restricted-output block
for k in ("hist_empty_htapes", "hist_fincl1"):
    t = re.sub(r'^\s*%s\s*=.*$\n?' % k, '', t, flags=re.M)
def setk(t, k, v):
    pat = re.compile(r'^\s*%s\s*=.*$' % re.escape(k), re.M)
    line = " %s = %s" % (k, v)
    return pat.sub(line, t) if pat.search(t) else t.rstrip() + "\n" + line + "\n"
for k, v in [("hist_nhtfrq", "0,0"), ("hist_mfilt", "12,12"),
             ("hist_dov2xy", ".true.,.false."), ("hist_avgflag_pertape", "'A','A'")]:
    t = setk(t, k, v)
# production second tape, copied verbatim
f2 = [l for l in open(prod) if l.strip().startswith("hist_fincl2")]
if not f2:
    sys.exit("production hist_fincl2 not found")
t = t.rstrip() + "\n" + f2[0].rstrip() + "\n"
open(mine, "w").write(t)
print("history set to production; hist_fincl2 copied verbatim")
PYEOF
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2024-01-01,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=nyears,STOP_N=2,REST_OPTION=nyears,REST_N=1,RESUBMIT=0
./xmlchange DOUT_S=FALSE
./xmlchange --id BATCH_COMMAND_FLAGS --val "$FLAGS"
./xmlchange JOB_WALLCLOCK_TIME=03:00:00
./xmlchange PRERUN_SCRIPT=$HARNESS/cases/t4_prerun.sh

say "4. build $CASE20"
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  cat > build_t4.sbatch <<EOF
#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p parallel
#SBATCH -q normal
#SBATCH -N 1 -n 1 -c 32
#SBATCH --mem=64g
#SBATCH --time=01:00:00
#SBATCH -J bld_t4
#SBATCH -o $BASE/e3sm_cases/$CASE20/build_t4.%j.out
cd $BASE/e3sm_cases/$CASE20 && ./case.build
EOF
  sbatch build_t4.sbatch
  echo "build submitted -- wait for it before creating $CASE10"
fi

# ---------------------------------------------------------------- 10 nodes
say "5. $CASE10 is created by setup_t4_n10.sh AFTER the build finishes"
cat <<EOF
  It clones $CASE20 with --keepexe so both layouts share one binary,
  then repoints RUNDIR, runs case.setup (a --keepexe clone has no .case.run),
  restores BATCH_COMMAND_FLAGS / JOB_WALLCLOCK_TIME / BUILD_COMPLETE and the
  CPL_BYPASS macro, and sets NTASKS=1280.
EOF
