# T4 方案 —— 10 / 20 节点标定（**待你确认，尚未提交**）

本地脚本已就位并已提交到仓库；**Pathfinder 上尚未创建任何 case，未提交任何作业。**

## 1. 生产构建

T1/T1b/T1c 的构建**不能用于本测量**，三处全部撤销：

| T1 系列 | T4 |
|---|---|
| `DEBUG=TRUE`（`-O0`） | **`DEBUG=FALSE`** |
| 诊断 SourceMods（逐步写日志） | **删除 `SourceMods/src.elm/lnd_import_export.F90`** |
| 受限逐时 history | **生产 history 设置**（见 §4） |

- 源码锁定 `0be814f868`（含 A `3cf28db19f` + B `fc2a4f2be1`）；建前脚本校验
  `lnd_import_export.F90` 与该提交逐字节相同，不符即拒建。
- 建成后记录 `bld/GIT_LOG`、`GIT_DIFF`、`GIT_STATUS`、`SourceMods.tar.gz`
  与 `md5sum e3sm.exe`，与 T1 系列同样口径。
- `case.setup --reset` 之后补回 `-DCPL_BYPASS`，并用
  `zgrep -l CPL_BYPASS $EXEROOT/e3sm.bldlog.*` 验证。

**两个布局共用同一个二进制**：E3SM 的 PE 布局是运行期属性，`NTASKS` 不进构建
（指南 §4.1），所以 10 节点 case 用 `create_clone --keepexe` 从 20 节点 case
克隆。**二进制因此不可能解释两个布局之间的差异。**

## 2. 两个布局

| | A | B |
|---|---|---|
| 节点 | **20** | **10** |
| `NTASKS_*`（全部组件） | **2560** | **1280** |
| `MAX_MPITASKS_PER_NODE` | 128 | 128 |
| `NTHRDS_*` | 1 | 1 |
| `--mem` | **200g**（候选值，本次要验证的对象） | 200g |
| walltime | 03:00:00 | 06:00:00 |
| CASEROOT | `…/e3sm_cases/20260908_seus_4km_fut_t4_n20` | `…_t4_n10` |
| RUNDIR / EXEROOT | `/scratch/…/cime_output_dirs/<case>/run` / `…_t4_n20/bld` | `…_t4_n10/run` / **共用 `…_t4_n20/bld`** |

Slurm 身份两边相同：

```
-p parallel  -A hpcl-cli185  -q hpcl-cli185  --mem=200g  --constraint=BL  --exclude=blc051,blc052
```

**节点排除项已于 2026-09-08 03:45 重新核验**：BL 共 140 台 = 67 alloc +
**8 down\*** + 65 idle。`blc045–052` 全部 `down*` "Not responding"，
其中就包含 blc051/052。所以 `--exclude` 目前是冗余的（Slurm 不调度 down 节点），
**保留作为它们恢复后的防护**。65 台 idle 且可分配内存 ≥200g，两布局共 30 节点
供给充足。

## 3. 共同模拟区间与初始场

两边完全相同，只有 `NTASKS` 不同：

- `finidat` = **A3 的 2024-01-01 初始场**
  （sha256 `20e9c29b13b519ef6085b11167cf0e4eaa02e21d65ce8d55923ef6fbf16f12ad`，已验收）
- 输入 = **SSP370 全套**（气象 / CO2 / Ndep / landuse，与 T1b/T1c 逐行相同，
  脚本用 `diff` 强制核对）
- `RUN_TYPE=startup`、`RUN_STARTDATE=2024-01-01`、`CONTINUE_RUN=FALSE`
- `STOP_OPTION=nyears`、**`STOP_N=2`**（2024-01-01 → 2026-01-01）
- `REST_OPTION=nyears`、`REST_N=1`、`RESUBMIT=0`

**为什么是 2 年而不是 1 年或 3 年**：1 年里初始化占比过大——future 配置要预载
227,760 条气象记录，是历史配置的 1.77 倍——指南 §7 明确警告不要用极短测试外推。
2 年给出一段干净的内部窗口测稳定速率，同时覆盖 **24 次月度 history 写出、
2 个 h0/h1 文件关闭、2 次 restart 写出**，满足"至少覆盖一次正常 history 写出"。
3 年只是把同样的信息买贵一倍。

## 4. history / restart 设置（生产口径）

```
hist_nhtfrq        = 0,0            月均
hist_mfilt         = 12,12          12 条/文件
hist_dov2xy        = .true.,.false. h0 二维、h1 一维
hist_avgflag_pertape = 'A','A'
hist_fincl2        = 从生产 case 逐字复制
```

T1 的 `hist_empty_htapes` / `hist_fincl1` 被删除。

