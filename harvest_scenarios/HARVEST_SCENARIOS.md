# Management 情景构建 —— RF / DF / RH

在已有的 4 个 SSP `landuse.timeseries`(2024-2100,见 `../FUTURE_LANDUSE_TIMESERIES.md`)基础上,
再做 3 个额外的土地管理干预情景:**RF(重造林)**、**DF(毁林反事实)**、**RH(采伐减半)**。

**RF 与情景无关,只有 1 个文件、四个 SSP 共用;DF 和 RH 各 SSP 一份。
合计 1 + 4×2 = 9 个文件。**

情景定义于 **2026-08-19** 锁定(见 §1),**9 个文件当天已全部产出并通过校验**(见 §6)。RF 当天经过一次重新设计
(从"Default + 增量"改为情景无关的独立轨迹 + 禁伐)。见 §6 状态。

> **本文档 2026-08-19 全面重写**,替换了 2026-08-18 那版基于
> `PRESERVE`/`HALFHARVEST_SSP370`/`REFOREST1850` 的旧设计——三个情景的定义全部改变(见 §7)。
> 旧设计**产出过 3 个有效文件,但已于 2026-08-19 删除**(与新设计无一对应,且无任何
> ELM case 引用;详见 §6)。因此不存在需要兼容/作废的既有结果,可以放心全量重跑。
> **§4(NetCDF 写入坑)和 §5(Slurm 资源)保留自旧版**,那两节是操作层教训,与情景定义无关,依然有效。

---

## 0. 来源:proposal Table 1

proposal 把这三个情景定位成 *"additional land management that can potentially be used for
carbon offset projects"*,每个都要和同一个 SSP 的 **Default**(无额外管理,即现有的 4 个
SSP landuse.timeseries 本身)对比,差值即该管理措施的碳汇潜力。

**与 proposal 字面文本的两处偏离**(项目层面早已定下,非本次决定):

- **用实际建好的 4 个 SSP**(`SSP1_RCP19` / `SSP2_RCP45` / `SSP3_RCP70` / `SSP5_RCP85`),
  不是 proposal 字面的 SSP1-2.6 等——SSP3-7.0 已在项目全局替代缺气候强迫的 SSP4-6.0。
- **用 2023 作为历史末年/干预锚点**(pipeline 实际的历史截止年),不是 proposal 字面的 2015。

---

## 1. 三个情景的定义(2026-08-19 锁定)

### 总体思路

三个情景都是对现有 4 个 Default 文件的**后处理变换**,**不需要重跑 §13 Chen2022 谐调器**。
RH 只改 5 个 `HARVEST_*`;RF 和 DF 都改 `PCT_NAT_PFT`,而且**都把 `HARVEST_*` 置零**
(RF 是造林后不再采伐,DF 是森林已清空、没有可采的树)。其余所有场
(`PCT_URBAN`/`PCT_CROP`/`PCT_NATVEG` 等)在本数据集里**本身就是时间不变的 2-D 场**,
结构上就碰不到——所以城市和耕地是**自动被保护的**,不需要额外写排除逻辑。

PFT 索引约定(见 `../src/elm_landuse/chen_classes.py` 的 `ELM_PFT_NAMES`):
**tree = natpft 1..8**,**grass = natpft 12,13,14**,crop = natpft 15。

### RF(Reforestation,重造林)—— 情景无关的单一文件

**RF 是一个与情景无关的政策处方,四个 SSP 的 RF run 共用同一个文件。**
它不是叠加在各 SSP 自身轨迹上的扰动,而是**替换**掉土地覆盖轨迹:

```
full_increment(g) = min(forest_1850(g) − forest_2023(g), grass_2023(g))
ramp(t)           = 2024→2050 线性 0→1(27 年),2051-2100 恒为 1

RF_tree_k(g,t)  = p(g,k,2023) + full_increment(g) × ramp(t) × w_tree_k(g)    k ∈ tree 1..8
w_tree_k(g)     = p(g,k,1850) / forest_1850(g)        按该格点 1850 年森林构成

RF_grass_k(g,t) = p(g,k,2023) − full_increment(g) × ramp(t) × w_grass_k(g)   k ∈ {12,13,14}
w_grass_k(g)    = p(g,k,2023) / grass_2023(g)         按该格点 2023 年草地构成

其余 PFT(bare / shrub / crop)= 冻结在 2023 年值
所有 5 个 HARVEST_*            = 0
```

