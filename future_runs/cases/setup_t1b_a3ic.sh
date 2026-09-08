#!/bin/bash
# T1b -- short future startup on the A3 initial condition, plus a restart READ.
#
# T1 used the old 20260723 restart and only ever *wrote* restarts. Two gaps it
# left, both closed here:
#
#   * the initial condition. T1's finidat was explicitly labelled code-path
#     verification only. The seven production runs start from the A3 restart,
#     and an initial condition is only accepted once the model has actually
#     started from it.
#
#   * reading a restart back. The future restart-initialisation path -- the
#     third branch, tindex = (yr - startyear_met)*2920, taken because
#     yr >= 2024 > endyear_met_spinup = 2023 -- has never been executed at any
#     resolution. Every 0.5deg future run was RESUBMIT=0 and wrote restarts it
#     never read. Defect A lived in the two branches above this one, so its
#     verification says nothing about this branch either.
#
# Two legs, same case, own RUNDIR:
#   leg 1  startup from the A3 restart, 2 model days, REST_N=1 day
#   leg 2  CONTINUE_RUN from leg 1's day-2 restart, 1 more day
#
# Leg 2 is the point. The diagnostic window spans both so the index pair the
# restart path computes is recorded, not inferred.
#
#   ./setup_t1b_a3ic.sh              # create, configure, build, submit leg 1
#   SKIP_BUILD=1 ./setup_t1b_a3ic.sh

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
CASE=20260908_seus_4km_fut_a3ic_ssp370
CASEROOT=$BASE/e3sm_cases/$CASE
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
PINNED=0be814f868
CLONE_FROM=$BASE/e3sm_cases/20260905_seus_4km_fut_t0_ssp370
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs
PROD=$OUTROOT/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
A3IC=$PROD/run/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC.elm.r.2024-01-01-00000.nc

say() { printf '\n=== %s ===\n' "$*"; }

say "0. reader source still matches the pinned commit"
cd $SRC
F=components/elm/src/cpl/lnd_import_export.F90
git diff --quiet $PINNED HEAD -- $F && git diff --quiet -- $F \
  || { echo "$F differs from $PINNED; refusing" >&2; exit 1; }
echo "ok (HEAD $(git rev-parse --short=10 HEAD))"

say "1. the A3 initial condition must be the one that was accepted"
[[ -f $A3IC ]] || { echo "missing $A3IC" >&2; exit 1; }
ls -l --time-style=full-iso $A3IC
echo "sha256 (expect 20e9c29b13b519ef6085b11167cf0e4eaa02e21d65ce8d55923ef6fbf16f12ad):"
sha256sum $A3IC | cut -d' ' -f1

say "2. clone from T1, independent build and rundir"
[[ -d $CASEROOT ]] && { echo "$CASEROOT exists" >&2; exit 1; }
$SRC/cime/scripts/create_clone --case $CASEROOT --clone $CLONE_FROM --cime-output-root $OUTROOT
cd $CASEROOT
./xmlchange RUNDIR=$OUTROOT/$CASE/run,EXEROOT=$OUTROOT/$CASE/bld

say "3. DEBUG + reset, then re-apply both macro edits"
./xmlchange DEBUG=TRUE
./case.setup --reset
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
sed -i 's/ -ffpe-trap=invalid,zero,overflow//' cmake_macros/gnu.cmake
grep -n CPPDEFS cmake_macros/universal.cmake
echo "ffpe-trap remaining: $(grep -c 'ffpe-trap' cmake_macros/gnu.cmake || true)"

say "4. diagnostic window spans both legs"
mkdir -p SourceMods/src.elm
git -C $SRC show $PINNED:$F > /tmp/lie_$PINNED.F90
python3 $HARNESS/sourcemods/make_diag_sourcemod.py \
    --src /tmp/lie_$PINNED.F90 \
    --out SourceMods/src.elm/lnd_import_export.F90 \
    --first-n 24 \
    --window 20240101-20240105

say "5. leg 1: startup from the A3 restart, 2 days, restart every day"
python3 - "$PWD/user_nl_elm" "$A3IC" <<'PYEOF'
import re, sys
path, ic = sys.argv[1], sys.argv[2]
txt = open(path).read()
txt = re.sub(r"^\s*finidat\s*=.*$", " finidat = '%s'" % ic, txt, flags=re.M)
open(path, "w").write(txt)
print("finidat ->", ic.split('/')[-1])
PYEOF
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2024-01-01,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=ndays,STOP_N=2,REST_OPTION=ndays,REST_N=1,RESUBMIT=0
sed -i 's/^ hist_mfilt = .*/ hist_mfilt = 120/' user_nl_elm
grep -E 'finidat|flanduse|metdata_type|metdata_bypass|co2_file|stream_fldfilename_ndep|hist_mfilt' user_nl_elm \
  | sed 's|/projects/hpcl-cli185/||;s|/scratch/hpcl-cli185/||'

say "6. build, then submit leg 1"
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  cat > build_t1b.sbatch <<EOF
#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p parallel
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 32
#SBATCH --mem=64g
#SBATCH --time=01:00:00
#SBATCH -J bld_t1b
#SBATCH -o $CASEROOT/build_t1b.%j.out
cd $CASEROOT && ./case.build
EOF
  sbatch build_t1b.sbatch
fi

say "leg 2 (run AFTER leg 1 completes, do not submit blind)"
cat <<EOF
  cd $CASEROOT
  cp env_run.xml env_run.xml.bak_leg1
  ls \$(./xmlquery RUNDIR --value)/*.elm.r.*.nc     # confirm the day-2 restart exists
  ./xmlchange CONTINUE_RUN=TRUE,STOP_N=1
  ./case.submit
EOF
