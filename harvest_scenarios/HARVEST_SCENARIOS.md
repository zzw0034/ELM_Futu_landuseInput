# Management 情景构建 —— RF / DF / RH

在已有的 4 个 SSP `landuse.timeseries`(2024-2100,见 `../FUTURE_LANDUSE_TIMESERIES.md`)基础上,
再做 3 个额外的土地管理干预情景:**RF(重造林)**、**DF(毁林反事实)**、**RH(采伐减半)**,
覆盖全部 4 个 SSP,共 **12 个文件**。

情景定义于 **2026-08-19** 全部锁定(见 §1)。截至本文档写就时,
**已完成 SSP1_RCP19 一个 SSP 的冒烟测试(3 个文件),其余 3 个 SSP 待跑**(见 §6 状态)。

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
RF/DF 只改 `PCT_NAT_PFT`,RH 只改 5 个 `HARVEST_*`。其余所有场
(`PCT_URBAN`/`PCT_CROP`/`PCT_NATVEG` 等)在本数据集里**本身就是时间不变的 2-D 场**,
结构上就碰不到——所以城市和耕地是**自动被保护的**,不需要额外写排除逻辑。

PFT 索引约定(见 `../src/elm_landuse/chen_classes.py` 的 `ELM_PFT_NAMES`):
**tree = natpft 1..8**,**grass = natpft 12,13,14**,crop = natpft 15。

### RF(Reforestation,重造林)

对每个格点,把 1850 年比 2023 年多出来的那部分森林**只从现有草地**转回来:

```
full_increment(g) = min(forest_1850(g) − forest_2023(g), grass_2023(g))
ramp(t)           = 2024→2050 线性 0→1(27 年,对齐 2050 net-zero),2051-2100 恒为 1
increment(g,t)    = full_increment(g) × ramp(t)

RF_forest_k(g,t) = Default_forest_k(g,t) + increment(g,t) × w_tree_k(g)    k ∈ tree 1..8
w_tree_k(g)      = p(g,k,1850) / forest_1850(g)          按该格点自身 1850 年森林构成分配

RF_grass_k(g,t)  = Default_grass_k(g,t) − increment(g,t) × w_grass_k(g)    k ∈ {12,13,14}
w_grass_k(g)     = p(g,k,2023) / grass_2023(g)           按该格点自身 2023 年草地构成分配
```

**2051-2100 不是独立冻结的状态**,而始终是 `Default(t) + 增量`,
所以 `RF(t) − Default(t)` 在任意时刻都等于"我们主动造的这片林",
不会被 Default 自身 SSP 轨迹的演化污染。

> **实现上的一个必要偏差:草地扣减要按当年 Default 实际有的量 clip。**
> `increment(g,t)` 是用 **2023 年**的草地构成算出来的目标,但 Default 自己的 SSP 轨迹
> 会让草地逐年变化——某些格点到 2050 年草地已经比 2023 年少,"要转的草"不够。
> 此时只能转实际存在的那部分(`removed_k = min(desired_k, Default_grass_k(g,t))`),
> **森林增加的量按实际扣到的草地量记**,而不是按目标量记——这样 sum-to-100 才严格守恒。
>
> **全域实测(SSP1_RCP19,job 466554_0):590 万 cell-year 中 771,734 个(13.1%)被 clip**,
> 达成率如下——注意**它在 ramp 结束后仍持续下降**:
>
> | 年份 | 2035 | 2050(ramp 结束) | 2075 | 2100 |
> |---|---:|---:|---:|---:|
> | 达成/名义目标 | 98.9% | **89.5%** | 83.3% | **79.3%** |
>
> 这是**正确行为而非缺陷**:不能去转一个情景里已经不存在的草地,否则就得动耕地,
> 违反 grass-only 约束。但由此产生一条**必须写进论文的性质**:
> **`RF − Default` 不是恒定的管理增量,2050→2100 会自行衰减约 11 个百分点**,
> 而这个衰减来自记账约束(草地被 Default 自己用掉了),**不是碳动力学**。
> 解释造林碳汇时若不说明,会被误读成"造林效果在减弱"。机制详见下方小节。
>
> (早前文档写的"低约 4%、再漂移 0.25%"是在**一小块空间窗口 + SSP3-7.0** 上测的,
> 全域尺度不成立,已废弃。)