**关键量**:

> ⚠️ **单位警告:下表全部是 77×324×504 逐格点 `PCT_NAT_PFT` 百分比直接求和,
> 不是物理面积,不能当 km² 用。** 实测换算:1850 森林的 %-求和是 5,643,976,
> 但用 `AREA × LANDFRAC × (NATVEG/100)` 面积加权算出的真实值是 **976,420 km²**——
> 相差约 5.8 倍,而且换算比例本身还随格点纬度分布小幅变化(1850 森林分布 vs 2023
> 森林分布,换算系数分别是 0.1730 和 0.1725,不是一个常数),**不能用固定系数简单换算**。
> 若论文要报真实面积,必须重新面积加权求和,不能直接拿下表数字乘系数。

| | 值(%-of-cell 求和,非 km²) |
|---|---:|
| 1850 年森林 | 5,643,976 |
| 2023 年森林(= RF 起点) | 4,649,764 |
| 1850 缺口(**逐格点正缺口**,`Σ max(f1850−f2023, 0)`) | **1,173,576** |
| **grass-only 可达目标** | **820,075** = 补上**逐格点缺口的 69.9%** |
| **RF 2050 年后的平台值** | **5,469,839** = 1850 年**森林范围的 96.9%** |

> **这两个百分比的分母不同,已经错过两次,务必仔细核对。**
>
> `69.9%` = **820,075 / 1,173,576**。分子分母是**同一组格点、同一种"缺口"算法**
> (`max(f1850−f2023, 0)`,逐格点算、负的清零、再加总),分子只是多加了一层
> "不能超过该格点现有草地" 的限制(`min(缺口, grass_2023)`)。所以这个比例回答的是
> "受限于每个格点自己的草地存量,理论造林上限里,有多少实际能造出来"。
>
> `96.9%` = **5,469,839 / 5,643,976**,分母是 1850 年**森林总量**(不是缺口),
> 回答的是"造完之后,SEUS森林恢复到了1850年规模的百分之多少"。
>
> **不要**把 820,075 除以任何"全域净差"类型的数字(如 `Σf1850 − Σf2023`)去凑百分比——
> 那种净差会把"部分格点2023森林反而比1850多"的量悄悄抵消掉,和 `full_increment`
> 逐格点单向构造的口径不一致,算出来的比例(会得到错误的82.5%)没有实际含义。
> 写成"恢复到 1850 extent 的 82.5%"也是**错的**(那个数其实是 96.9%)。

**为什么不再是"Default + 增量"**(2026-08-19 改):旧设计里各 SSP 自己的轨迹会和我们抢同一批草地,
导致交付的增量在 ramp 结束后持续衰减——实测 2100 年只剩名义值的 **71.6%–95.2%**(随情景而异)。
一个政策目标不该因为基线世界自己也在造林就缩水。新设计从 2023 锚点独立构造,
**按构造精确达标,不可能 clip**:对草地 PFT k 的扣减是
`full_increment × ramp × w_grass_k ≤ grass_2023 × w_grass_k = p(k,2023)`,
所以草地最低到 0 而绝不为负,树增加的正好等于草减少的。
实测 sum-to-100 误差 **5.68e-14**(机器精度,比 Default 自身的 5.55e-06 还好三个数量级)。

**为什么是单一文件**:已验证四个 Default 文件**只有 `PCT_NAT_PFT` 和 5 个 `HARVEST_*` 不同**
(其余包括 `GRAZING` 全部逐字节相同)。RF 恰好覆盖这两类——`PCT_NAT_PFT` 用情景无关轨迹,
`HARVEST_*` 全部置零——**于是没有任何情景相关的内容残留**,一个文件即可服务全部四个 run。

**为什么 `HARVEST_* = 0`**:造林的目的就是恢复**并保护**森林,不再采伐。
这同时也是单一文件成立的前提(采伐是最后一个情景相关字段)。
另外这让 **RF 和 DF 构成一对对称的书挡**:最大森林碳储 vs 零森林碳储,两者都不采伐,Default 夹在中间。

