#!/bin/bash
# Create ONE production future case. Creates and verifies; never submits.
#
# Every check here exits non-zero on failure. T3's setup script printed
# "DIFFERS -- stop" and then carried on, which is worse than having no check at
# all: it leaves a reassuring line in the log while the case goes out wrong.
# These are 77-year jobs; a misconfigured one is discovered days later.
#
#   ./setup_production_case.sh <scenario>
#
# scenario is one of: ssp119 ssp245 ssp370 ssp585 ssp370_RF ssp370_DF ssp370_RH

set -euo pipefail

SC="${1:?usage: setup_production_case.sh <scenario>}"

BASE=/projects/hpcl-cli185/proj-shared/zw5
WS=/projects/hpcl-cli185/world-shared/e3sm/inputdata
OUTROOT=/scratch/hpcl-cli185/zw5/cime_output_dirs
SRC=$BASE/E3SM
PINNED=0be814f868
T4=20260908_seus_4km_fut_t4_n20
T4ROOT=$BASE/e3sm_cases/$T4
EXPECT_MD5=e8b487b04a27adfd8f683359dfd73df5
A3=$OUTROOT/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC/run/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC.elm.r.2024-01-01-00000.nc
A3_SHA=20e9c29b13b519ef6085b11167cf0e4eaa02e21d65ce8d55923ef6fbf16f12ad
LUD=$BASE/ELM_Futu_landuseInput/outputs/processed
FLAGS='--time $JOB_WALLCLOCK_TIME -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052'

# scenario -> landuse, met dir, co2, ndep
case "$SC" in
  ssp119)     LU=$LUD/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP1_RCP19_simyr2024-2100.nc; MET=ssp119; CO2=fco2_datm_ssp119_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp119_c260818.nc ;;
  ssp245)     LU=$LUD/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP2_RCP45_simyr2024-2100.nc; MET=ssp245; CO2=fco2_datm_ssp245_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp245_c240903.nc ;;
  ssp370)     LU=$LUD/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_simyr2024-2100.nc; MET=ssp370; CO2=fco2_datm_ssp370_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp370_c220614.nc ;;
  ssp585)     LU=$LUD/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP5_RCP85_simyr2024-2100.nc; MET=ssp585; CO2=fco2_datm_ssp585_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp585_c190103.nc ;;
  ssp370_RF)  LU=$LUD/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_RF_simyr2024-2100.nc; MET=ssp370; CO2=fco2_datm_ssp370_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp370_c220614.nc ;;
  ssp370_DF)  LU=$LUD/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_DF_simyr2024-2100.nc; MET=ssp370; CO2=fco2_datm_ssp370_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp370_c220614.nc ;;
  ssp370_RH)  LU=$LUD/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_RH_simyr2024-2100.nc; MET=ssp370; CO2=fco2_datm_ssp370_1765-2500_c260818.nc; ND=fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp370_c220614.nc ;;
  *) echo "unknown scenario '$SC'" >&2; exit 1 ;;
esac

CASE=20260908_seus_4km_fut_${SC}
CASEROOT=$BASE/e3sm_cases/$CASE
RUNDIR=$OUTROOT/$CASE/run
METDIR=$WS/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/$MET
CO2F=$WS/atm/datm7/CO2/$CO2
NDF=$WS/lnd/clm2/ndepdata/$ND

die() { echo "FATAL: $*" >&2; exit 1; }
say() { printf '\n=== %s ===\n' "$*"; }

