# Future landuse.timeseries 构建 —— 工作记录（记忆文档）

把 Chen2022 未来土地利用趋势谐调进 NLCD-derived 历史,产出与现有 ELM SEUS
`landuse.timeseries` schema 完全一致的 **未来 2024–2100** 强迫场。

- 方法理论:`HARMONIZATION_SEUS_PILOT.md`(§13)、`REFERENCE.md` §13。
- 主脚本:`scripts/02_harmonize_seus.py --build-timeseries`(A/B/C 三阶段都在里面)。
- 网格工具:`scripts/01_chen2022_to_elm_landuse.py`(加了 `--like <ELM文件>`)。

---

## 0. 最终成品

```
outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc
  <SSP> ∈ {SSP1_RCP19, SSP2_RCP45, SSP4_RCP60, SSP5_RCP85}   各 ~152 MB
```

时间 2024–2100(77 年),网格 324×504(lsmlat/lsmlon),变量名/维度/dtype/网格
**与目标历史文件逐项一致**:

```
目标:landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc
      (/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/surfdata_results/)
```

---

## 1. 全景：谁提供什么

| 角色 | 来源 | 提供 |
|---|---|---|
| 历史状态(锚) | 目标 landuse.timeseries c260723 | 静态 `PCT_NATVEG` + `PCT_NAT_PFT(2023)` + 所有静态 land-unit 变量 |
| 未来趋势 | Chen2022 SSP(1km → 目标网格) | `PCT_NAT_PFT` 的逐年组成变化 |
| 未来采伐 | LUH2 v2f 情景 transitions(`/luh/ssp*_transitions.nc`) | `HARVEST_×5` + `GRAZING` |

核心思想(LUH2 / Chen2020 §2.3 / Chen2022 §1.4):**状态听高分辨率 base map,
未来变化听情景模型,用 delta 谐调接起来**。

---

## 2. 关键决策与理由（记忆重点）

| 决策 | 选择 | 为什么 |
|---|---|---|
| splice 年 | **anchor = 2023**(NLCD 末观测年) | 观测用满到 2023,Chen 只负责 2024 起;输出从 **2024** 开始 |
| 谐调层次 | **功能组**(Bare/Tree/Shrub/Grass/Crop)再拆回 17 PFT | 避开 9/10、13/14、1/7 等约定/标签假象(§11c) |
| 拆分比例 | **NLCD 2023 组内比例冻结** | Chen 只定组总量,PFT 身份(松/落叶等)留给 NLCD |
| natveg | **静态(option A)** | ELM landuse.timeseries schema 固定 land-unit,只让 `PCT_NAT_PFT` 时变;mksurfdata 源码证实(natveg 只写一次)。城市化(natveg 收缩)在此 schema 结构性无法表达——被丢的量:SEUS 2020→2100 均值仅 −2.8% of cell,集中在 ~5% 城市边缘格。保留的组成变化(grass→tree)是丢弃量的 ~6×,方向正确。 |
| natveg=0 格点 | **PFT0 (bare) = 100** | 对齐目标约定;组成在 natveg=0 处对 ELM 无意义 |
| 农田 | 保留(= PFT15 在 natveg 内,`PCT_CROP≡0`) | 农田变化是组成变化,不是被忽略;只有 urban 扩张被忽略 |
| harvest 权重 | **我们逐年 harmonized 森林 × 目标静态 natveg** | 和 ELM 实际跑的(冻结)森林自洽;与"用 Chen 逐年真实 natveg"实测只差 ~1.3%,可忽略 |
| harvest 情景 | 与土地利用情景**配对**(SSP2 land use ↔ ssp2rcp45 harvest) | 一个 forcing 内自洽 |
| GRAZING | 沿用目标 **2023** 值 | s4_2 里 GRAZING 是常数;持久化历史末值最简单一致 |
| 输出 dtype | float64 | 与目标一致 |

---

## 3. 流水线（`02 --build-timeseries` 内部三阶段）

**前置(一次性):Chen → 目标网格**
```
01 --scenario <SSP> --years 2015 --extra-years 2020:2100:5 \
   --like <目标 landuse.timeseries>  --out interim/chen_targetgrid_<SSP>_2015-2100_1_24deg.nc
```
为什么必须重生成:旧 CONUS Chen 格心从 25.0 起、南界到 25°N;目标网格格边从
24.0 起(格心 24.0208,半格偏移)、南到 24°N。两者是**不同网格**,不能裁/挪,
只能从 1km 用 `--like` 重新面积聚合。（`--bbox -95 24 -74 37.5` 等价。）

**阶段 A —— 组成（§13 on 目标网格）**
- 锚 `p_nl = 目标静态 natveg × 目标 natpft(2023)`;Chen `p_ch` = target-grid 文件逐年。
- §13 功能组 min-footprint march(公式1)+ NLCD 冻结比例拆回 17 PFT。
- `recover`:natveg=0 → **PFT0=100**;其余 sum=100。

**阶段 B —— harvest 下采样（复用 s4_2 方法)**
- 读 `/luh/ssp{X}_transitions.nc`(0.25°,720×1440,lat 降序)。
- 权重 `w = tree_share(逐年 harmonized) × natveg(静态)`。
- 面积守恒下采样 `frac_i = F·w_i·ΣA/Σ(wA)`(逐字复用 s4_2 的
  `_build_hr_to_coarse_index` / `_distribute_conservatively`)。
- 转 LUT 单位 `÷veg_frac`,5 类和裁 ≤1。
- 时间 **k=−1**:输出标签年 Y → LUH2 日历 Y−1 → SSP index `(Y−1)−2015`。
- 5 变量:`primf/primn/secmf/secyf/secnf_harv → VH1/VH2/SH1/SH2/SH3`。

