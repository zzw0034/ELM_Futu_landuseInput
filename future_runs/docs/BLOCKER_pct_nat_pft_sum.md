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

## 根因定位（2026-09-05）

`scripts/02_harmonize_seus.py`，`build_landuse_timeseries()`（`--build-timeseries`
生产入口）。归一化本身是对的，**错在归一化之后被降精度存了一遍**：

```python
442:  comp = np.zeros((nyr, NPFT, ny, nx), dtype=np.float32)      # ← 容器是 float32
...
452:      ci = np.where(s > 0, 100.0 * p_harm[i] / np.where(s > 0, s, 1.0)[None], 0.0)
                                                              # ↑ float64，精确归一到 100
456:      comp[i] = ci.astype(np.float32)                       # ← 精度在这里丢掉
...
462:  pft_out = comp[1:]
...
556:  pft_out.astype(np.float64)   # 注释写的是 "match the target dtype exactly"
                                   # 只修 dtype，修不回已经丢掉的位
```

17 个分量各自舍入到 float32 后，其和不再精确等于 100，而是 100 ± 6e-6
（相对 6e-8），与实测的 5.55e-08 完全对得上。第 556 行那个 `astype(np.float64)`
把它洗成了一个"看起来是双精度"的数——所以 `ncdump` 显示 `double`，
但数值只有单精度的信息量。这也是为什么"检查 dtype"这一关没能发现问题。

### 为什么各条 QA 都没拦住

| 检查 | 阈值 | 为什么漏掉 |
|---|---|---|
| `02_harmonize_seus.py:508` 的 sum-to-100 | **没有阈值** | 只是 `print(f"...{...:.4f}")`。真实误差 5.5e-06（百分数单位）在 4 位小数下打印成 `0.0000` |
| `FUTURE_LANDUSE_TIMESERIES.md` §6 验证表 | 抄的上面那行 | 记录成 "max\|sum−100\| = **0.0000**"，看起来是完美通过 |
| `build_harvest_scenarios.py:187` 的 gate | `err.max() > 1e-3` | 比 ELM 的 1e-14 松 11 个数量级 |
| dtype 一致性检查 | 比较声明类型 | 声明确实是 `double`，一致 |

四道关都是"看起来通过"，没有一道对着 ELM 的真实判据 `1e-14`。

### 为什么 RF 干净、DF/RH 不干净

`build_harvest_scenarios.py` 里 RF 自己在 float64 下从 2023 anchor 重算
`rf_pft`，没走过 float32；DF/RH 则是
`default_pft = np.array(ds["PCT_NAT_PFT"][:])` 直接从 Default 成品里读，
把缺陷一起继承了。

## 修复方案（已执行，见下方"解决状态"）

改两行，`02_harmonize_seus.py`：

```python
442:  comp = np.zeros((nyr, NPFT, ny, nx), dtype=np.float64)
456:      comp[i] = ci
```

`ci` 已经在 float64 里精确归一，保留即可。实测旁证：历史文件、0.5° future、
RF 三者都是 float64 路径，实测偏差 6.66e-16，比 ELM 的 1e-14 低两个数量级，
**说明纯 float64 归一化足够，不需要额外的强制配平**。

内存代价：`comp` 从 875 MB 变 1.75 GB，作业是
`submit_landuse_future_array.sbatch`（`--mem=64g`，`-t 00:40:00`），余量充足。

同时应该修的（否则下次还是拦不住）：

1. ~~`02_harmonize_seus.py:508` 的打印改成对着 `1e-14` 的**断言**，不是 `:.4f` 打印。~~
   **已修**，commit `9de4236`（2026-09-05 08:31），同一提交里一起做的。
2. ~~`build_harvest_scenarios.py:187` 的 `1e-3` 收紧到 ELM 判据。~~
   **已修**，同一提交 `9de4236`：`err.max() > 1e-3` 改成了 `> 1e-12`
   （对应 ELM `eps=1e-14` 在百分数单位下的等价阈值），现在超标会直接
   `raise ValueError` 拒绝写出，不会再让坏文件蒙混过关。
