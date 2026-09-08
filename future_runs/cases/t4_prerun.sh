#!/bin/bash
# CIME PRERUN_SCRIPT for T4: start the in-allocation memory sampler detached.
# Must never fail the run, hence the trailing || true and the nohup detach.
H=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs
# CIME does not export RUNDIR into PRERUN_SCRIPT's environment, so ${RUNDIR}
# silently fell back to $PWD (the CASEROOT) on the first T4 run -- harmless,
# the samples were still written, just not where the plan said. Ask the case.
RD=$(./xmlquery RUNDIR --value 2>/dev/null || true)
[[ -d "$RD" ]] || RD="$PWD"
OUT="$RD/mem_samples.${SLURM_JOB_ID:-nojob}.txt"
nohup "$H/tools/mem_sampler.sh" "$OUT" 60 >/dev/null 2>&1 &
echo "T4 prerun: memory sampler detached -> $OUT"
exit 0