> **解读时必须注意的两点(写文章时都要说)**
>
> **(1) 禁伐覆盖的是全部森林,不只是新造的那部分。** `HARVEST_*` 是逐格点速率、作用于该格点
> 全部木本 PFT,没有地块身份,所以 `HARVEST_*=0` 意味着连 2023 年就已存在的 **4,649,764**
> 也一起停伐——**是新造林(820,075)面积的 6.7 倍**。因此 `RF − Default` 度量的是
> **"造林 + 全域禁伐"的合计效应**,不是造林本身,而且它与 **RH 重叠**(RH 是同一批采伐 ×0.5)。
> 情景名必须写成 **"forest restoration and protection"**,不能只叫 reforestation。
>
> **本项目的立场(2026-08-19 决定):只声称合计效应,不拆分。** 算力受限,不做
> 额外的 NH(`PCT_NAT_PFT`=Default + `HARVEST_*`=0)情景,所以**没有干净的分解路径**。
> `(RF−Default) − 2×(RH−Default)` 只能当 **sensitivity / approximation**,
> **不得当作精确分解**:ELM 里采伐、product pool 衰减、再生长、面积变化互相耦合,碳响应不线性;
> 而且 RH 用的是 Default 的 PFT 轨迹、RF 用的是恢复后的轨迹,两者的采伐作用在**不同面积**的
> 森林上,乘 2 更不成立。若将来确实需要拆分,正确做法是补跑 NH:
> `禁伐效应 = NH − Default`,`保护下的恢复效应 = RF − NH`,三项自洽且无需线性假设
> (代价是实验数 16 → 20,算力 +25%)。
>
> **(2) `RF − Default` 还吸收了各 SSP 自身的土地漂移。** 因为 RF 是替换而非扰动,
> 差值里含有"该 SSP 本来会发生的土地变化被抹掉"这一项,而这一项**量级大且正负不同**:
>
> | SSP | 2100 森林 | 相对 2023 |
> |---|---:|---:|
> | SSP1-1.9 | 4,964,523 | +314,760 |
> | SSP2-4.5 | 5,285,435 | **+635,671** |
> | SSP3-7.0 | 4,459,526 | **−190,237** |
> | SSP5-8.5 | 4,777,311 | +127,547 |
>
> 跨度 826,145,和造林目标(820,075)几乎一样大。**必须把两项都报告**,让读者能自己拆开。
> 特别注意 SSP2-4.5:基线 2100 年已达 5,285,435,而 RF 平台是 5,469,839,**只差 184,404**。

**这个设计带来的一个独有能力**:四个 RF run 共用同一片陆面,**唯一差别是气候**——
所以 `Sim_SSPxx_RF` 之间互比是一个**纯净的气候效应对比**(同一片恢复后的森林在不同气候下固碳)。
旧设计做不到这一点,因为四个 RF 的陆面各不相同。

**为什么基准是 1850 而不是 1985**:实测 SEUS 数据,1985 vs 2023 森林面积净变化只有
**−0.28%**,单向 gross loss(22,824 km²)≈ gross gain(20,545 km²),76,582 个陆地格点里
超过一半在两个方向上抖动——这是 NLCD 分类噪声或 SEUS 人工松林轮伐周期的特征,不是真实毁林。
用 `max(1985−2023,0)` 会系统性地只挑抖动的一侧尾巴。1850 的森林占比(占 SEUS 陆地 72.3%)
另有独立交叉验证:CLM/LUH2 体系的全球 0.5° raw 数据集
`mksrf_landuse_rc1850`(`/projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/rawdata/AA_mksrf_landuse_rc_1850-2015_06062017_LUH2/`)
在同一 bbox 给出 71.8%,**相差不到 1 个百分点**,而两者数据来源/方法/分辨率完全独立。

**为什么不改用 mksurfdata 的 raw PFT 底图**:那份 raw 数据本身**也只是一个 1850 年重建**,
不是"排除人类活动的真实自然植被"——和我们自己的 1850 数据是同一类东西,只是来源不同。
既然森林占比只差 <1pp,换过去要额外解决 0.5°↔1/24° 的分辨率/海岸线口径问题
(粗网格海岸线判定导致 bbox 内总陆地面积相差约 20%),换来的却是几乎一样的答案。

**为什么只转草地,不含灌木/耕地**:实测过两个替代方案。加灌木只多 3,000 km²
(141,603→144,603,**+2.1%**)——即使在草地不够用的 14,293 个格点里,灌木也只能补上剩余缺口的
4.8%(SEUS 灌木本来就少),不值得为这点收益增加一套 sub-PFT 分配逻辑。完全不设限
(草地+灌木+耕地)能达到 203,496 km²(约等于 1850 全部缺口,其中**耕地独占约 29%**)——
**这是一个真正的分岔**,而且 proposal 字面文本("we converted them back to forests")
其实并未排除耕地,grass-only 是我们自己加的解读。仍然保留 grass-only,理由是
**proposal 明确把 RF 定位成 "potentially used for carbon offset projects"**,
它必须代表一个**可信、可实施**的干预——真实的造林碳汇项目针对的是边际/撂荒地,
不是在产耕地,把大片耕地退耕当 offset 情景会被质疑可信度。