**存储**：按实测 18.82 GB/模式年（h0 11.36 + h1 7.46），
2 年 × 2 布局 ≈ **75 GB**，加 4 套 restart ≈ 55 GB，合计 **约 130 GB**。

## 5. 内存采样 —— 在 allocation 内部，持续记录

`tools/mem_sampler.sh`，由 CIME 的 `PRERUN_SCRIPT`（`cases/t4_prerun.sh`）
以 `nohup … &` 分离启动，运行在批处理节点上、作业自己的 allocation 内，
每 **60 秒**通过 `srun --jobid=$SLURM_JOB_ID --overlap -N <nodes> --ntasks-per-node=1`
采一次，写到 `$RUNDIR/mem_samples.<jobid>.txt`。

每节点每次记录：

```
memory.current    memory.stat 的 anon / file / slab    memory.peak
memory.max（limit）    memory.events 的 oom / oom_kill
/proc/meminfo 的 used / cached
```

**明确不采用的两种做法**：

- **不用 `sacct MaxRSS`**。Pathfinder 是 `JobAcctGatherType=jobacct_gather/cgroup`
  （Slurm 24.11.7，已核实），MaxRSS 取自 cgroup、**含可回收页缓存**；
  按它定 `--mem=400g` 正是那次白排 12 小时队的来源。
- **不在登录节点长跑 `WATCH` 循环**。采样器随作业启动、随作业结束。

判据：`anon` 是真实需求，`file` 是机会性的、在更小 limit 下会自行收缩，
**非零 `oom_kill` 是 `--mem` 过小的唯一硬证据**。

## 6. 计时口径（三段分开报）

- **初始化读入**：`lnd.log` 首行时间戳 → 第一个 `Beginning timestep` 的墙钟差
- **稳定积分速度**：`lnd.log` 的 `Beginning timestep` 模式日期做**内部窗口**
  两点取样，跳过初始化与最后一次输出；辅以 `$RUNDIR/timing/checkpoints/*_stats`
  的 GPTL 快照（指南 §7）
- **输出时间**：月度写出与 restart 写出前后的时间戳差
- **node-hours / 模式年** = 节点数 × 总墙钟 ÷ 2

另：起跑 5 分钟后各跑一次 `check_node_freq.sh`，降频节点会同时污染速度和
node-hours（指南 §16）。

## 7. `sbatch --test-only` 结果（2026-09-08 03:50，已实跑）

```
20 节点: sbatch --test-only --time 03:00:00 -p parallel -A hpcl-cli185 \
         -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052 \
         -N 20 -n 2560 -c 1
  → Job 516281 to start at 2026-09-08T10:24:03 using 2560 processors
    on nodes blc[081-100] in partition parallel

10 节点: 同上，--time 06:00:00 -N 10 -n 1280 -c 1
  → Job 516282 to start at 2026-09-08T10:24:03 using 1280 processors
    on nodes blc[129-138] in partition parallel
```

两者均通过 QoS、内存档位与 `BL` 特征约束。**注意**："to start at 10:24" 是
Slurm 当时的排程估计，不是保证；实际起跑时间以提交后为准。

首次尝试因缺 `-n` 被拒（`Task count undefined`），与 AGENTS.md 记的
"缺 `-q`/`-n`/`-c`/`--mem` 会被拒" 一致；CIME 自己生成的作业脚本在
`#SBATCH` 里带这些，`BATCH_COMMAND_FLAGS` 不需要重复。

## 8. 预计提交命令

`preview_run` 的 `SUBMIT CMD` 应为（两边只有 walltime 不同）：

```
sbatch --time 03:00:00 -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g \
  --constraint=BL --exclude=blc051,blc052 \
  /projects/hpcl-cli185/proj-shared/zw5/e3sm_cases/20260908_seus_4km_fut_t4_n20/.case.run --resubmit
```

执行顺序：

```
1  cases/setup_t4_calibration.sh     建 n20、删 SourceMods、DEBUG=FALSE、生产 history、提交构建作业
2  等构建完成，核对 CPL_BYPASS 与 exe md5
3  cases/setup_t4_n10.sh             --keepexe 克隆出 n10、改 RUNDIR、case.setup、恢复设置
4  两边各 ./case.submit
```

**脚本本身不提交任何模型作业**（只提交构建作业），第 4 步是独立动作。

## 9. 布局选择判据（跑完之后）

1. **峰值 `anon` 余量**对 200g——`anon` 而不是 `memory.current`，
   且 `oom_kill` 必须为 0
2. **稳定吞吐**（模式年/小时）
3. **node-hours / 模式年**

若 10 节点的 node-hours 不劣于 20 节点，选 10 节点：并发度翻倍，
七个正式 run 的总时长由此决定。
