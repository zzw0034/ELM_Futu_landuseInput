#!/bin/bash
# T1 -- 4 km future startup test, Default/ssp370, bounds-checking build.
#
# Verifies the code path only. finidat is the OLD 2024 restart from the
# 20260723 historical run, NOT the A3 initial condition; nothing produced here
# is a science result and none of it substitutes for handoff acceptance on the
# final initial condition.
#
# Run on Pathfinder from anywhere; every path is absolute.
#   ./setup_t1_ssp370.sh            # create, configure, build
#   SKIP_BUILD=1 ./setup_t1_ssp370.sh
#
# It stops at the build. Submission is a separate, reviewed step.

set -euo pipefail

BASE=/projects/hpcl-cli185/proj-shared/zw5
CASE=20260905_seus_4km_fut_t0_ssp370
CASEROOT=$BASE/e3sm_cases/$CASE
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
PINNED=0be814f868
CLONE_FROM=$BASE/e3sm_cases/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
REFCASE=$BASE/e3sm_cases/20260901_seus_halfdeg_transient   # post-fix env_mach_specific reference
HARNESS=$BASE/ELM_Futu_landuseInput/future_runs

NTASKS=1280          # 10 nodes x 128
PPN=128

say() { printf '\n=== %s ===\n' "$*"; }

say "0. the reader source must match the pinned commit"
# Guard the file, not HEAD. A parallel session commits docs to this same repo,
# which moves HEAD without touching any source we compile; refusing on that
# would be a false positive. What must hold is that the file we build is the
# file we pinned, in the index and in the working tree.
cd $SRC
F=components/elm/src/cpl/lnd_import_export.F90
if ! git diff --quiet $PINNED HEAD -- $F || ! git diff --quiet -- $F; then
  echo "$F differs from $PINNED (committed or working-tree). Refusing to build." >&2
  git --no-pager diff --stat $PINNED HEAD -- $F >&2 || true
  git --no-pager diff --stat -- $F >&2 || true
  exit 1
fi
echo "$F matches $PINNED (HEAD is $(git rev-parse --short=10 HEAD), which may differ -- that is fine)"

say "1. clone (no --keepexe: independent build)"
[[ -d $CASEROOT ]] && { echo "$CASEROOT exists; remove or rename it first" >&2; exit 1; }
$SRC/cime/scripts/create_clone \
    --case $CASEROOT --clone $CLONE_FROM --cime-output-root $OUTROOT

cd $CASEROOT

say "2. trap 14.1 -- env_mach_specific.xml is a snapshot of the source case's build day"
if ! diff -q env_mach_specific.xml $REFCASE/env_mach_specific.xml >/dev/null; then
  echo "differs from the post-fix reference; removing the redundant Lmod loads"
  diff env_mach_specific.xml $REFCASE/env_mach_specific.xml || true
  sed -i '/<command name="load">gcc\/12.4.0<\/command>/d;/<command name="load">openmpi\/5.0.5<\/command>/d' \
      env_mach_specific.xml
  diff -q env_mach_specific.xml $REFCASE/env_mach_specific.xml \
      && echo "now identical to the reference" \
      || { echo "STILL differs -- inspect before continuing" >&2; diff env_mach_specific.xml $REFCASE/env_mach_specific.xml || true; }
fi

say "3. PE layout: $NTASKS tasks / $PPN per node = $((NTASKS/PPN)) nodes"
for c in ATM LND ICE OCN CPL GLC ROF WAV ESP IAC; do
  ./xmlchange NTASKS_$c=$NTASKS,NTHRDS_$c=1 >/dev/null
done
./xmlchange MAX_MPITASKS_PER_NODE=$PPN,MAX_TASKS_PER_NODE=$PPN
./xmlchange RUNDIR=$OUTROOT/$CASE/run,EXEROOT=$OUTROOT/$CASE/bld

say "4. bounds-checking build (construction D)"
./xmlchange DEBUG=TRUE
# guide 18.1: -ffpe-trap=invalid fires inside mpi_init, long before any model code
sed -i 's/ -ffpe-trap=invalid,zero,overflow//' cmake_macros/gnu.cmake
grep -n 'FLAGS_DEBUG' cmake_macros/gnu.cmake

say "5. case.setup --reset  (wipes cmake_macros; -DCPL_BYPASS goes back after)"
./case.setup --reset
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
grep -n CPPDEFS cmake_macros/universal.cmake
# --reset re-renders gnu.cmake too
sed -i 's/ -ffpe-trap=invalid,zero,overflow//' cmake_macros/gnu.cmake
grep -c 'ffpe-trap' cmake_macros/gnu.cmake | xargs -I{} echo "ffpe-trap occurrences remaining: {}"