**为什么是渐变而不是瞬时**:在 ELM 源码里核实过
(`dynPatchStateUpdaterMod.F90:269` 的 `update_patch_state`)——面积增大的 patch,
其单位面积碳被**稀释**:`var = var*old/new + seed*dwt/new`,而 seed 只有
`leafc_seed_param = 1 gC/m²`、`deadstemc_seed_param = 0.1 gC/m²`
(`ComputeSeedMod.F90:36-37`),相对成熟林的 ~10⁴ gC/m² 等于从零开始。
**瞬时造林在转换当年一点碳都不增加**,只是把现有森林密度摊薄再慢慢长回来;
27 年渐变让每年的稀释扰动只有 1/27。
**写作时必须保留的 caveat**:ELM 每个 gridcell 每个 PFT 只有一个 patch,没有林龄结构
(除非用 FATES),所以新造林永远和现有成熟林**平均**成一个密度——渐变只能减小这个假象,不能消除。

**论文可用的一句话**:

> The forest restoration and protection scenario prescribes a common land-management
> trajectory across all SSPs: forest cover is restored from the shared 2023 baseline
> toward the 1850 forest extent by 2050 using available grassland only, held constant
> thereafter, with wood harvest disabled across all forests throughout the simulation.

必要时再补一句量化(注意分母):

> Under the no-cropland constraint the prescribed restoration closes 69.9% of the
> grid-cell-wise 1850-to-2023 forest deficit, bringing regional forest cover to 96.9%
> of its 1850 extent.

### DF(Deforestation counterfactual,毁林反事实)

**不是**冻结/保护森林,而是**相反**:从 2024 年起每年把森林**全部清空**转成草地,
锁死到 2100 不许长回来,并把 `HARVEST_*` 清零。

```
DF_forest_k(g,t)  = 0                                                     t = 2024..2100, k ∈ tree 1..8
DF_grass_k(g,t)   = Default_grass_k(g,t) + Default_forest(g,t) × w_k(g)   k ∈ {12,13,14}
w_k(g)            = p(g,k,2023) / grass_2023(g)
                    (grass_2023(g)=0 的格点用 SEUS 全域面积加权兜底 C3=85.0% / C4=15.0%;
                     实测只有 5 个格点触发,占 76,558 个有林格点的 0.01%)
DF_HARVEST_*(g,t) = 0                                                     t = 2024..2100(历史段 1850-2023 不变)
```

- **逐年跟随 Default,不是把 2023 快照冻结前推**:`DF_grass(g,t)` 每年重新从
  `Default_forest(g,t)` 推导,所以 Default 自己在任何未来年份"本该有"的森林也一并转给草地,
  `Default(t) − DF(t)` 在任意年份都干净地等于"该年实际存在多少森林",不被过期的 2023 基准污染。
- **瞬时而非渐变**(与 RF 不同):机制上没问题——面积**缩小**的 patch 走
  `dynPatchStateUpdaterMod.F90` 里 `dwt<0` 的 `flux_out` 分支,碳干净地进入 conversion flux
  和 product pool,没有稀释假象;而且瞬时清除本来就是真实皆伐的物理类比。
- **永久锁零,不许恢复**:这是刻意的理论上界,不是真实砍伐后的碳轨迹(真实次生演替会部分挽回)。
- **只转草地**(不用灌木,也不按比例分给所有非森林 PFT):草地(牧场/干草地)是 SEUS 森林转出的
  最主要现实去向;用灌木会因其自身木质碳回长而低估毁林信号,用裸地则会引入不物理的土壤碳崩溃和
  反照率/粗糙度/ET 冲击,把碳差值弄脏。

**为什么 DF 可以"不设限"而 RF 要限制在草地**:这个不对称是**刻意的,不是不一致**。
RF 必须**可信**,因为 proposal 把它定位成 "potentially used for carbon offset projects",
是一个别人真能出钱执行的干预。DF 在 proposal 里**没有这层定位**——它唯一的作用是当
`Default − DF` 的分母,是一把**理论上界**的尺子,不是要"执行"的方案。
量级参照:DF 清掉 802,181 km² 森林 = **SEUS 全部陆地的 59.4%**——这个数字若当作可信情景会显得荒谬,
但作为"衡量现存全部森林资产价值"的会计工具恰恰是对的。