#### 衰减的机制:目标锚在 2023,而 Default 自己在消耗草地

先看一个由公式直接推出的事实。ramp 结束后 `increment(g,t) = full_increment(g) = min(deficit, grass_2023)`,
而分到第 k 个草地 PFT 的目标是

```
desired_k(g,t) = full_increment(g) × w_grass_k(g)
               ≤ grass_2023(g) × [p(g,k,2023) / grass_2023(g)]
               = p(g,k,2023)
```

也就是说,**我们要的从来不超过该草地 PFT 在 2023 年的量**。所以 clip 只会在一种情况下触发:
**Default 自己在第 t 年的该草地 PFT 已经少于它 2023 年的值。**

而 SSP1-1.9 恰好就在大规模这么做(实测,%-of-cell 单位):

| 年份 | 2023(基准) | 2024 | 2035 | 2050 | 2075 | 2100 |
|---|---:|---:|---:|---:|---:|---:|
| 草地 | 1,840,617 | 1,819,635 | 1,710,266 | 1,661,152 | 1,592,999 | **1,537,565** |
| 森林 | 4,649,764 | 4,678,803 | 4,824,186 | 4,855,927 | 4,931,554 | **4,964,523** |
| 耕地 | 931,573 | 923,341 | 886,678 | 903,649 | 894,877 | 916,574 |
| 相对 2023 的单向草地缺口 | — | 28,952 | 172,185 | 269,698 | 358,330 | **413,520** |

**草地 −303,052,森林 +314,759,耕地基本不动**——Default 自己就在把草地变成森林,几乎一比一。
SSP1-1.9 是最"绿"的情景,本身就含大量自然/政策造林。

于是形成一个直接的资源竞争:**RF 想转的那块草地,Default 自己已经先转成森林了**。
年份越靠后,Default 转得越多,留给 RF 的越少,达成率就越低——这正是 79.3% 这个数的来源。

两个推论:

1. **这不是 bug,反而是物理上应该的**:那块地在 Default 里已经是森林了,RF 不该、也无法
   "再造一次林"。真正的管理增量本来就只剩下 Default 没做掉的那部分。
2. **不同 SSP 的衰减幅度会不同**,取决于该情景自身的草地→森林转换有多强。SSP1-1.9 是
   最绿的,预期衰减最大;SSP3-7.0/SSP5-8.5 里 Default 可能反而在毁林,草地不减甚至增加,
   达成率应该更接近 100%。**四个 SSP 跑完后要把这张达成率表逐个补上**,不能用
   SSP1-1.9 的数字代表全部。脚本现在会为每个 SSP 打印 2050 和 2100 的达成率。

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

## 2. 最终成品(计划中,尚未生成)

不在本文件夹内——沿用主项目的 `outputs/` 树:

```
../outputs/processed/harvest_scenarios/
  landuse.timeseries_SEUS_1_24deg_nlcd2elm_{SSP}_{RF,DF,RH}_simyr2024-2100.nc
```

其中 `{SSP}` ∈ `SSP1_RCP19` / `SSP2_RCP45` / `SSP3_RCP70` / `SSP5_RCP85`,
`{RF,DF,RH}` 三个情景 → 共 **12 个文件**。

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
> 12 个文件合计约 **26G 写入 + 26G 读取**,而计算本身只是几遍 elementwise 运算。
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
- 脚本 `scripts/build_harvest_scenarios.py` 和作业 `jobs/submit_harvest_scenarios.sbatch`
  **已按锁定的定义重写**。
