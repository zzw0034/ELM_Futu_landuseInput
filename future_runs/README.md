# future_runs — 4 km SEUS future (2024–2100) 运行侧测试与标定

remote root: `/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput`

本目录是 4 km future 七情景正式运行**之前**的测试工装。输入数据本身
（气象/landuse/CO2/Ndep）不在这里生成，见同仓库 `future_climate/` 与
`outputs/processed/`。

## 锁定基线

| 项 | 值 |
|---|---|
| E3SM 提交 | `0be814f868`（含缺陷 A `3cf28db19f` + 缺陷 B `fc2a4f2be1`） |
| 分支 | `zw5/seus-halfdeg-metdata-type` |
| 仓库 | `/projects/hpcl-cli185/proj-shared/zw5/E3SM` |

不追逐移动中的 HEAD。诊断补丁不进共享树，只进各 case 的 `SourceMods/src.elm/`，
由 `sourcemods/make_diag_sourcemod.py` 从上述提交生成，版本单独记录。

## 与并行会话共存的约定

各自独立的 `CASEROOT`、`RUNDIR`、`EXEROOT`、`SourceMods`；共享源码树在任一方
编译期间保持不变。只有双方需要改同一文件、或需要切换共享源码版本时才须协调。

## 目录

```
tools/cmp_nc2.py             两文件比较：DATA / TEXT / META 三类分开，记录维度可对齐
tools/mem_probe.sh           分类内存采样（anon / file / slab / peak / oom），不混为一个数
sourcemods/make_diag_sourcemod.py   生成 forcing 诊断 SourceMods，锚点不匹配即拒写
jobs/                        Slurm 作业脚本
docs/                        测试记录
```

## 已确立的事实（截至 2026-09-05）

**源码推导**（`lnd_import_export.F90` @ `0be814f868`）

- `use_daymet_fut`：`startyear_met=2023`、`endyear_met_spinup=2023`、
  `endyear_met_trans=2100` → `nyears_spinup=1`、`timelen_spinup=2920`、
  `timelen=227760`（实测确认：future 文件 `DTIME=227760`）。
- `mystart` 因 `nyears_spinup=1` 收敛到 1850，对齐偏移为 0；`yr ≥ 2024` 一律走
  线性分支 `(yr-startyear_met)*2920`。**结论限定为**：2024–2100 年内、零点启动
  的初始化索引在界内。不可扩大为任意日期安全。
- 从 2101-01-01 初始化得 `(227760, 227761)`，`t2` 越界；初始化路径不经过
  per-timestep 守卫。这是与"连续积分跨终点"不同的第三条路径。
- `caldaym = (/1,32,60,91,121,152,182,213,244,274,305,335,366/)`，
  `tindex += (caldaym(mon)+day-2)*nint(24/timeres)`。
- `atm_input` 为 `integer*2`，形状 `(met_nvars, begg:endg, 1, timelen)`，
  `met_nvars=7`（14 仅用于 `metdata_type(1:3)=='cpl'`）。
- 递增相位分两类：`v=4 (FSDS)`、`v=5 (PRECTmms)` 走记录边界触发，其余五个走
  记录中点触发。4 km `ATM_NCPL=24` → `npf=3`；0.5° `ATM_NCPL=48` → `npf=6`，
  两者相位不同，0.5° 的末端行为不能外推到 4 km。

**实测确认**

- 七个 0.5° future run 全部跑完 77 年到 2101-01-01（jobs 504890、506383–85、
  506394–96），退出码 0:0。**但它们用的是 B 修复之前的 exe，末端气象正确性待核查。**
- 0.5° future 衔接（另一会话，jobs 511773/511775）：`TINDEX_INIT yr=2024 t1=2920
  t2=2921 timelen=227760`，与推导一致；该诊断只覆盖 `v=1`。
- 测试 exe（`20260904_dbg_halfdeg_2023end/bld`，md5 `9dfcf9dfd3ef4c42fae0f32d520ade4f`）
  的编译期 `GIT_LOG` HEAD = `f7056dbe75` = `fc2a4f2be1` 的父提交，编译期
  `GIT_DIFF` 的 ± 行与 `fc2a4f2be1` 逐行相同，`SourceMods.tar.gz` 为空 →
  **源码等价于 B**。
- 生产 exe（md5 `cb75cc200c3fb15fe460d19b2d20a71a`）编译期 HEAD = `6a3d7b0e2b`，
  工作树 tracked 部分干净（2711 字节的 `GIT_DIFF` 全是 submodule 遍历噪声）
  → **不含 A、不含 B**。
- Pathfinder Slurm 24.11.7，`JobAcctGatherType = jobacct_gather/cgroup`，
  `ProctrackType = proctrack/cgroup`，`AcctGatherProfileType = (null)` →
  **`sacct MaxRSS` 源自 cgroup，含可回收页缓存，不能当内存需求**；也没有
  profile 时间序列可用，需自行采样（`tools/mem_probe.sh`）。

**存储实测**（4 km 历史 run 分类统计）

| 类别 | 单位量 |
|---|---|
| `elm.h0` | 11.36 GB / 模式年 |
| `elm.h1` | 7.46 GB / 模式年 |
| `elm.r` | 13.83 GB / 套 |
| `rh0`+`rh1`+`cpl.r` | 可忽略 |

future 单 run（77 年，`REST_N=11` 保留 7 套）≈ **1.50 TiB**；七个 ≈ **10.5 TiB**。
`/scratch` 当前可用 15 TiB（该数字已扣除现有输出），余量约 30%。scratch 作为
运行目录，向项目盘归档，**不把 scratch 当备份**。

## 待验证（不得当成已知）

- 4 km future 启动的七变量索引、相位与解码值。
- 4 km future 末端（2100-12-29 → 2101-01-01）的实际驱动、守卫是否触发、
  是否存在 `yr=2101` 的 import。
- 4 km future 的 restart 续接一致性。
- 4 km future 的实际内存需求（`anon` 与 `file` 分开）与 10/20 节点速度。
- 关闭三个 `check_*_consistency` 后的人工一致性核查证据。