> **由此产生的硬性写作要求**:任何写作都**必须明确标注 DF 的产出是理论上界**
> (theoretical upper bound),不能暗示它是"预期会发生"的量。否则 `Default − DF`
> 会被读成"某项具体政策的预期收益"(不可信),而不是"若保护完全不存在时全部处于风险中的碳"
> (这才是它真正的含义)。

### RH(Reduced Harvest,减少采伐)

```
RH_HARVEST_*(g,t) = Default_HARVEST_*(g,t) × 0.5     全部 5 个变量,全部年份
```

**这是刻意偏离 proposal 字面文本的决定(2026-08-19)**。proposal 写的是
*"extend the interval of wood harvest by 50%"*(延长采伐间隔 50%),而**本项目选择直接把
采伐速率减半**,不做"间隔延长 50%"那个换算。

两者的换算关系(理解清楚才不会写错):设每轮采伐固定生物量 `A`、间隔 `T` 年,年化速率 `= A/T`。

| 操作 | 年速率 | 等价的间隔变化 |
|---|---|---|
| proposal 字面("间隔 +50%") | `rate/1.5`(降 33%) | `T → 1.5T` |
| **本项目采用(速率减半)** | **`rate × 0.5`(降 50%)** | **`T → 2T`(间隔翻倍,即延长 100%)** |

已对照 `dynHarvestMod.F90`/`CNHarvest` 确认:ELM 里采伐是数据驱动的年速率,
Fortran 端**没有"间隔"这个可调参数**,间隔的概念只存在于本数据预处理层——所以无论选哪个,
实际操作都是在这一层缩放 `HARVEST_*`。

> **写作要求**:描述成 **"annual wood harvest rate halved"**,或者等价地
> **"rotation interval doubled"**。
> **绝对不要**写成 proposal 的 "extending the time between wood harvest by 50%"
> ——我们做的是间隔**翻倍**,不是延长 50%,照抄 proposal 会与实际做的事不符。
> 另外 ELM 的连续速率 formulation 根本无法表示离散轮伐,所以"轮伐间隔"这个说法本身
> 始终只是一个便于理解的等价表述,不是模型里真实存在的机制。
> 情景名 "Reduced Harvest" 本身是准确的。

---

## 2. 最终成品(已生成,见 §6)

不在本文件夹内——沿用主项目的 `outputs/` 树:

```
../outputs/processed/harvest_scenarios/
  landuse.timeseries_SEUS_1_24deg_nlcd2elm_RF_simyr2024-2100.nc          # 1 个,四个 SSP 共用
  landuse.timeseries_SEUS_1_24deg_nlcd2elm_{SSP}_{DF,RH}_simyr2024-2100.nc   # 每 SSP 各 2 个
```

其中 `{SSP}` ∈ `SSP1_RCP19` / `SSP2_RCP45` / `SSP3_RCP70` / `SSP5_RCP85`
→ 共 **1 + 4×2 = 9 个文件**。**RF 文件名里没有 SSP 标签,这是刻意的**——
它与情景无关,四个 RF run 的 `flanduse_timeseries` 都指向同一个路径。

每个文件都是对应 SSP Default 文件的"骨架"复制品——维度/变量/dtype/YEAR 范围
(2024-2100,77 年)完全一致,只改 `PCT_NAT_PFT` 和/或 `HARVEST_*`。

**注意 `SSP4_RCP60` 被刻意排除**:TESSFA 里没有对应的气候强迫,项目全局已用 SSP3-7.0 替代它。

---

## 3. 0.5° 版本怎么做

**先在 4km 上做完(即本脚本的产出),再原样走 Default 已定的那套 0.5° 聚合流水线**
(见 `seus_task_backlog` 任务 3),**不要**在 0.5° 网格上独立重算 RF/DF/RH 的变换。理由:

1. 和"0.5° 永远是 4km 的聚合,不独立生成"这条项目原则保持一致。
2. 这样得到的 0.5° 版本描述的是**同一组**被造林/被清林的 4km 格点换个粗分辨率看,
   而不是用粗网格量重新定义的另一个干预。

