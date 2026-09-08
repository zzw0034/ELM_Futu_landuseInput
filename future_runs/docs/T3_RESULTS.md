# T3 结果 —— 20 节点生产布局下的 restart 一致性

| | A（连续基准） | B（重启） |
|---|---|---|
| case | `20260908_seus_4km_fut_t4_n20`（T4，未修改） | `20260908_seus_4km_fut_t3_restart` |
| 区间 | 2024-01-01 → 2026-01-01 连续 | **2025-01-01 → 2026-01-01，`CONTINUE_RUN=TRUE`** |
| job | 516284 | **516288** |
| exe | md5 `e8b487b04a27adfd8f683359dfd73df5` | **同一个**（`--keepexe`，md5 已断言） |
| 布局 | 20 节点 / 2560 tasks / 200g | 相同 |
| 构建 / 输出 | `DEBUG=FALSE`、0 SourceMods、生产 history、netcdf | 相同 |
| `user_nl_elm` | — | 与 A **逐行相同**（脚本 `diff` 强制） |

**A 全程只读**：所有 restart 依赖都是**复制**出 A 的运行目录，没有软链、没有写入。

## 1. B 的运行

`COMPLETED`，`ExitCode 0:0`，**12:41**，`blc[081-100]`。
**8760 个时间步**，`2025-01-01_01:00:00` → `2026-01-01_00:00:00`（365×24，NO_LEAP）。

错误扫描：`above upper bound` / `Fortran runtime error` / `ENDRUN` / `SIGSEGV` /
`cbalance` / `nbalance` **全部 0**。

产物齐全：`elm.r.2026-01-01`、`cpl.r.2026-01-01`、`elm.rh0/rh1.2026-01-01`、
`elm.h0/h1.2025-02-01`，以及被追加了 2025 年 1 月的
`…t4_n20.elm.h0/h1.2024-02-01`。

## 2. 完整比较（job 516291）

| 文件 | DATA 相等 | DATA 不同 | TEXT | META |
|---|---|---|---|---|
| `elm.r` 2026-01-01 | 460 | **2** | `locfnh`/`locfnhr` | `case_id`、`history` |
| `cpl.r` 2026-01-01 | 16 | **0** | `seq_infodata_case_name` | 无 |
| `elm.rh0` 2026-01-01 | 10 | **0** | 0 | `case`、`history` |
| `elm.rh1` 2026-01-01 | 10 | **0** | 0 | `case`、`history` |
| **`elm.h0` 2024-02-01（跨重启点）** | **569** | **0** | **0** | **无** |
| **`elm.h1` 2024-02-01（跨重启点）** | **115** | **0** | **0** | **无** |
| `elm.h0` 2025-02-01 | 560 | **1** | `time_written` | 4 项 |
| `elm.h1` 2025-02-01 | 115 | **0** | `time_written` | 3 项 |

**跨越重启点的那两个 history 文件（2024-02-01，含 2025 年 1 月）DATA、TEXT、META
三者全等**——这是最直接的一条：重启那一刻前后的输出完全一致。

### 点名字段（job 516291 §3）

| 类别 | 字段 | 差异点数 |
|---|---|---|
| 气象驱动 | TBOT, PBOT, QBOT, FSDS, FLDS, WIND, RAIN, SNOW | **全部 0** |
| CO2 | PCO2 | **0** |
| Ndep | NDEP_TO_SMINN | **0** |
| 人口 | HDM | **0** |
| 土地利用状态 | TLAI, TOTVEGC | **0** |
| — | **SEEDC_GRC** | **551,650** |

## 3. 三处差异，逐项定位

### 3.1 `SEEDC_GRC`（h0 2025-02-01，551,650 点）

每条记录 45,970–45,971 个点，**12 条记录完全一致**：
A = **−0.249561**，B = **0**，`max rel = 1`。
A 的域内和从 −605.4（2025-02）单调走到 −838.6（2026-01），B 恒为 0。

与 0.5° 测试 2a 完全同一签名。`SEEDC_GRC` 是"pool for seeding new PFTs via
dynamic landcover"的**格点级诊断，不随 restart 保存**，在分段起点归零。
列级 `seedc` 与其余全部碳库一致（`TOTVEGC` 差异 0）。
**不是状态发散。**

### 3.2 `BTRANAVG_VALUE` / `BTRAN_MIN`（elm.r，各 515 点）

两者签名完全相同（job 516292）：

```
shape (2441624,) 在 pft 维
NaN:  A=1,852,577   B=1,853,092    only-B=515   only-A=0
在两侧都有效的 588,532 个点上:  max|A-B| = 0，差异点数 = 0
B 为 NaN 而 A 有值的那 515 点，A 的取值 0..1，均值 0.806
```

`BTRANAVG_VALUE` = "average over an hour of btran"，
`BTRAN_MIN` = "daily minimum of transpiration wetness factor"——都是蒸腾水分
胁迫因子的**短周期累加量**。

**两侧都有效的点上逐位相同**；差别只是 B 多了 515 个填充点（占 2,441,624 个
PFT 点的 **0.021%**），那是 A 在 2024 年某时刻写入、之后一直保留的陈旧值，
而 B 在它自己那一年里从未写入过。**不是数值分歧，是"有没有被赋过值"的差别。**

### 3.3 B 的 2025-02-01 h0 多 8 个变量

`BSW`、`DZLAKE`、`DZSOI`、`HKSAT`、`SUCSAT`、`WATSAT`、`ZLAKE`、`ZSOI`——
时间常量的 3D 场。B 的这个文件是**它那次作业的第一个 history 文件**，ELM 把
时间常量场写进每次运行的第一个文件。与 0.5° 测试 2a 观察到的现象相同。
对应的 `Time_constant_3Dvars` / `Time_constant_3Dvars_filename` 两个全局属性
也因此只在一侧出现。

## 4. 允许通过的元数据差异（逐项列明）

- `case_id` / `case`：`…t4_n20` vs `…t3_restart`
- `history`：文件创建时间戳
- `time_written`
- `locfnh` / `locfnhr`：restart 内部记录的 history 文件路径
- `seq_infodata_case_name`：**本次刻意改写**，否则驱动会拒绝续跑
- `Time_constant_3Dvars` / `_filename`：见 §3.3

## 5. 结论

**通过。** 物理状态一致：全部气象驱动、CO2、Ndep、HDM、土地利用状态与所有
碳氮磷库在 A、B 之间差异为 0；跨重启点的 history 文件三项全等。

三处差异全部是**重启的记账副作用**，没有一处是模型状态或驱动的分歧。

### 对正式运行的影响（需要在分析时知道）

11 年 × 7 段意味着 **6 个重启边界**，每个边界上：

1. `SEEDC_GRC` 归零并重新累积 → 该变量在段边界有不连续，**出图与区域统计时
   需排除或说明**。量级：两年累积域内和 −839，对照 `TOTVEGC` 1.22e10，
   相对 7e-8。
2. `BTRANAVG_VALUE` / `BTRAN_MIN` 有约 515 个 PFT 点转为填充值。
3. 每段第一个 h0 文件会多带 8 个时间常量场。

这三条都不影响科学结论，但**都会出现在正式输出里**，事先记下来免得被
误读成物理信号。

## 6. 范围限定

单一重启点、日历年边界、20 节点布局、1 + 2 模式年。
**不覆盖** 77 年跨 6 个边界的累积效应——那只有正式运行本身能给出。
