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
  <SSP> ∈ {SSP1_RCP19, SSP2_RCP45, SSP3_RCP70, SSP4_RCP60, SSP5_RCP85}   各 ~152 MB
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
| harvest 权重 | **逐年 harmonized 森林占比 × 逐年谐调 natveg** | 下采样与 LUT 分母都用 annual natveg（对齐 s4_2）；文件里的 `PCT_NATVEG` 仍是目标静态列，所以 ELM 收回的采伐面积带 `natveg_static/natveg_annual` 因子（§11.6，约 +2%） |
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
| LUH2 情景 harvest | `/projects/hpcl-cli185/proj-shared/zw5/luh/ssp{1rcp19,2rcp45,3rcp70,4rcp60,5rcp85}_transitions.nc`（文件名是 `ssp1rcp19` 式,不是 `ssp119` 式;映射见 `02` 的 `LUH_FILE`）|
| **成品** | `outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc` |
| harvest 下采样参考实现 | `.../s4_LUToutput_pft/s4_2_donwscale_LUH2harvest.py`（面积守恒 36× 修复见其中）|

---

## 5. 如何复现

```bash
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
export PYTHONPATH=$PWD/src
TGT=.../surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc

# 1) Chen -> 目标网格（原 4 情景循环:jobs/submit_chen_targetgrid.sbatch
#                      仅 SSP3_RCP70:jobs/submit_chen_targetgrid_ssp370.sbatch）
$PY scripts/01_chen2022_to_elm_landuse.py --scenario SSP2_RCP45 --years 2015 \
    --extra-years 2020:2100:5 --like "$TGT" \
    --out outputs/interim/chen_targetgrid_SSP2_RCP45_2015-2100_1_24deg.nc

# 2) 建 landuse.timeseries（原 4 情景循环:jobs/submit_landuse_future.sbatch
#                           仅 SSP3_RCP70:jobs/submit_landuse_future_ssp370.sbatch）
$PY scripts/02_harmonize_seus.py --build-timeseries --scenario SSP2_RCP45
```
不带 `--build-timeseries` 的 `02` 是 standalone 诊断路径，输入缺失时会直接退出，不是维护中的 ELM 强迫入口。`jobs/submit_harmonize_seus.sbatch` / `submit_harmonize_regen.sbatch` 走的就是这条，不要当成生产链。

（Slurm:`-p hpcl-cli185 -q hpcl-cli185 -A hpcl-cli185 --mem=64g`。）

---

## 6. 验证结果（5 情景全过）

下表前 4 情景为 2026-07-24 那批;SSP3_RCP70(2026-07-29 补跑)前四项同样是
1.0000 / 0.0000 / 0.0000 / True,24 变量、324×504 网格、77 年 2024–2100、
152 MB 均与其余四套一致。


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
- `jobs/submit_chen_targetgrid.sbatch`、`jobs/submit_landuse_future.sbatch`（原 4 情景循环）。
- `jobs/submit_chen_targetgrid_ssp370.sbatch`、`jobs/submit_landuse_future_ssp370.sbatch`
  —— SSP3_RCP70 单情景版。**不要**把 SSP3_RCP70 加进上面两个循环脚本:那会重算并
  覆盖已验证的 4 套 interim/processed 文件。
- `jobs/download_luh2_ssp370.sbatch` —— 取 LUH2 v2f ssp370 harvest(见 §9.4)。
- 谐调诊断(读 interim diag npz,不是交付 .nc):
  - `scripts/analysis/03_harmonize_seus_diag.py` —— 单情景轨迹/残差/样点组成
    (`jobs/submit_diag.sbatch`, `jobs/submit_harmonize_regen.sbatch`)。
  - `scripts/analysis/04_chen_spatial_years.py` / `05_chen_change_map.py` —— Chen
    空间年切片与 2020→2100 变化(`jobs/submit_chen_spatial.sbatch`,
    `jobs/submit_chen_change.sbatch`)。
  - `scripts/analysis/06_harmonize_seus_compare.py` —— 四情景 diag 对比,覆盖
    SSP1/2/**4**/5(`jobs/submit_harmonize_compare.sbatch`)。