> **已知的数学副作用**:RF 的 `min()` 是凹函数,按 Jensen 不等式,
> "先聚合再取 min" 得到的造林面积会**系统性地大于** "先在 4km 取 min 再聚合"。
> 两者不是同一个东西,**不能拿来互相校验对错**,只能选一种口径贯彻到底——本项目选前者(4km 先做)。
> RH 是纯线性运算,不受影响,两种顺序结果完全一样。

---

## 4. 踩过的坑:压缩 NetCDF4 原地改写,文件全损坏(保留自旧版,依然有效)

**第一版实现**(已废弃):用 `shutil.copyfile` 复制模板文件,再用
`nc4.Dataset(path, 'r+')` 打开、按年份循环赋值。

**结果**:文件全部损坏——体积从 158MB 涨到约 300MB(接近翻倍),
`HARVEST_SH1/SH2/SH3` 等变量重新读取时直接报 `RuntimeError: NetCDF: HDF error`。

**根因**:模板文件本身是 **NetCDF4 压缩分块格式**(`zlib` + `chunking=[39,162,252]`)。
对这种文件用 `r+` 做原地部分改写(尤其跨块、多次分片写入),HDF5 层面容易出问题——这和
`../future_climate/README_cpl_bypass_future.md` §6.1 记录的气候强迫构建那次
"NetCDF4 分块写入静默损坏数据"是**同一个坑**,只是这次是直接读取报错,不是静默错误。

**修复(当前脚本沿用)**:不再对已压缩文件做原地编辑,改成**从零构建全新的经典格式
(`NETCDF3_64BIT_OFFSET`,无分块无压缩)文件**,每个变量一次性整体赋值写入,不做多次分片写。
和气候强迫那次的"真正修复方式"完全一致——避开 HDF5 分块写入这一整类问题,
而不是去调分块缓存大小这种治标不治本的参数。

---

## 5. Slurm 资源配置(保留自旧版,依然有效)

**为什么必须用 Slurm,不能在登录节点跑**:早先版本第一次是直接在 Pathfinder 登录节点上跑的
(没提交作业),被系统杀掉(`exit 137`,内存不足)。`PCT_NAT_PFT` 是一个
77×17×324×504 float64 数组,单个就有约 1.7GB——这正是项目 `AGENTS.md`/`CLAUDE.md` 里
"内存密集型任务不要在登录节点跑"这条规则要防的情况。

| 项目 | 值 | 依据 |
|---|---|---|
| `--array` | **0-3** | 一个 SSP 一个 task(索引对应脚本里的 `ALL_SSPS`)。见下方并行说明 |
| `-c`(核数) | **1** | 脚本里 `OPENBLAS_NUM_THREADS=1`/`OMP_NUM_THREADS=1` 已关掉 numpy 多线程,没有 `multiprocessing`,没有子进程,netCDF4/HDF5 默认也不开线程——**没有任何一步能用上第二个核** |
| `--mem` | **96g** | **实测值**(按 task 计)。冒烟测试 job `466554_0`(SSP1_RCP19,COMPLETED)实测 **MaxRSS = 17.6GB**。事前按数组大小推导得 ~9GB,**低了约一倍**——漏掉了 `clone_structure` 对**未 override 的变量要整块读入再写出**(RH 文件即整个 1.71GB 的 `PCT_NAT_PFT`),以及 netCDF4 返回 masked array 导致一次读取要付 data + mask + `np.array()` 拷贝三份。四个 SSP 数组形状完全相同,17.6GB 应可代表全部。96g 留约 5.5 倍余量——**高于数字所需,是刻意的**:serial 分区有数千空闲核,多要内存几乎不影响排队,而 OOM 被杀要重跑 |
| `-t`(墙钟) | **00:30:00** | **实测值**。同一次冒烟测试单个 SSP(3 个文件)耗时 **00:02:20**,30 分钟约 13 倍余量。原来的 04:00:00 是未实测的占位值 |

```bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=96g
#SBATCH -t 00:30:00
#SBATCH --array=0-3
```

### 环境:不需要任何 module(不要加)

作业脚本里**故意不 load 任何 module**:

1. `~/.bashrc` 对非交互式 shell 会**提前 return**(`case $- in *i*) ;; *) return;;`),
   所以它里面的 `module load` 对批处理作业**根本不生效**——即使写 `source ~/.bashrc` 也没用。