say "0. inputs must exist before anything is created"
[[ -f $A3   ]] || die "A3 initial condition missing: $A3"
[[ -f $LU   ]] || die "landuse missing: $LU"
[[ -f $CO2F ]] || die "co2 missing: $CO2F"
[[ -f $NDF  ]] || die "ndep missing: $NDF"
[[ -d $METDIR ]] || die "met dir missing: $METDIR"
NMET=$(ls -1 $METDIR/*.nc 2>/dev/null | wc -l)
[[ "$NMET" -eq 7 ]] || die "met dir has $NMET files, expected 7"
GOTSHA=$(sha256sum $A3 | cut -d' ' -f1)
[[ "$GOTSHA" == "$A3_SHA" ]] || die "A3 sha256 $GOTSHA != $A3_SHA"
echo "A3 sha256 verified; landuse/co2/ndep present; met dir has 7 files"

say "1. pinned source, and T4's production exe"
git -C $SRC diff --quiet $PINNED HEAD -- components/elm/src/cpl/lnd_import_export.F90 \
  || die "reader source differs from $PINNED (committed)"
git -C $SRC diff --quiet -- components/elm/src/cpl/lnd_import_export.F90 \
  || die "reader source dirty in the working tree"
[[ -x $OUTROOT/$T4/bld/e3sm.exe ]] || die "T4 build missing"
GOT=$(md5sum $OUTROOT/$T4/bld/e3sm.exe | cut -d' ' -f1)
[[ "$GOT" == "$EXPECT_MD5" ]] || die "exe md5 $GOT != $EXPECT_MD5"
echo "source pinned; exe md5 $GOT"

say "2. clone T4 with --keepexe"
[[ -d $CASEROOT ]] && die "$CASEROOT already exists"
$SRC/cime/scripts/create_clone --case $CASEROOT --clone $T4ROOT \
    --cime-output-root $OUTROOT --keepexe
cd $CASEROOT

say "3. repoint RUNDIR before anything else"
./xmlchange RUNDIR=$RUNDIR
RD=$(./xmlquery RUNDIR --value); EX=$(./xmlquery EXEROOT --value)
[[ "$RD" == "$RUNDIR" ]] || die "RUNDIR is '$RD'"
[[ "$EX" == "$OUTROOT/$T4/bld" ]] || die "EXEROOT is '$EX', not T4's build"
mkdir -p "$RUNDIR"

say "4. case.setup, then restore everything it re-renders"
./case.setup
./xmlchange BUILD_COMPLETE=TRUE
./xmlchange --id BATCH_COMMAND_FLAGS --val "$FLAGS"
./xmlchange JOB_WALLCLOCK_TIME=04:00:00
grep -q 'DCPL_BYPASS' cmake_macros/universal.cmake \
  || echo 'string(APPEND CPPDEFS " -DCPL_BYPASS")' >> cmake_macros/universal.cmake
# PRERUN_SCRIPT is deliberately NOT set: T4 answered the memory question and the
# approved production config does not include a sampler. Use mem_probe.sh for a
# spot check instead if one is wanted.
./xmlchange PRERUN_SCRIPT=""

say "5. scenario inputs"
python3 - "$PWD/user_nl_elm" "$A3" "$LU" "$METDIR" "$CO2F" "$NDF" <<'PYEOF'
import re, sys
path, ic, lu, met, co2, nd = sys.argv[1:7]
t = open(path).read()
def setk(t, k, v):
    pat = re.compile(r'^\s*%s\s*=.*$' % re.escape(k), re.M)
    line = " %s = %s" % (k, v)
    return pat.sub(line, t) if pat.search(t) else t.rstrip() + "\n" + line + "\n"
for k, v in [("finidat", "'%s'" % ic), ("flanduse_timeseries", "'%s'" % lu),
             ("metdata_type", "'era5-daymet-fut'"), ("metdata_bypass", "'%s'" % met),
             ("co2_file", "'%s'" % co2), ("stream_fldfilename_ndep", "'%s'" % nd),
             ("stream_year_first_ndep", "1850"), ("stream_year_last_ndep", "2101")]:
    t = setk(t, k, v)
open(path, "w").write(t)
print("user_nl_elm updated")
PYEOF

say "6. seven segments of eleven years"
./xmlchange RUN_TYPE=startup,RUN_STARTDATE=2024-01-01,CONTINUE_RUN=FALSE
./xmlchange STOP_OPTION=nyears,STOP_N=11,REST_OPTION=nyears,REST_N=11,RESUBMIT=6
./xmlchange DOUT_S=FALSE

say "7. verification -- every check exits on failure"
read -r RT RS CR SO SN RO RN RSB DB NT MP DS <<<"$(./xmlquery RUN_TYPE,RUN_STARTDATE,CONTINUE_RUN,STOP_OPTION,STOP_N,REST_OPTION,REST_N,RESUBMIT,DEBUG,NTASKS_LND,MAX_MPITASKS_PER_NODE,DOUT_S --value | tail -1 | tr ',' ' ')"
for pair in "RUN_TYPE|$RT|startup" "RUN_STARTDATE|$RS|2024-01-01" "CONTINUE_RUN|$CR|FALSE" \
            "STOP_OPTION|$SO|nyears" "STOP_N|$SN|11" "REST_OPTION|$RO|nyears" "REST_N|$RN|11" \
            "RESUBMIT|$RSB|6" "DEBUG|$DB|FALSE" "NTASKS_LND|$NT|2560" \
            "MAX_MPITASKS_PER_NODE|$MP|128" "DOUT_S|$DS|FALSE"; do
  IFS='|' read -r n got want <<<"$pair"
  [[ "$got" == "$want" ]] || die "$n is '$got', expected '$want'"
done
echo "xml settings verified"

NSM=$(ls SourceMods/src.elm/ | grep -cv README || true)
[[ "$NSM" -eq 0 ]] || die "$NSM SourceMods override(s) present -- production must have none"
echo "SourceMods overrides: 0"

# lnd_in is the file that is actually read; user_nl_elm is only an input to it
./preview_namelists >/dev/null 2>&1
LNDIN=$RUNDIR/lnd_in
[[ -f $LNDIN ]] || die "lnd_in not generated"
grep -q "finidat = '$A3'"                  $LNDIN || die "lnd_in finidat wrong"
grep -q "flanduse_timeseries = '$LU'"      $LNDIN || die "lnd_in flanduse wrong"
grep -q "metdata_bypass = '$METDIR'"       $LNDIN || die "lnd_in metdata_bypass wrong"
grep -q "co2_file = '$CO2F'"               $LNDIN || die "lnd_in co2_file wrong"
grep -q "stream_fldfilename_ndep = '$NDF'" $LNDIN || die "lnd_in ndep wrong"
grep -q "metdata_type = 'era5-daymet-fut'" $LNDIN || die "lnd_in metdata_type wrong"
echo "lnd_in verified against the intended scenario inputs"

say "8. preview_run and sbatch --test-only"
./preview_run 2>&1 | grep -A2 'SUBMIT CMD'
sbatch --test-only --time 04:00:00 -p parallel -A hpcl-cli185 -q hpcl-cli185 \
  --mem=200g --constraint=BL --exclude=blc051,blc052 -N 20 -n 2560 -c 1 --wrap='true' 2>&1 | tail -1

cp env_run.xml env_run.xml.bak_ok
echo
echo "$CASE ready. NOT submitted."