- 成品对比与采伐诊断(见 §11,均配 `jobs/submit_*.sbatch`,用 `-p serial -q normal`):
  - `scripts/analysis/07_scenario_compare_final.py` —— 读**交付的 .nc**做四情景对比
    (`--compute` 算 npz / `--plot` 只重画)。注意与 `06_harmonize_seus_compare.py`
    的区别:06 读 interim diag npz 且覆盖 SSP1/2/**4**/5。
  - `scripts/analysis/08_harvest_block_diag.py` —— 0.25° 方块成因、Ouachita 空洞、
    面积守恒核账。
  - `scripts/analysis/09_luh2_source_look.py` —— LUH2 源数据原貌(harvest + states)。
  - `scripts/analysis/10_harvest_time_index_check.py` —— k=−1 索引验证、2050 台阶、
    2100 断崖。
- 一次性检查:`check_anchor2023`、`check_natveg_zero`、`check_zero_cause`、
  `decomp_change`、`harvest_weight_diff`、`inspect_target`、`area_ours_vs_source`、
  `verify_pft3`(均在 `scripts/analysis/`,各有对应 `jobs/submit_*.sbatch`)。
- `HARMONIZATION_SEUS_PILOT.md`、`REFERENCE.md`(§13 方法与证据)。
- 采伐:`s4_2_donwscale_LUH2harvest.py`;工作流:`.../Make_surface_data/my_workflow_Make_surface_data.md`。

## 9. 情景集合：为什么加 SSP3-7.0（记忆重点，2026-07-29）

**结论**:4km SEUS 模拟的情景集合定为 **SSP1-1.9 / SSP2-4.5 / SSP3-7.0 / SSP5-8.5**。
SSP4-6.0 的土地利用产物保留在盘上,但**不进入实验**——配不到气候强迫。

### 9.1 为什么 SSP4-6.0 走不通

TESSFA(`/projects/hpcl-cli185/proj-shared/TESSFA`)整树搜 `*460*` 零命中,
只有 ssp119/126/245/370/585 五条,正好是 **AR6 WG1 评估的核心五条**。

根因不在 TESSFA 而在上游:**SSP4-6.0 是 ScenarioMIP Tier 2**(自愿),实际跑的
CMIP6 模式极少,没有可降尺度的源数据。Tier 1 只有 SSP1-2.6 / SSP2-4.5 /
SSP3-7.0 / SSP5-8.5 四条是强制的。**所以补齐 ssp460 气候基本没希望,不要等。**

### 9.2 为什么选 SSP3-7.0 顶替

| 理由 | 说明 |
|---|---|
| **情景一致性**(决定性) | 气候和土地利用回到同一条 SSP 路径,延续 §2"harvest 与土地利用配对"的原则。若拿 ssp370 气候配 SSP4-6.0 土地利用,则 land-use × climate 不自洽,是这类实验最不能犯的错 |
| 数据齐全 | TESSFA 里 SE 域四条全 1032/1032/1032 完整(见 9.3) |
| 文献可比 | 四条全是 AR6 核心情景 |
| 强迫跨度 | 1.9/4.5/**7.0**/8.5 比原 1.9/4.5/**6.0**/8.5 更宽 |

**代价**:SSP3 与 SSP4 叙事差异大(SSP3 高人口/低单产/无土地保护,全球土地利用
变化最剧烈;SSP4 治理两极化,变化温和),且 ssp370 是 AerChemMIP 的高气溶胶情景
(SO₂/NOx/BC 全程高位),会经由氮沉降、散射辐射比例、雪面黑碳影响 ELM。这是换
情景带来的真实差异,不是误差。

### 9.3 配套气候强迫(TESSFA)

**用 `CanESM5` + `TESSFA2`**,四条各 Prec/Solr/TPHWL 1032 个月文件(2015-01~2100-12),
单情景约 578 GB。

```
CanESM5_ssp{119,245,370,585}_r1i1p1f1_DBCCA_Daymet_TESSFA2
```

两个坑:

1. **`TESSFA2` 才是 SEUS,不是 TESSFA1。** 靠 netCDF header 确认:
   `domain.lnd.TESSFA_SE.4km.1d` 与 `surfdata.TESSFA_DOMAIN2.4km.1d` 都是
   625×361 = 225,625 gridcell。TESSFA1/DOMAIN1 是另一个更大的域(PT)。
2. **`MIROC-ES2L_ssp585_..._TESSFA2` 残缺,别用。** 只有 `TPHWL3Hrly` 目录
   (815/1032,散落全程缺 217 个月,`2088-10` 截断在 80 MiB 整),
   `Precip3Hrly`/`Solar3Hrly` 目录根本不存在。生产于 2026-07-18 中断后搁置。
   MIROC 的 ssp119/245/370 是完整的,可作第二个 ensemble 成员,但 ssp585 要重跑。
   `E3SM-1-1` 缺 ssp119 和 ssp245,不适合本组合。

**网格不同,datm 必须重映射**:气候是 TESSFA_SE 361×625 @ 4km 投影网格,陆面是
SEUS 324×504 @ 1/24° 经纬网格。覆盖关系已核对(`scripts/analysis/plot_grid_coverage_tessfa.py`,
图 `outputs/figures/grid_coverage_TESSFA_SE_vs_SEUS.png`):

| | 经度 | 纬度 |
|---|---|---|
| TESSFA_SE | −100.0000 ~ −74.0000 | 25.0000 ~ 40.0000 |
| SEUS | −94.9792 ~ −74.0208 | 24.0208 ~ 37.4792 |

边界余量:西 **+5.02°**、东 **+0.02°**、北 **+2.52°**、南 **−0.98°**。

**南边界差 1°,但不影响。** TESSFA_SE 止于 25.0°N,SEUS 到 24.02°N,差出最下面
**24 行 / 12,096 格**——按 `PFTDATA_MASK` 统计,其中**陆地格点为 0**,全落在佛州
半岛以南的海面。**TESSFA_SE 覆盖了 SEUS 全部 76,582 个陆地格点。**

这条 25.0°N 南界与 NLCD 源网格一致(§7 相关:`REFERENCE.md` 记 SEUS 裁出 300 行,
比 324 行目标网格短 24 行——正是同样这 24 行),目标网格是刻意向南多留 1° 海面。

⚠️ **东边界只富余 0.02°(约半格)**,是四条边里最紧的。若日后 SEUS 网格东界东移,
这条边会最先失去覆盖。

### 9.4 LUH2 ssp370 harvest 的获取

`luh.umd.edu` 自 2026-07-28 起 80/443 双端口 `Connection refused`(连 07-24 成功
下载过的 URL 也一样;同节点 github/esgf/www.umd.edu 均正常,故是 UMD 主机问题)。

改从 **DKRZ 的 ESGF 副本**取,同一产品:`source_id=UofMD-landState-AIM-ssp370-2-1-f`
(`-2-1-f` 即 LUH2 **v2f**),`v20171005`,文件名与 UMD 版逐字相同。THREDDS
fileServer URL **直接返回 200,不需要任何 ESGF 凭证**——生成的 ESGF wget 脚本里那套
OpenID/MyProxy/Java 证书机制完全用不上,只需要它给的 URL 和 SHA256。
见 `jobs/download_luh2_ssp370.sbatch`(已内置 sha256 校验,UMD 作 fallback)。

**不要用 LUH v3 顶替。** ESGF 上的 `UofMD-landState-3-*` 是 CMIP7 世代产物,三处
不兼容:(a) 情景段起始年是 **2022** 而非 2015,而 `02` 里
`LUH_SSP_YEAR0=2015` 是写死的,套上去会**静默取错时间片**;(b) 情景改用 `h`/`vl`
等强迫水平标签,与 SSP-RCP 无 1:1 对应;(c) 另外四套是 v2f,混版本会让情景间差异
混入产品版本差异——正是 `REFERENCE.md` 那条"产品差距 >> 情景差距"的同类陷阱。
分辨率两者都是 0.25°,v3 **不是**分辨率升级。

### 9.5 待查 —— 已查,见 §11.3