say "6. diagnostic SourceMods, generated from the pinned commit"
mkdir -p SourceMods/src.elm
git -C $SRC show $PINNED:components/elm/src/cpl/lnd_import_export.F90 > /tmp/lie_$PINNED.F90
python3 $HARNESS/sourcemods/make_diag_sourcemod.py \
    --src /tmp/lie_$PINNED.F90 \
    --out SourceMods/src.elm/lnd_import_export.F90 \
    --first-n 24 \
    --window 20240101-20240103
grep -c 'forcing diagnostic' SourceMods/src.elm/lnd_import_export.F90

say "7. run settings"
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2024-01-01,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=ndays,STOP_N=2,REST_OPTION=ndays,REST_N=1,RESUBMIT=0
./xmlchange DOUT_S=FALSE
./xmlchange --id BATCH_COMMAND_FLAGS --val '--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'
./xmlchange JOB_WALLCLOCK_TIME=02:00:00

say "8. user_nl_elm"
FUT=/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/ssp370
WS=/projects/hpcl-cli185/world-shared/e3sm/inputdata
cp user_nl_elm user_nl_elm.clone_orig
python3 - "$PWD/user_nl_elm" "$FUT" "$WS" <<'PYEOF'
import re, sys
path, fut, ws = sys.argv[1], sys.argv[2], sys.argv[3]
txt = open(path).read()

def setkey(txt, key, val):
    pat = re.compile(r'^\s*%s\s*=.*$' % re.escape(key), re.M)
    line = " %s = %s" % (key, val)
    return pat.sub(line, txt) if pat.search(txt) else txt.rstrip() + "\n" + line + "\n"

lu = ('/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/'
      'landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_simyr2024-2100.nc')
fi = ('/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/'
      '20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC/run/'
      '20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC.elm.r.2024-01-01-00000.nc')

for k, v in [
    ("finidat",                   "'%s'" % fi),
    ("flanduse_timeseries",       "'%s'" % lu),
    ("metdata_type",              "'era5-daymet-fut'"),
    ("metdata_bypass",            "'%s'" % fut),
    ("co2_file",                  "'%s/atm/datm7/CO2/fco2_datm_ssp370_1765-2500_c260818.nc'" % ws),
    # the clone inherits no explicit ndep filename and would silently fall back
    # to the compset default, which is an ssp245 file
    ("stream_fldfilename_ndep",   "'%s/lnd/clm2/ndepdata/fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp370_c220614.nc'" % ws),
    ("stream_year_first_ndep",    "1850"),
    ("stream_year_last_ndep",     "2101"),
    # bounded output: the default h0 field set at hourly frequency would be
    # ~90 GB for two model days
    ("hist_empty_htapes",         ".true."),
    # every name checked against an existing h0 header except HDM, which is
    # absent from the default tape but is carried in the production case's
    # hist_fincl2 and therefore a valid field
    ("hist_fincl1",               "'TBOT','PBOT','QBOT','FSDS','FLDS','WIND','RAIN','SNOW','PCO2','NDEP_TO_SMINN','HDM','GPP','TLAI','TOTVEGC'"),
    ("hist_nhtfrq",               "1"),
    ("hist_mfilt",                "48"),
    ("hist_dov2xy",               ".true."),
    ("hist_avgflag_pertape",      "'I'"),
]:
    txt = setkey(txt, k, v)

# drop the inherited second tape's field list, which belongs to hist_fincl2
txt = re.sub(r'^\s*hist_fincl2\s*=.*$', '', txt, flags=re.M)
open(path, "w").write(txt)
print("user_nl_elm updated")
PYEOF
grep -vE '^\s*$' user_nl_elm

say "9. build"
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  cat > build_t1.sbatch <<EOF
#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p parallel
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 32
#SBATCH --mem=64g
#SBATCH --time=01:00:00
#SBATCH -J bld_t1
#SBATCH -o $CASEROOT/build_t1.%j.out
cd $CASEROOT && ./case.build
EOF
  sbatch build_t1.sbatch
else
  echo "SKIP_BUILD=1 -- not building"
fi

say "done -- verify before submitting"
echo "  ./preview_run                                   # SUBMIT CMD must carry all four flags"
echo "  zgrep -l CPL_BYPASS $OUTROOT/$CASE/bld/e3sm.bldlog.*"
echo "  grep -E 'ndep|co2_file|metdata|flanduse|finidat' $OUTROOT/$CASE/run/lnd_in"
