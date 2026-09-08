#!/bin/bash
# Continuous per-node memory sampling from INSIDE the job's own allocation.
#
# Launched detached by PRERUN_SCRIPT so it lives for the run and dies with it.
# Two things it deliberately is not:
#
#   * not sacct MaxRSS. Pathfinder runs JobAcctGatherType=jobacct_gather/cgroup
#     (Slurm 24.11.7, verified), so MaxRSS is the cgroup total and includes
#     reclaimable page cache. On a Lustre-heavy run that is most of the number,
#     and sizing --mem from it is what bought the 4km run a 12-hour queue for
#     memory it did not need.
#   * not a WATCH loop on the login node. It runs on the batch node, inside the
#     allocation, and needs no external process to survive.
#
# What it records per node, per sample: memory.current, and from memory.stat
# the anon / file / slab split, plus memory.peak and memory.events oom and
# oom_kill. anon is the requirement; file is opportunistic and shrinks under a
# smaller limit; a non-zero oom_kill is the only hard proof a --mem was too
# small.
#
# Usage (from PRERUN_SCRIPT):  mem_sampler.sh <outfile> [interval_sec]

set -uo pipefail
OUT="${1:?usage: mem_sampler.sh <outfile> [interval]}"
INT="${2:-60}"
JOB="${SLURM_JOB_ID:?must run inside a job}"
N="${SLURM_JOB_NUM_NODES:-1}"

{
  echo "# job $JOB  nodes $N  interval ${INT}s  started $(date -Is)"
  echo "# node epoch cur_G anon_G file_G slab_G peak_G limit_G oom oom_kill node_used_G node_cached_G"
} >> "$OUT"

while squeue -h -j "$JOB" -o '%T' 2>/dev/null | grep -q RUNNING; do
  srun --jobid="$JOB" --overlap -N "$N" --ntasks-per-node=1 \
    bash -c '
      CG=""
      for c in /sys/fs/cgroup/system.slice/slurmstepd.scope/job_'"$JOB"' \
               /sys/fs/cgroup/slurm/uid_$(id -u)/job_'"$JOB"'; do
        [[ -d "$c" ]] && CG="$c" && break
      done
      g() { awk -v k="$1" "\$1==k {printf \"%.2f\", \$2/1073741824}" "$CG/memory.stat" 2>/dev/null || echo NA; }
      f() { [[ -f "$CG/$1" ]] && awk "{printf \"%.2f\", \$1/1073741824}" "$CG/$1" 2>/dev/null || echo NA; }
      e() { [[ -f "$CG/memory.events" ]] && awk -v k="$1" "\$1==k{print \$2}" "$CG/memory.events" || echo NA; }
      MU=$(awk "/MemTotal/{t=\$2} /MemAvailable/{a=\$2} END{printf \"%.1f\",(t-a)/1048576}" /proc/meminfo)
      MC=$(awk "/^Cached/{printf \"%.1f\", \$2/1048576}" /proc/meminfo)
      printf "%s %s %s %s %s %s %s %s %s %s %s %s\n" \
        "$(hostname -s)" "$(date +%s)" "$(f memory.current)" "$(g anon)" "$(g file)" \
        "$(g slab)" "$(f memory.peak)" "$(f memory.max)" "$(e oom)" "$(e oom_kill)" "$MU" "$MC"
    ' 2>/dev/null | sort >> "$OUT"
  sleep "$INT"
done
echo "# ended $(date -Is)" >> "$OUT"