SSP3_RCP70 的 `HARVEST_SH1` 均值 **0.004102**,低于 SSP4_RCP60(0.006051)和
SSP2_RCP45(0.005076)。SSP3 在全球尺度是土地利用变化最剧烈的情景,但 SEUS 域内
采伐强度并非最高。单个均值不足以下结论(主信号在 `PCT_NAT_PFT` 组成变化,harvest
只是一路),但跨情景对比时应专门核查:换成 SSP3 后 SEUS 域的情景间 spread 到底有
没有变大。

**结论(2026-08-03)**:spread 变大了。SSP3 是四条里离其他情景最远的一条,也是唯一
方向相反的一条(树减、农田增)。采伐强度不是最高,但采伐本来就是次要信号。详见
§11.2 / §11.3。

---

## 10. 待办 / 未做

- 只做了 **2024–2100 未来段**;若要完整 1850–2100 单文件,需把目标 1850–2023 拼在前面。
- **urban/城市化**未表达(option A);若需要,得改 ELM schema 为时变 land-unit(需确认 ELM 版本支持)。
- harvest 未来段目前是 `02` 内部重实现的下采样;`s4_2` 本身尚未扩到 2100(文档标"待实现")。

---

## 11. 四情景成品对比与采伐诊断（记忆重点，2026-08-03）

对**交付的四个 .nc 文件本身**做的对比(不是 interim diag npz),情景集合
SSP1-1.9 / SSP2-4.5 / SSP3-7.0 / SSP5-8.5。脚本 `scripts/analysis/07..10`。

### 11.1 情景之间只有两处不同（先确认这个,再谈别的）

所有静态 land-unit 变量(`AREA`/`LANDFRAC_PFT`/`PCT_NATVEG`/`PCT_CROP`/
`PCT_URBAN`/`PCT_LAKE`/`PCT_GLACIER`/`*_P`)在四个文件间**逐字节相同**——它们从
同一个目标文件拷贝。`GRAZING` 也是跨情景相同**且时间恒定**(沿用 2023)。

→ 情景信号**全部**在 `PCT_NAT_PFT` 组成 + 五个 `HARVEST_*` 里。自然植被总量恒为
**131.843 Mha**,五个功能组只在这个固定盘子里互相搬。

### 11.2 组成变化:三种走向,不沿辐射强迫梯度排列

净变化 2024→2100 [Mha]:

| 组 | SSP1-1.9 | SSP2-4.5 | SSP3-7.0 | SSP5-8.5 |
|---|---|---|---|---|
| Tree | +4.97 | **+10.95** | **−3.15** | +2.41 |
| Grass | −4.88 | −8.65 | +0.61 | −1.02 |
| Crop | −0.14 | −2.39 | **+2.57** | −1.54 |
| Shrub | +0.04 | +0.09 | −0.03 | +0.14 |
| Bare | +0.00 | −0.00 | −0.00 | +0.01 |

- **SSP2-4.5 才是最激进的造林情景,不是 SSP1**(树 +13.6%,草 −27.8%,农田 −14.8%)。
- **SSP3-7.0 是唯一反向的**(树 −3.9%,农田 **+15.8%**),农田扩张集中在 2040–2080。
- SSP1 与 SSP5 都温和造林但机制不同:SSP1 草→树(农田几乎不动);SSP5 同时挤压草
  和农田,且是唯一 Bare 明显上升的(+2.9%)。
- PFT 层面只有 8 个 PFT 有变化,树的增减由 PFT1/PFT7 承担,草的损失几乎全在
  PFT13。这是 §13 谐调的预期行为(Chen 定组总量,组内比例冻结在 NLCD 2023)。

2100 年两两分歧(`D = 0.5Σ|P_a,g − P_b,g|`,面积加权,pp of natveg column):
SSP3 离所有人都最远(对 SSP2 **13.3**,对 SSP1 12.7),而 SSP1↔SSP2 只有 8.2。
**分歧不沿辐射强迫梯度排列**——SSP5-8.5 坐在 SSP2 和 SSP3 中间。