**阶段 C —— 组装成 landuse.timeseries**
- 从目标**逐字拷贝**所有静态变量(LANDFRAC_PFT/PFTDATA_MASK/PCT_NATVEG/PCT_CROP/
  AREA/LONGXY/LATIXY/PCT_WETLAND/PCT_LAKE/PCT_GLACIER/PCT_URBAN/*_P)。
- 时变量(2024–2100):`PCT_NAT_PFT` + `HARVEST_×5` + `GRAZING` + `YEAR` +
  `input_pftdata_filename`。
- 维名 `lsmlat/lsmlon/time/natpft/numurbl`,dtype float64;写前 `assert` 网格
  与目标逐点相等。

---

## 4. 路径速查

| 内容 | 路径 |
|---|---|
| 目标(锚+网格+静态变量) | `.../surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc` |
| Chen 1km 源 | `data/external/chen2022_1km/<SSP>/global_PFT_*.tif` |
| Chen → 目标网格 | `outputs/interim/chen_targetgrid_<SSP>_2015-2100_1_24deg.nc` |
| LUH2 情景 harvest | `/projects/hpcl-cli185/proj-shared/zw5/luh/ssp{119,245,460,585}_transitions.nc` |
| **成品** | `outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc` |
| harvest 下采样参考实现 | `.../s4_LUToutput_pft/s4_2_donwscale_LUH2harvest.py`（面积守恒 36× 修复见其中）|

---

## 5. 如何复现

```bash
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
export PYTHONPATH=$PWD/src
TGT=.../surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc

# 1) Chen -> 目标网格（4 情景，jobs/submit_chen_targetgrid.sbatch）
$PY scripts/01_chen2022_to_elm_landuse.py --scenario SSP2_RCP45 --years 2015 \
    --extra-years 2020:2100:5 --like "$TGT" \
    --out outputs/interim/chen_targetgrid_SSP2_RCP45_2015-2100_1_24deg.nc

# 2) 建 landuse.timeseries（4 情景，jobs/submit_landuse_future.sbatch）
$PY scripts/02_harmonize_seus.py --build-timeseries --scenario SSP2_RCP45
```
（Slurm:`-p hpcl-cli185 -q hpcl-cli185 -A hpcl-cli185 --mem=64g`。）

---

## 6. 验证结果（4 情景全过）

| 检查 | 结果 |
|---|---|
| harvest 面积守恒 placed/allocatable | **1.0000** |
| `PCT_NAT_PFT` sum-to-100 | max|sum−100| = **0.0000** |
| anchor 2023 == 目标 2023(natveg>0) | max|diff| = **0.0000** |
| 网格 LATIXY/LONGXY/dims vs 目标 | **一致(True)** |
| 变量名/维度/dtype vs 目标 | **NONE mismatch**(24 变量全对应) |
| 静态变量 vs 目标 | **逐字节相等** |
| harvest 量级(我 2024 vs 目标 2023) | SH1 sum 661 vs 691(~4%)、VH1 39 vs 48(~19%),连续 |
| inf/nan | 无 |

---

## 7. 踩过的坑（记忆重点）

1. **网格半格偏移**:A(格心对整数,从 25.0)vs B(格边对整数,从 24.0,格心
   24.0208)是两个网格,南界还差 1°。→ 必须 `01 --like <目标>` 从 1km 重聚合。
2. **PFT3 落叶松 bug**(§4):`remap_boreal_ndt_by_lat` 传了升序 lat 而数组是
   north-up,mask 上下颠倒 → 佛州出现 100% 落叶松。修:`lat_centers[::-1]`。
3. **harvest 36× 守恒 bug**(s4_2):旧版守恒"分数之和"而非"面积积分";正确
   `frac_i = F·w_i·ΣA/Σ(wA)`。用经验比值 35.99→1.00 验证。
4. **LUH2 时间无法解码**:units="years since..." + noleap 日历 → `xr.open_dataset(...,
   decode_times=False)`(只用位置索引 isel)。
5. **dtype**:时变量默认 float32,目标是 float64 → 写前 `.astype(np.float64)`。
6. **natveg=0 的 4 个目标异常格**:目标自己在 natveg=0 处给了非-bare,我们统一
   强制 bare=100(更自洽,natveg=0 处组成无意义)。
7. **mksurfdata 冻结 natveg**:源码证实 landuse.timeseries 的 `PCT_NATVEG` 只写
   一次(取 base year),LUT 里逐年 natveg 不进输出 → option A 是 schema 固有行为,
   不是我们的近似选择。城市化因此不可表达(见 §2)。

---

## 8. 相关文件

- `scripts/02_harmonize_seus.py` —— 主脚本(标准 CONUS 谐调 + `--build-timeseries` 模式)。
- `scripts/01_chen2022_to_elm_landuse.py` —— Chen→ELM,`--like` 支持 ELM 格式。
- `scripts/analysis/` —— 全部诊断/画图/一次性检查脚本。
- `jobs/submit_chen_targetgrid.sbatch`、`jobs/submit_landuse_future.sbatch`。
- `HARMONIZATION_SEUS_PILOT.md`、`REFERENCE.md`(§13 方法与证据)。
- 采伐:`s4_2_donwscale_LUH2harvest.py`;工作流:`.../Make_surface_data/my_workflow_Make_surface_data.md`。

## 9. 待办 / 未做

- 只做了 **2024–2100 未来段**;若要完整 1850–2100 单文件,需把目标 1850–2023 拼在前面。
- **urban/城市化**未表达(option A);若需要,得改 ELM schema 为时变 land-unit(需确认 ELM 版本支持)。
- harvest 未来段目前是 `02` 内部重实现的下采样;`s4_2` 本身尚未扩到 2100(文档标"待实现")。
