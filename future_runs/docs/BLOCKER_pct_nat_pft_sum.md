# 阻塞项：4 km future landuse 的 `PCT_NAT_PFT` 不满足 ELM 的和为 1 检查

发现于 2026-09-05，T1 首次提交（job 511795）启动 41 秒即 ENDRUN。
**报告，不自行重做输入数据。**

## 现象

```
read_variable_3d ERROR: sum of PCT_NAT_PFT not 1.0 at nl=60 and t=1
sum is:  1.0000000168383121
sum is:  0.99999998517334465
ENDRUN:ERROR in .../components/elm/src/main/surfrdUtilsMod.F90 at line 75
```

`t=1` 是文件的第一条时间记录，即 2024 年。全部 1280 个 task 同时报错，
作业 FAILED，无 restart 写出。

## 判据

`surfrdUtilsMod.F90` 的 `check_sums_equal_1_3d`：

```fortran
real(r8), parameter :: eps = 1.e-14_r8
...
if (abs(sum(arr(nl,t,:)) - 1._r8) > eps) then ... call endrun
```

`eps = 1e-14`，实际上是双精度精确相等。这不是 DEBUG 专属检查，
release 构建同样 ENDRUN。

## 实测（jobs 511796 / 511797）

对每个文件取第 1 / 中间 / 最后一条时间记录，按 `sum(PCT_NAT_PFT)/100 − 1` 统计：

| 情景用的 landuse | max\|sum/100−1\| | 超出 1e-14 的格点 | 结论 |
|---|---|---|---|
| Default SSP1_RCP19 | 5.552647e-08 | 76,357 | **FAILS** |
| Default SSP2_RCP45 | 5.552647e-08 | 76,355 | **FAILS** |
| Default SSP3_RCP70 | 5.552647e-08 | 76,347 | **FAILS** |
| Default SSP5_RCP85 | 5.552647e-08 | 76,367 | **FAILS** |
| DF SSP3_RCP70 | 5.552647e-08 | 76,347 | **FAILS** |
| RH SSP3_RCP70 | 5.552647e-08 | 76,347 | **FAILS** |
| **RF**（情景无关） | 6.661338e-16 | **0** | passes |

对照组，同样口径：

| 对照 | max\|sum/100−1\| | 超出 1e-14 | 说明 |
|---|---|---|---|
| 4 km 历史 smoothHARV（生产 511164 正在用） | 6.661338e-16 | 0 | 通过 |
| 0.5° future ssp370（七个 run 已跑完 77 年） | 6.661338e-16 | 0 | 通过 |

## 事实与推断的分界

**事实**

- 七个正式情景里 **6 个的 landuse 文件不满足该检查**，只有 RF 通过。
- 偏差 5.55e-08 ≈ float32 机器精度（1.19e-07）量级；`PCT_NAT_PFT` 在三类
  文件里都声明为 `double`，所以不是存储类型差异。
- 受影响格点约 76,3xx 个，对照活跃陆地格点 75,920——**基本是全部陆地格点**，
  不是个别坏点。
- 第一条和最后一条记录偏差相同，是系统性的，不是单条记录的问题。
- DF/RH 只改 `HARVEST_*`、`PCT_NAT_PFT` 沿用 Default，所以继承了同一缺陷；
  RF 重建了整条土地覆盖轨迹，因而干净。
- 0.5° 版本通过，是因为聚合过程在 float64 里重新归一化，把偏差洗掉了——
  **这也解释了为什么 0.5° 七个 run 能跑完而 4 km 一步都起不来。**

**推断，未证实**

- 2026-08-31 的 `t0probe`（job 503734，17 秒失败）用的是
  `Default SSP2_RCP45` 这一族文件。现在有了一个可复现、签名吻合的失败模式，
  它比之前"当时的构建有问题"或"2 节点内存不足"的猜测更有依据。
  但当时的 exe 已被替换，**不能据此断定**，只能记为最可能的候选。

## 影响

- **T1 按 Default/ssp370 配置无法进行**；T2/T3/T4 同样受阻，因为都以
  Default 基准 case 为起点。
- 七个正式长作业中 6 个直接受阻。
- 生产 511164（历史）不受影响，其 landuse 通过检查。

## 待决

修复归属在 `ELM_Futu_landuseInput` 的 landuse 生成侧，不在运行侧。
按指示不自行重做输入数据，等指示。