⚠️ **2024 年四个情景已经不同**(树 80.23–80.73 Mha)。共同锚是 **NLCD 2023**,
Chen 趋势从 2024 起就在作用。做基准年比较时不要拿 2024 当共同起点。

### 11.3 采伐:几乎全是 SH1

累计 2024–2100:SSP2 **111.2** > SSP5 105.0 > SSP3 89.8 > SSP1 78.4 Mha。

五类里 **SH1(次生成熟林)占几乎 100%**,VH1 仅 0.14–0.16 Mha,**VH2/SH2/SH3 恰好
为零**。根因在 LUH2 的状态场:SEUS 的 `primf ≈ 0`(历史上早被砍光),只有 `secdf`。
所以"只有 SH1 有值"是源头的物理事实,不是我们丢了东西。

### 11.4 累计采伐图上的 0.25° 方块 = LUH2 的分辨率,不是 bug

下采样公式(`_distribute_conservatively`):

```
frac_i = F_c × w_i × Σ_c(area) / Σ_c(w·area)        w = tree_share × natveg
         └─┬─┘   └────────────┬────────────┘
      LUH2 定总量          我们的森林图定位置(块内均值为 1,面积守恒)
```

`F_c` = **LUH2 文件里该 0.25° 格当年的原始值**(`luh[var].isel(time=hidx)`,
见 `02_harmonize_seus.py` 的 `coarse = ...` 那行),一个粗格一个数。LUH2 是 0.25°,
目标是 1/24°,正好 **6×6 细格对一个粗格**,且两者边界都落在 0.25° 整数倍上(细格边
从 24.0 / −95.0 起),完全对齐。

块内输出 = 常数 `F_c` × 归一化权重,而 SEUS 的森林权重在 0.25° 内相当均匀 → `F_c`
主导图案。实测粗格间累计采伐面积 CV = **0.536**。**方块画年均还是累计都不会消失**,
它就是 LUH2 的真实分辨率。

### 11.5 Ouachita 空洞:LUH2 与 NLCD 的森林分类分歧

**lat 34.5–35.0, lon −94.5..−94.0**(阿肯色西部),2×2 个 LUH2 粗格 = 144 个细格。
五个采伐变量在**全部 85 年上精确为零**,而紧邻格累计 0.6–1.4,断崖式落差。

查 `states.nc`(2015)就明白:那 4 格 `primf = 0` **且** `secdf = 0`,被归为
`primn` 0.46–0.73 + `range` 0.11–0.20。**LUH2 认为那里没有森林**,没有森林状态就
不可能有采伐。而我们的 NLCD 图在同一位置 144 格全有 natveg,树占比 **77.1%**(2024)
/ 88.4%(2100),树面积 0.196 Mha;往东一格树占比 84.2%,LUH2 却给了正常采伐。

→ 这是两套数据对森林的**分类分歧**,不是下采样缺陷。四个情景空洞位置完全一致
(洞在 LUH2 状态场里,跨 SSP 共用)。影响范围小(0.25 Mha),留着并记录即可。

### 11.6 没有采伐被丢掉;守恒超额 = 那个已知因子,量化为 +2%

担心的失效模式是粗格内 `Σ(w·area)=0` 会让 `valid` 全 False、整块归零、源采伐静默
丢失。**实测 0 个这样的粗格**。只有 39 个粗格是"LUH2 有采伐但完全无 natveg"
(沿海/水域),未落地 0.03–0.16 Mha,可忽略。

用**静态** natveg 反推的落地面积是 LUH2 源的 **101.7–102.5%**。这正是文件属性
`harvest_natveg_convention` 说的 `natveg_static/natveg_annual` 因子(下采样时归一化
用的是逐年谐调 natveg,受城市化影响逐年缩小)。**跨情景比较不受影响**(同一约定),
但绝对采伐量不要直接引用。

### 11.7 时间索引 k=−1 已验证;2050 台阶与 2100 断崖都在源里

把年总量与 LUH2 源在三种位移下对齐,比 RMS 差 [Mha]:

