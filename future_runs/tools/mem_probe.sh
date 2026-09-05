#!/bin/bash
# Sample per-node memory inside a running Slurm allocation, with the
# categories separated instead of collapsed into one number.
#
# WHY THIS EXISTS
# ---------------
# The 4km SEUS run was given --mem=400g on the strength of `sacct MaxRSS =
# 345 GB`, then queued 12 hours for nodes it did not need. On Pathfinder
# `JobAcctGatherType = jobacct_gather/cgroup` (verified 2026-09-05, Slurm
# 24.11.7), so MaxRSS is derived from the job's cgroup and therefore includes
# reclaimable page cache -- on a Lustre-heavy run that is most of the number.
#
# But `memory.current` is not "process memory" either. Per the cgroup v2
# documentation it is the total charged to the cgroup: anonymous pages, page
# cache, kernel slab and more. The only way to say what the job actually
# needs is to read the breakdown:
#
#   memory.stat  anon        anonymous -- the part that cannot be reclaimed
#                file        page cache -- reclaimable under pressure
#                slab,sock,kernel_stack, ...
#   memory.peak  high-water mark of memory.current (kernel >= 5.19)
#   memory.events  low/high/max/oom/oom_kill -- non-zero oom* means the limit
#                  was actually reached, which is the only hard evidence that
#                  a --mem value was too small
#
# Sizing rule of thumb this supports: `anon` + headroom is the requirement;
# `file` is opportunistic and will shrink under a smaller limit. A --mem that
# only squeezes `file` costs I/O performance, not correctness; a --mem below
# peak `anon` gets the job OOM-killed. Both need to be measured, not inferred.
#
# USAGE (on Pathfinder)
#   ./mem_probe.sh <jobid>          # one snapshot across every node
#   WATCH=300 ./mem_probe.sh <jobid>  # repeat every 300 s until the job ends
#
# USAGE (from the Mac)
#   scp mem_probe.sh pathfinder:/tmp/ && ssh pathfinder "/tmp/mem_probe.sh <jobid>"
#   Copy then execute -- do not pipe it over stdin, srun and ssh fight for it
#   (same trap documented in check_node_freq.sh).
#
# Exit status: 0 sampled, 2 could not determine.

set -uo pipefail

JOBID="${1:-}"
WATCH="${WATCH:-0}"

if [[ -z "$JOBID" ]]; then
  echo "usage: $0 <jobid>   (explicit jobid required; see check_node_freq.sh for why)" >&2
  exit 2
fi

STATE=$(squeue -h -j "$JOBID" -o '%T' 2>/dev/null)
if [[ "$STATE" != "RUNNING" ]]; then
  echo "ERROR: job $JOBID is not RUNNING (state='${STATE:-not found}')" >&2
  exit 2
fi

probe_once() {
  srun --jobid="$JOBID" --overlap -N "$(squeue -h -j "$JOBID" -o '%D')" --ntasks-per-node=1 \
    bash -c '
      CG=""
      for c in /sys/fs/cgroup/system.slice/slurmstepd.scope/job_'"$JOBID"' \
               /sys/fs/cgroup/slurm/uid_$(id -u)/job_'"$JOBID"'; do
        [[ -d "$c" ]] && CG="$c" && break
      done
      read_stat() { [[ -f "$CG/memory.stat" ]] && awk -v k="$1" "\$1==k {print \$2}" "$CG/memory.stat" || echo NA; }
      to_g() { [[ "$1" == "NA" || -z "$1" ]] && echo "NA" || awk -v b="$1" "BEGIN{printf \"%.1f\", b/1073741824}"; }

      CUR=$( [[ -f "$CG/memory.current" ]] && cat "$CG/memory.current" || echo NA )
      PEAK=$( [[ -f "$CG/memory.peak" ]] && cat "$CG/memory.peak" || echo NA )
      MAXL=$( [[ -f "$CG/memory.max" ]] && cat "$CG/memory.max" || echo NA )
      ANON=$(read_stat anon); FILE=$(read_stat file); SLAB=$(read_stat slab)
      OOM=$( [[ -f "$CG/memory.events" ]] && awk "\$1==\"oom\"{print \$2}" "$CG/memory.events" || echo NA )
      OOMK=$( [[ -f "$CG/memory.events" ]] && awk "\$1==\"oom_kill\"{print \$2}" "$CG/memory.events" || echo NA )
      MT=$(awk "/MemTotal/{printf \"%.0f\", \$2/1048576}" /proc/meminfo)
      MA=$(awk "/MemAvailable/{printf \"%.0f\", \$2/1048576}" /proc/meminfo)
      CA=$(awk "/^Cached/{printf \"%.0f\", \$2/1048576}" /proc/meminfo)

      printf "%-10s cg=%-6s anon=%-7s file=%-7s slab=%-6s peak=%-7s limit=%-8s oom=%s/%s | node total=%sG avail=%sG cached=%sG\n" \
        "$(hostname -s)" "$(to_g $CUR)" "$(to_g $ANON)" "$(to_g $FILE)" "$(to_g $SLAB)" \
        "$(to_g $PEAK)" "$( [[ "$MAXL" == "max" ]] && echo unlimited || to_g $MAXL )" \
        "${OOM:-0}" "${OOMK:-0}" "$MT" "$MA" "$CA"
    ' 2>/dev/null | sort
}

echo "# job $JOBID  $(date -Is)"
echo "# cg = memory.current (anon+file+slab+...), NOT process memory"
echo "# anon = non-reclaimable; file = reclaimable page cache; oom/oom_kill non-zero = limit actually hit"
probe_once

if [[ "$WATCH" -gt 0 ]]; then
  while squeue -h -j "$JOBID" -o '%T' 2>/dev/null | grep -q RUNNING; do
    sleep "$WATCH"
    echo
    echo "# job $JOBID  $(date -Is)"
    probe_once
  done
fi