- **冒烟测试(`--array=0`,job `466554_0`,SSP1_RCP19)已 COMPLETED / exit 0**,
  耗时 00:02:20,MaxRSS 17.6GB,产出 3 个文件(RF/DF/RH),各项校验全绿:
  sum-to-100 max|err| 6e-06(与 Default 自身相同)、DF 树 PFT 与 5 个 `HARVEST_*` 精确为 0、
  RH 比值精确 0.500000、C3/C4 兜底恰好命中预测的 5 个格点。
- **`../outputs/processed/harvest_scenarios/` 目前只有 SSP1_RCP19 的 3 个文件,
  其余 3 个 SSP(共 9 个文件)尚未生成。**
- 冒烟测试之后又改了三处(见 git 历史):`clone_structure` 改为**写临时文件 → 校验 → 原子
  `os.replace()`**;sum-to-100 校验的 mask 从自指的 `PFT-sum>0` 换成独立的 `PCT_NATVEG>0`;
  `--mem`/`-t` 换成实测值。**SSP1_RCP19 的 3 个文件是用改动前的版本生成的**——数值逻辑
  未变(改的只是校验和落盘方式),但如果要求"12 个文件全部由同一版本产出",
  应连 `--array=0` 一起重跑。
- **旧设计产出的 3 个文件已于 2026-08-19 17:06 删除**。经过:v1(压缩格式原地改写)产出的
  3 个损坏文件先前已删;v2 脚本(经典格式)最终在 **2026-08-19 14:08 成功跑完**,
  产出 `PRESERVE` / `HALFHARVEST_SSP370` / `REFOREST1850` 三个各 2.2G 的**有效**文件
  (不是损坏文件)。因本次重新设计后三者与新的 RF/DF/RH **无一对应**
  (`PRESERVE` 与 DF 概念相反、`HALFHARVEST` 系数和 SSP 覆盖都不同、`REFOREST1850`
  缺 grass-only 约束且渐变年数/分树种方式都不同),且无任何 ELM case/run 引用它们
  (已查 `e3sm_cases`/`e3sm_run` 下全部 `user_nl_elm`/`lnd_in`,零命中),
  留在同一目录里会与新的 12 个文件混淆(尤其 `PRESERVE` 这个名字极易被误当作森林保护情景),
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
- **RF**:2024 年切片应与 Default 2024 年**完全相同**(ramp=0);2050 年及以后
  `RF − Default` 的森林总量应**接近但通常略低于** `full_increment`
  (草地 clip 导致,见 §1 RF 小节的说明——实测约低 4%,且 2050→2100 还会再漂移约 0.25%),
  **不要**把"精确等于 `full_increment`"当作验收标准。
- **DF**:全部 77 年的 tree PFT(natpft 1-8)应恒为 0;5 个 `HARVEST_*` 应恒为 0。
- **RH**:5 个 `HARVEST_*` 对全部 77 年求和后,新/旧比值应精确为 **0.5**。
  **注意不要按单一年份切片算比值**——`HARVEST_VH2`/`SH2`/`SH3` 在 SEUS 域内本来就接近全零
  (见 `../FUTURE_LANDUSE_TIMESERIES.md` §11.3),单年切片可能除以零得到 `nan`,不代表数据错。
- 全部 12 个文件都要确认**能被完整读回**(不只是写完没报错)——这正是 §4 那次的教训,
  写入"看起来成功"不等于文件没坏。

---

## 8. 相关文件

- `scripts/build_harvest_scenarios.py` —— 构建脚本(经典 NetCDF 格式,12 文件)
- `jobs/submit_harvest_scenarios.sbatch` —— Slurm 提交脚本
- `../FUTURE_LANDUSE_TIMESERIES.md` —— 上游的 4 个 SSP Default landuse.timeseries 怎么来的
- `../HARMONIZATION_SEUS_PILOT.md` §13 —— Default 情景所用的 Chen2022 谐调框架(本流程**不**重跑它)
- `../future_climate/README_cpl_bypass_future.md` §6.1 —— 同一类 NetCDF4 分块写入坑的更早案例
- `../outputs/processed/harvest_scenarios/` —— 产出数据存放位置(不在本文件夹内,见 §2)