| 情景 | shift −1 | shift 0 | shift +1 |
|---|---|---|---|
| SSP1-1.9 | **0.0115** | 0.0298 | 0.0424 |
| SSP2-4.5 | **0.0263** | 0.0709 | 0.0971 |
| SSP3-7.0 | **0.0056** | 0.0351 | 0.0506 |
| SSP5-8.5 | **0.0356** | 0.0667 | 0.0879 |

**shift −1 四个情景全赢 2.5–3 倍**,映射正确。残差(0.4–2.7%)就是 §11.6 那个因子。

- **2050 台阶在源里**:2049→2050 单年下跌 5.4–9.0%(四情景同时),之后趋势恢复。
  正好卡在整十年边界。在产品里出现在标签年 **2051**,正是 k=−1 预测的位置。
- **2100 断崖是 LUH2 文件的最后一条记录**:文件 85 条,覆盖日历 2015–2099;输出
  2100 → `cal=2099` → `hidx=84` = 末条。2095–2098 平滑,末条掉 **22–34%**(SSP1
  −22%、SSP2 −34%、SSP3 −29%、SSP5 −32%)。`min(cal, 2099)` 的截断在 2024–2100
  **从未触发**,不存在重复取末年的问题。我们忠实复现了源里的断崖。

**未决**:2100 那年采伐突降三成对 ELM 是个不自然的强迫。三个选项——(a) 保持原样
(忠于源,当前状态);(b) 2100 沿用 2099 的值;(c) 输出截到 2099。取决于实验怎么用
最后一年。

### 11.8 复现

```bash
sbatch jobs/submit_scen_final_cmp.sbatch        # 07 两阶段:算 npz + 画三张图
sbatch jobs/submit_scen_final_cmp_plot.sbatch   # 07 只重画(读 npz,不再读 600MB)
sbatch jobs/submit_harvest_block_diag.sbatch    # 08 方块/空洞/守恒诊断
sbatch jobs/submit_luh2_source_look.sbatch      # 09 LUH2 源数据原貌图
sbatch jobs/submit_harvest_tidx_check.sbatch    # 10 时间索引验证
```

产出:`outputs/figures/fig_scen_final_cmp_{trajectory,maps,harvest}.png`、
`fig_luh2_source_look.png`、`fig_harvest_time_index_check.png`;
中间量 `outputs/interim/scenario_compare_final.npz`。

⚠️ 这五个 job 用的是 `-p serial -q normal`(公共分区),不是专属分区。

---

## 12. 容器格式转成经典 NetCDF3（记忆重点，2026-08-21）

四个正式情景的 landuse.timeseries 从 **NETCDF4 + zlib level 4** 重写成
**NETCDF3_64BIT_OFFSET**，与历史文件同容器。同批的 `SSP4_RCP60` 成品删除。

### 12.1 为什么改 —— 不是修故障，是拆雷

**当前配置下 NetCDF4 本来就读得了**，这点先说清楚，免得以后误以为修过一个 bug：

- `e3sm.exe` 链接的是 netCDF-C 4.9.2（`libnetcdf.so.19`），`has-nc4=yes`；
- lnd 用的是 `pio_typename = "netcdf"`（串行 netCDF-C 路径）。

雷在于：`libpnetcdf.so.4` 同样被链接，模块栈里也有 `parallel-netcdf`，而
**pnetcdf 读不了 NetCDF4**。4km 域 75,920 个陆地格，把 `PIO_TYPENAME` 换成
`pnetcdf` 提 I/O 性能是迟早会做的动作，那一刻这些输入会直接失败，而且失败点
离原因很远。经典格式在所有 `PIO_TYPENAME` 下都能读，所以对齐容器是把这个
隐患提前拆掉。

### 12.2 对齐了哪三项

| | 转换前 | 转换后（= 历史文件） |
|---|---|---|
| 格式 | NETCDF4 + zlib 4 | `NETCDF3_64BIT_OFFSET` |
| `time` | 固定长度 | **unlimited**（record 维） |
| `_FillValue` | 21 个变量带 `NaN` | **无** |

那 21 个 `_FillValue = NaN` 是 xarray 默认编码加的，不是科学量；历史文件一个
都没有。除这三项外，变量集合、顺序、dtype、维度、其余属性、全部数值都不动。

