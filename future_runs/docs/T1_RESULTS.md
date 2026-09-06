# T1 — 4 km future 启动测试结果

case `20260905_seus_4km_fut_t0_ssp370`，10 节点 / 1280 tasks，构建 D
（`DEBUG=TRUE`，`-fcheck=bounds,pointer`，已删 `-ffpe-trap`），
E3SM `0be814f868`（含缺陷 A + B 修复）。
`finidat` = 旧 20260723 的 2024 存档，**仅用于代码路径验证，非科学验收**。

| 作业 | 结果 |
|---|---|
| 511795（修 landuse 之前） | **FAILED**，41 s，`PCT_NAT_PFT` 和不为 1 → ENDRUN |
| 511835（修 landuse 之后） | **COMPLETED 0:0**，14:04 |

## 通过项

**积分**：49 个时间步，2024-01-01_00:00 → 2024-01-03_00:00（2 模式日，1 小时步长），
写出 2 个 restart（`REST_N=1 ndays`）。

**零错误，且 bounds checking 是开着的**——这证明没有越界，而不只是没崩：

```
above upper bound 0   Fortran runtime error 0   ENDRUN 0
SIGSEGV 0             cbalance 0                nbalance 0
```

**七个变量的初始化索引**（`DIAG_INIT`，call 1），与源码推导逐位吻合：

```
v=1..7 全部:  t1=2920  t2=2921  timelen=227760  tl_spinup=2920  npf=3  tres=3
```

`(2024−2023)×2920 = 2920`，`timelen = 78×2920 = 227760`。这也是 0.5°
衔接测试（只打 `v=1`）拿不到的七变量覆盖。

**递增相位**（`DIAG_POST`，按 `v=` 索引提取），与源码的两类触发条件吻合：

| call | TBOT | PSRF | FSDS | PRECT | WIND | FLDS |
|---|---|---|---|---|---|---|
| 2 | 2921 | 2921 | **2920** | **2920** | 2921 | 2921 |
| 4 | 2921 | 2921 | 2921 | 2921 | 2921 | 2921 |
| 5 | 2922 | 2922 | **2921** | **2921** | 2922 | 2922 |
| 7 | 2922 | 2922 | 2922 | 2922 | 2922 | 2922 |

`FSDS(v=4)`/`PRECTmms(v=5)` 走记录边界触发，其余五个走记录中点触发，
两组相差一步；每条记录用满 3 步（`npf=3`）。**4 km 的 `npf=3` 与 0.5° 的
`npf=6` 相位不同，所以这一条只能在 4 km 上测。**

**dummy-year 尾记录修复，在 4 km 上独立复现**（`DIAG_READ`，call 1）：

```
七个变量全部  raw1 == raw2
TBOT 6148/6148  PSRF 9324/9324  QBOT -10238/-10238  FSDS -14600/-14600
PRECTmms 0/0    WIND -12590/-12590   FLDS -2736/-2736
```

record 2920（dummy 年最后一条）与 2921（2024 第一条真数据）值相同，
插值发生在两个相同值之间，零失真。

**实际 forcing ≠ 混合值，三段分离是必要的**（`DIAG_FORC`/`DIAG_FLUX`，call 1）：

| 量 | 混合值 | 实际 forcing |
|---|---|---|
| T / TH / PBOT / Q | 298.617 / 101300 / 0.01563 | 相同（`vmult=1, voff=0`，未触 323 钳位） |
| LWD | 408.15 | 相同——`ea·σ·tbot⁴` 覆盖分支**未触发**（观测，不是假设） |
| **FSDS** | **−0.0269** | **SOLAD1/2 = SOLAI1/2 = −0.0** ← 被 `max(...,0)` 归零并拆成四个分量 |
| **PRECTmms** | **0** | RAINC/RAINL/SNOWC/SNOWL 全 0 |
| WIND | 6.8136 | U = 6.8136 |

如果按原来那版把混合值标成 "used"，FSDS 这一条就会拿 −0.027 去核对，
而模型实际用的是 0。

**输入年份配对**（h0，48 条逐时记录）：`PCO2` max 43.27 Pa
→ 427.1 ppmv，对照 ssp370 CO2 文件 2024 年 428.78 ppmv（2023 = 425.28，
2025 = 432.35），落在 2024 上。`HDM` 0.497–1397 counts/km²、
`NDEP_TO_SMINN` 7.6e-09–3.9e-08 均非零。

**三项人工一致性核查**（三个 `check_*_consistency` 都是 `.false.`，所以必须人工做）：

| 项 | 结果 |
|---|---|
| fsurdat / landuse 维度 | `lsmlat=324 lsmlon=504 natpft=17` 一致 |
| landuse `YEAR` | 2024..2100，n=77 |
| finidat | `gridcell=75920 column=1226904 pft=2441624` |
| `LANDFRAC_PFT` / `PCT_NATVEG` / `AREA` / `LONGXY` / `LATIXY` fsurdat vs landuse | 全部 max\|diff\| = **0** |

## 查出的既有问题（不是 T1 引入，不阻塞 T1）

**194 个活跃陆地格点读到海洋 sentinel。** `TBOT` 触 `min(...,323)` 上钳、
`PBOT` 同时触 `max(...,40000)` 下钳，同样的 194 个格点。

对照生产历史运行的 h0（2023 年）：

```
T1 future        : 9312 点 / 194 个格点 (0.2555% of finite)
生产历史 (2023)  : 2328 点 / 194 个格点 (0.2555% of finite)
两边都热的格点   : 194     仅 future : 0     仅历史 : 0
```

**完全相同的 194 个格点，前六个索引也相同。** 所以这是 4 km 域与 TESSFA2
气象网格之间既有的陆/海掩膜错配（同 `cpl_bypass_met_reader_resolution_independence`
记的 HDM 沿海格点问题），已完成的 174 年历史生产运行同样带着它。
占活跃陆地格点的 0.26%。**记录待处置，不阻塞 T1/T2。**

## 我自己诊断补丁的一个缺陷

`DIAG_PRE`/`DIAG_POST` 里的变量名是垃圾字符（有时截断整行）。原因：
`metvars` 只在 `loaded_bypassdata == 0` 的加载分支里赋值，逐步分支里它是
未初始化的局部数组。`DIAG_INIT` 在加载分支内，名字是对的。

影响：`v=` 索引可靠，名字不可靠，`v=3 (QBOT)` 的部分行被截断无法解析。
不影响模型。T2 之前应改掉（从 PRE/POST 去掉 `metvars`）。