2. conda 环境是**完全自包含**的:已用 `env -i`(彻底清空环境,连 `PATH`/`LD_LIBRARY_PATH` 都没有)
   验证过,能正常 import numpy 和 netCDF4,用的是它自带的 **libnetcdf 4.10.0 / libhdf5 2.1.0**。
3. **加载 `.bashrc` 里那些 module 反而有破坏风险**:那边是 `hdf5/1.14.5-mpi` 和
   `netcdf-c/4.9.2-mpi-h5f`,与本 python 链接的版本不同(HDF5 甚至跨了大版本:1.14 vs 2.1),
   通过 `LD_LIBRARY_PATH` 注入不匹配的 libhdf5 是典型的动态链接故障场景。
   那些 module 是给**编译 ELM/PFLOTRAN** 用的,不是给这个 python 环境用的。

本项目 `jobs/` 下所有已跑通的 sbatch 脚本都是同一模式(绝对路径 conda python + 零 module)。

### 并行(job array)说明

脚本的 per-SSP 循环体**完全独立**(共享输入只读,输出文件名互不重叠),所以按 SSP 拆成
4 个 array task 是安全的。脚本接受一个可选参数选择单个 SSP:

```bash
build_harvest_scenarios.py              # 4 个 SSP 串行(不传参)
build_harvest_scenarios.py 2            # 只做 ALL_SSPS[2]
build_harvest_scenarios.py SSP2_RCP45   # 同上,按名字
```

> **加速幅度存疑,不要期待 4 倍**:这个任务是**写 I/O 密集**而非 CPU 密集——
> `clone_structure` 每产出一个文件要完整读一遍源文件再写出一个**未压缩**的 2.2G 经典格式文件,
> 9 个文件合计约 **20G 写入 + 20G 读取**,而计算本身只是几遍 elementwise 运算。
> 4 个 task 并发访问同一个 NFS 文件系统(且该文件系统已 99% 满)可能是**争抢**而不是线性扩展。
>
> **可靠的收益是故障隔离**:某个 SSP 失败不再拖垮其余三个,重跑也只需
> `sbatch --array=<i> jobs/submit_harvest_scenarios.sbatch` 补那一个。
>
> 想改回单作业串行:删掉 `--array` 那行,并去掉 python 调用后面的
> `"${SLURM_ARRAY_TASK_ID}"` 参数即可。

---

## 6. 当前状态

- 情景定义(§1)**已于 2026-08-19 全部锁定**,包括所有边界情况(0/0 权重兜底等),没有遗留的开放设计问题。
- **9 个文件已全部产出并通过校验(job `466639`,2026-08-19,4 个 array task 全部
  COMPLETED / exit 0)。**

| Task | SSP | 耗时 | MaxRSS |
|---|---|---:|---:|
| 466639_0 | SSP1_RCP19 + **共用 RF** | 2:50 | 13.3 GB |
| 466639_1 | SSP2_RCP45 | 2:24 | 13.2 GB |
| 466639_2 | SSP3_RCP70 | 2:10 | 14.9 GB |
| 466639_3 | SSP5_RCP85 | 2:15 | 13.3 GB |

  **并行几乎没有加速**(并发 2:10–2:50 vs 之前单 task 串行 2:20)——印证了这活是写 I/O
  密集、四个 task 争抢同一节点的 NFS 带宽。故障隔离仍是真收益。
  内存实测 13.2–14.9GB(低于冒烟测试的 17.6GB,因为新 RF 不再复制 `default_pft`),
  96g 余量约 6.4 倍。

- **独立复核 RF 文件**(不依赖脚本自身输出)全部通过:
  2024 森林 = 4,649,763.5(精确等于 2023 锚点)、2050 = **5,469,838.7**(精确等于平台值)、
  2050 与 2100 切片**逐字节相同**、sum-to-100 误差 **5.68e-14**、最小 PFT 值 **0**、
  5 个 `HARVEST_*` 全为 0、**无 `.tmp.` 残留**(原子写入路径工作正常)。
  DF 四个 SSP 的树 PFT 与 5 个 `HARVEST_*` 精确为 0;RH 四个 SSP 比值精确 **0.500000**。

- **`RF − baseline`(文章要解释的核心数,%-of-cell 单位)**:

| SSP | 2050 | 2100 | 2050→2100 |
|---|---:|---:|---:|
| SSP1-1.9 | +613,912 | +505,316 | −108,596 |
| SSP2-4.5 | +531,874 | **+184,404** | **−347,470** |
| SSP3-7.0 | +929,437 | **+1,010,313** | **+80,876** |
| SSP5-8.5 | +775,043 | +692,528 | −82,515 |

  **跨情景差 5.5 倍**(184,404 → 1,010,313)。**SSP3-7.0 是唯一随时间增大的**——
  它的基线在毁林,差距越拉越开;其余三个基线自己在造林,差距缩小。
  **SSP2-4.5 到 2100 只剩 +184,404**,说明那个世界的基线自己几乎把森林恢复到了 RF 的水平,
  额外干预空间很小——这个数会直接决定该情景的碳汇结论,必须在文章里点出。

- **旧设计产出的 3 个文件已于 2026-08-19 17:06 删除**。经过:v1(压缩格式原地改写)产出的
  3 个损坏文件先前已删;v2 脚本(经典格式)最终在 **2026-08-19 14:08 成功跑完**,
  产出 `PRESERVE` / `HALFHARVEST_SSP370` / `REFOREST1850` 三个各 2.2G 的**有效**文件
  (不是损坏文件)。因本次重新设计后三者与新的 RF/DF/RH **无一对应**
  (`PRESERVE` 与 DF 概念相反、`HALFHARVEST` 系数和 SSP 覆盖都不同、`REFOREST1850`
  缺 grass-only 约束且渐变年数/分树种方式都不同),且无任何 ELM case/run 引用它们
  (已查 `e3sm_cases`/`e3sm_run` 下全部 `user_nl_elm`/`lnd_in`,零命中),
  留在同一目录里会与新的 9 个文件混淆(尤其 `PRESERVE` 这个名字极易被误当作森林保护情景),
  故删除。**生成它们的旧脚本完整保存在 git commit `dd82b07`**,需要时可复现。

## 7. 怎么跑

```bash
ssh pathfinder "cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios && sbatch jobs/submit_harvest_scenarios.sbatch"
```

提交后是 4 个 array task(每个 SSP 一个),日志在
`../outputs/logs/harvest_scenarios_<jobid>_<task>.{out,err}`。
只重跑某一个 SSP:`sbatch --array=2 jobs/submit_harvest_scenarios.sbatch`。

脚本自带验证输出,但独立复核更稳。跑完之后建议核对:

- `PCT_NAT_PFT` 逐格点 sum-to-100(natveg>0 处)——RF/DF 都是"森林增加多少草地就减少多少"的
  等量互换,按构造应严格守恒。
- **RF**(注意:RF 已不再基于 Default,以下是**绝对值**判据,不是与 Default 的差):
  2024 年森林应等于 **2023 锚点 4,649,763.5**(ramp=0);
  2050 年应等于**平台值 5,469,838.7**;2050–2100 各年切片应**逐字节相同**;
  5 个 `HARVEST_*` 应恒为 0;`PCT_NAT_PFT` 最小值应 ≥ 0。
  **按构造不存在 clip**,所以平台值必须精确命中,不接受"略低"。
- **DF**:全部 77 年的 tree PFT(natpft 1-8)应恒为 0;5 个 `HARVEST_*` 应恒为 0。
- **RH**:5 个 `HARVEST_*` 对全部 77 年求和后,新/旧比值应精确为 **0.5**。
  **注意不要按单一年份切片算比值**——`HARVEST_VH2`/`SH2`/`SH3` 在 SEUS 域内本来就接近全零
  (见 `../FUTURE_LANDUSE_TIMESERIES.md` §11.3),单年切片可能除以零得到 `nan`,不代表数据错。
- 全部 9 个文件都要确认**能被完整读回**(不只是写完没报错)——这正是 §4 那次的教训,
  写入"看起来成功"不等于文件没坏。

---

## 8. 相关文件

- `scripts/build_harvest_scenarios.py` —— 构建脚本(经典 NetCDF 格式,9 文件)
- `jobs/submit_harvest_scenarios.sbatch` —— Slurm 提交脚本
- `../FUTURE_LANDUSE_TIMESERIES.md` —— 上游的 4 个 SSP Default landuse.timeseries 怎么来的
- `../HARMONIZATION_SEUS_PILOT.md` §13 —— Default 情景所用的 Chen2022 谐调框架(本流程**不**重跑它)
- `../future_climate/README_cpl_bypass_future.md` §6.1 —— 同一类 NetCDF4 分块写入坑的更早案例
- `../outputs/processed/harvest_scenarios/` —— 产出数据存放位置(不在本文件夹内,见 §2)