代价是体积：每情景 0.15 → 约 2.2 GB，四个共约 +8.7 GB（`/projects` 当时余
39 TB）。压缩省的那点盘远不值得换一个格式陷阱。

### 12.3 怎么做的 —— 只换容器，不重跑管线

**没有**重跑 `jobs/submit_landuse_future*.sbatch`。这批文件下游已经用过、验过
（§11），重跑存在产出数值不同的可能，那会让 §11 的所有结论失去对应物。

也**没有**用 `nccopy`：`-k nc6 -u` 能改格式和 unlimited，但删不掉
`_FillValue`，还要再套一次 `ncatted`，两步比一步难验证。改为单遍逐变量拷贝：

- `scripts/to_classic_netcdf.py` —— 转换；
- `scripts/check_classic_rebuild.py` —— 验证（权威）；
- `jobs/submit_to_classic.sbatch` —— 两阶段驱动（`-p serial -q normal`）。

两个实现细节值得记住，都不是可有可无的：

1. **必须关掉 auto-masking**（`set_auto_maskandscale(False)`）。源文件
   `_FillValue = NaN`，netCDF4-python 默认会把等于 fill 的值 mask 掉，写出时
   masked 位置被填成目标类型的默认 fill（9.97e36）——正好在这次声称"一个数
   都不动"的变量里静默改值。
2. **按源 chunk 读**。`PCT_NAT_PFT` 的 HDF5 分块是 `[20, 4, 81, 126]`，逐条
   时间读会让每个 chunk 被反复解压最多 80 次。实测 15 秒 vs 331 秒。

流程是"先写临时文件 → 验 → 原件改名 `.nc4-orig` 保留 → 新件就位 → 再验一次"，
四个文件全过 phase A 才进 phase B，任何一步不过就停。

### 12.4 生成脚本已同步改（本次不用它重跑）

`scripts/02_harmonize_seus.py` 的写出改为：

```python
enc = {v: {"_FillValue": None} for v in out_ds.variables}
out_ds.to_netcdf(out, format="NETCDF3_64BIT", encoding=enc,
                 unlimited_dims=["time"])
```

去掉 `zlib`（正是它把 xarray 逼进 NETCDF4）、显式指定 format、抑制
`_FillValue`、`time` 设 unlimited。**只影响将来的重新生成**。

⚠️ **format 字面量是 `"NETCDF3_64BIT"`，不是 `"NETCDF3_64BIT_OFFSET"`。**
后者是 netCDF4-python 的拼法，xarray 不接受（`ValueError: unexpected
format=...`），但写出来的文件读回去 `file_format` 报的正是
`NETCDF3_64BIT_OFFSET`。两个名字指同一个格式，写的时候只有前者管用。
本地 xarray 2026.7.0 与 Pathfinder `make_surfdata_pf` 的 2026.4.0 都是如此。

### 12.5 保留的差异：`string256` vs `nchar`

`input_pftdata_filename` 的字符维度，SSP 文件叫 `string256`（xarray 按串长自动
命名），历史文件叫 `nchar`。**故意不改**：它不影响 pnetcdf 兼容性，也不影响
ELM 读取，而改维度名比改容器格式风险大得多。

### 12.6 验证怎么算过

`SEUS_halfdeg/qa/check_format_equivalence.py` 是现成的第二意见，但它的退出码
不能直接用，输出要读而不是信，有两个原因：

1. 它把有意为之的 `_FillValue` 删除报成普通 FAIL —— 它没有"预期变更"的概念；
2. 它的数值检查是 `np.array_equal`，只要数组里有一个 NaN 就返回 False，哪怕
   两边逐位相同（NaN != NaN）。§6 记录这批文件无 NaN，所以这项预期会 PASS，
   但不该拿它当依据。

所以判定权交给 `scripts/check_classic_rebuild.py`：它逐字节比较（NaN 与自己
的副本逐字节相等），并要求每一处结构差异只能是那两项之一；同时打印每个变量的
NaN 计数，万一真有 NaN，也能看出第二意见的失败是假阳性而不是真问题。
第二意见只做集合约束：FAIL 必须是那两个已知名字的子集。