3. `FUTURE_LANDUSE_TIMESERIES.md` §6 的验证表重记（当前那个 `0.0000` 是假通过）——
   **仍未做**，如果之后要引用那张表，先重新measure再填。

## 重建范围（原计划）

需要重跑 `02_harmonize_seus.py --build-timeseries` 的 4 个 SSP（array job，
4 个 task 并行，每个 40 分钟内），然后由它们派生的 DF、RH 重建；
**RF 不需要动**。合计 6 个文件。

按指示，定位与方案到此为止，未修改脚本、未重做任何数据。（此段是
2026-09-05 诊断时的原始记录，保留存档——实际重建范围比这里写的更窄，
见下方"解决状态"。）

## 解决状态

**2026-09-05**：代码修复（`02_harmonize_seus.py` float64 + 两处 QA 门槛收紧，
commits `d94ddb0`/`0ce5c85`/`9de4236`）当天完成，同时重建了 4 个 SSP 的
Default 文件（`landuse.timeseries_SEUS_1_24deg_nlcd2elm_{SSP1_RCP19,
SSP2_RCP45,SSP3_RCP70,SSP5_RCP85}_simyr2024-2100.nc`，全部 mtime 09-05
08:34）。但**只有 `SSP3_RCP70` 的 DF/RH 衍生文件被一并重建**（09-05
08:36/08:37，因为当时"七个正式 run"只用得到 SSP3_RCP70 的 DF/RH，见
`PRODUCTION_STATUS.md`）；`SSP1_RCP19`/`SSP2_RCP45`/`SSP5_RCP85` 的 DF、RH
六个文件停留在 08-19/08-28 的旧版本，未被纳入当时的重建范围。

**2026-09-19**：这个遗漏在 `20260915_seus_4km_fut_{ssp119,ssp245,ssp585}_{DF,RH}`
六个新增敏感性 case（不在原七个正式 run 之列）上被踩中——全部在初始化阶段
以完全相同的签名 ENDRUN（`sum of PCT_NAT_PFT not 1.0 at nl=... and t=1`）。
`ssp245_DF` 首次提交（job 540582）还额外撞上一个无关的 `.git/index.lock`
竞争（`e3sm_cases` 目录被并发 session 同时操作），在到达 PCT_NAT_PFT 检查
之前就已失败；该锁后来已消失，不影响本次修复。

**2026-09-20/21**：
1. 用 `harvest_scenarios/jobs/submit_harvest_scenarios.sbatch --array=0,1,3`
   （job 549462，跳过已修好的 index 2/`SSP3_RCP70`）重建了 6 个文件：
   `{SSP1_RCP19,SSP2_RCP45,SSP5_RCP85}_{DF,RH}`。3 个 array task 全部
   `COMPLETED 0:0`，脚本内建的 `1e-12` 完整性门槛全部通过（顺带以同一次
   提交重写了共享的 RF 文件——RF 与 Default 无关、构建路径本就是
   float64，重写前后应为等价结果，未见异常）。
2. 独立用 ELM 的真实判据 `eps=1e-14` 复核了 `SSP5_RCP85_RH`：偏差从旧文件
   的 `5.552647e-08`（76,367 个活跃陆地格点超标，99.93%）降到新文件的
   `6.661338e-16`（0 个超标），与历史文件/0.5°聚合/RF 的"干净"基准完全同量级。
3. 重新提交 6 个 case（job 549473/549474/549476/549477/549479/549481），
   全部越过初始化阶段（此前平均在 2 分钟内 ENDRUN），首段（11 年）全部
   `COMPLETED 0:0`，`RESUBMIT=6` 自动续投链条已接管，持续正常产出 h0。
   **截至 2026-09-21 09:39，6 个 case 均未跑完**（各自进度 46-55/77 年，
   仍在自动续投中，尚无 2101-01-01 收尾 restart）——本节记录的是"初始化
   bug 已修复、run 正常推进"，不是"run 已完成"，完成状态请在推进后
   重新核对 h0 文件数与收尾 restart。
