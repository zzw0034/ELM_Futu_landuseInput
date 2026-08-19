# Harvest 管理情景构建 —— 工作记录（记忆文档）

在已有的 4 个 SSP `landuse.timeseries`(2024-2100,见 `../FUTURE_LANDUSE_TIMESERIES.md`)基础上,
再做 3 个假设性管理干预情景:**保护森林**、**减半采伐**、**重造林**。2026-08-18 规划并写好构建
脚本,截至本文档写就时**尚未成功运行产出**(见 §5 状态)。

---

## 0. 最终成品(计划中,尚未生成)

不在本文件夹内——沿用主项目根目录下现有的 `outputs/` 树(和其余 4 个 SSP landuse.timeseries
放一起,不是本次整理进 `harvest_scenarios/` 的对象):

```
../outputs/processed/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_PRESERVE_simyr2024-2100.nc
../outputs/processed/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_HALFHARVEST_SSP370_simyr2024-2100.nc
../outputs/processed/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_REFOREST1850_simyr2024-2100.nc
```

三个文件都是已有 SSP3-7.0(`landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_simyr2024-2100.nc`)
的"骨架"复制品——维度/变量/dtype/YEAR 范围(2024-2100,77年)完全一致,只改 `PCT_NAT_PFT`
和/或 `HARVEST_*` 五个变量。

---

## 1. 三个情景的定义(和用户逐条确认过,2026-08-18)

| 情景 | PCT_NAT_PFT | HARVEST_* | 备注 |
|---|---|---|---|
| **保护森林**(preserve) | 冻结在 2023 年状态(所有未来年份复制同一份) | 五个变量全部置零 | 用户确认的定义,无争议 |
| **减半采伐**(half harvest) | 不变,沿用 **SSP3-7.0** 自己的轨迹 | 五个变量整体 ×0.5 | 用户选 SSP3-7.0 做基准——四个 SSP 里唯一土地利用**反向**(毁林、农田扩张)的一条,用它测试"采伐减半能不能抵消 SSP3 的毁林趋势"更有针对性 |
| **重造林**(reforest) | 从 2023 年状态**逐年线性过渡**到 **1850 年**状态,过渡期 **30 年**(2024→2053),2053 年之后保持 1850 年状态不变 | 五个变量全部置零(assistant 默认假设,已向用户说明,用户未反对) | 1850/2023 两个年份的 `PCT_NAT_PFT` 直接从历史文件 `landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc` 里取,不需要额外推算 |

**重造林插值公式**:

```
alpha(year) = clip((year - 2023) / 30, 0, 1)
PCT_NAT_PFT(year) = (1 - alpha) × [2023年状态] + alpha × [1850年状态]
```

逐格点、逐 17 个 PFT 类型独立线性插值,纯数值混合,**不是**模拟森林演替/生长过程。因为 2023
和 1850 两张图各自在每个格点都已经 sum-to-100,线性组合自动保持 sum-to-100,不需要额外归一化。

---

## 2. 构建脚本

- `scripts/build_harvest_scenarios.py` —— 三个情景都在这一个脚本里,读历史文件取 1850/2023
  年 `PCT_NAT_PFT` 锚点,读 `SSP3_RCP70` 未来文件当结构模板,分别算出三份新数据,各自建一个
  全新的输出文件。
- `jobs/submit_harvest_scenarios.sbatch` —— Slurm 提交脚本(资源配置见 §4)。

2026-08-18 把这两个文件和本文档一起,从项目根目录的 `scripts/`/`jobs/`(以及 Pathfinder 上
图方便临时放的 `co2_ndep_ssp_forcing/`)整理进这个自成一体的 `harvest_scenarios/` 子目录,
和 `future_climate/` 的组织方式保持一致(各自有自己的 `scripts/`、`jobs/`)。整理前本地和
Pathfinder 上这个脚本放的位置并不一致,顺带修正了。

---

## 3. 踩过的坑:v1 压缩 NetCDF4 原地改写,文件全损坏

**第一版实现**(已废弃):用 `shutil.copyfile` 复制 `SSP3_RCP70` 模板文件,再用
`nc4.Dataset(path, 'r+')` 打开、按年份循环给 `PCT_NAT_PFT`/`HARVEST_*` 赋值。

**结果**:三个文件全部损坏——`preserve`/`reforest` 文件从 158MB 涨到约 300MB(接近翻倍),
`HARVEST_SH1/SH2/SH3` 等变量重新读取时直接报 `RuntimeError: NetCDF: HDF error`,
`preserve` 文件甚至连 `HARVEST_VH1` 也读不出来。

**根因**:`SSP3_RCP70` 模板文件本身是 **NetCDF4 压缩分块格式**(`zlib` + `chunking=[39,162,252]`)。
对这种文件用 `r+` 模式做原地部分改写(尤其跨块、多次分片写入),HDF5 层面容易出问题——这
和本项目 `future_climate/README_cpl_bypass_future.md` §6.1 里记录的气候强迫构建那次"NetCDF4
分块写入静默损坏数据"是**同一个坑**,只是这次是直接读取报错,不是静默错误。

**修复(v2,当前脚本版本)**:不再对已压缩文件做原地编辑,改成**从零构建一个全新的经典格式
(`NETCDF3_64BIT_OFFSET`,无分块无压缩)文件**,每个变量一次性整体赋值写入,不做多次分片写。
和气候强迫那次的"真正修复方式"完全一致——避开 HDF5 分块写入这一整类问题,而不是去调
分块缓存大小这种治标不治本的参数。

---

## 4. Slurm 资源配置(几轮讨论定下来的)

**为什么必须用 Slurm,不能在登录节点跑**:v2 脚本第一次是直接在 Pathfinder 登录节点上跑的
(没提交作业),被系统杀掉(`exit 137`,内存不足)。`PCT_NAT_PFT` 是一个 77×17×324×504
float64 数组,单个就有约 1.7GB,加上前后几个中间数组,峰值内存明显超出登录节点的限额——
这正是项目 `AGENTS.md`/`CLAUDE.md` 里"内存密集型任务不要在登录节点跑,要走 Slurm"这条规则
要防的情况,第一次没照做,踩了坑之后改用 `sbatch` 提交。

**资源配置的几轮修正**(核数/时长都被质疑并改过,记录下推理过程,不只是最终数字):

| 项目 | 初版 | 最终 | 为什么改 |
|---|---|---|---|
| `-c`(核数) | 8 | **1** | 初版是照抄 `submit_landuse_future_ssp370.sbatch` 模板抄的,没针对这个脚本重新核算。脚本里 `OPENBLAS_NUM_THREADS=1`/`OMP_NUM_THREADS=1` 已经关掉了 numpy 的多线程,没有 `multiprocessing`,没有子进程,netCDF4/HDF5 默认也不会自己开线程——**没有任何一步能用上第二个核**,`-c 2` 那个"留个 I/O 余量"的说法被追问后确认也是站不住脚的,最终定为 `-c 1`。 |
| `--mem` | 64g | **64g**(没变) | 峰值实际估计只有几 GB(最大数组约 1.7GB),16g 本来就够,但用户选择保留 64g 留更大安全边际——毕竟刚经历过一次意外 OOM。这是用户的判断,不是核算出来的最优值。 |
| `-t`(墙钟时间) | 00:30:00 / 00:40:00 | **03:00:00** | 用户直接要求改成 3 小时,没有进一步核算实际需要多久(脚本本身预计几分钟到十几分钟量级)——纯粹是留出充足余量,避免时间不够被 Slurm 杀掉。 |

**最终 `#SBATCH` 配置**:

```bash
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=64g
#SBATCH -t 03:00:00
```

---

## 5. 当前状态(截至文档写就时)

- v1 产出的 3 个损坏文件已删除(`rm`,确认过是本 session 生成的新文件,不是删的别人的东西)。
- v2 脚本(经典格式、单核资源配置)已经写好、测试过语法,**但还没有成功跑完过一次**——
  第一次 Slurm 提交(job 465188)排队中(`ReqNodeNotAvail`)被用户主动 `scancel` 取消,
  用户想先想清楚再跑。
- **`outputs/processed/harvest_scenarios/` 目录目前是空的**,不要假设这三个文件已经存在。

## 6. 怎么跑

```bash
ssh pathfinder "cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios && sbatch jobs/submit_harvest_scenarios.sbatch"
```

跑完之后建议核对(脚本自带的验证输出会打印,但独立复核更稳):
- `PCT_NAT_PFT` 逐格点 sum-to-100(natveg>0 处)
- `preserve` 2024 年切片应和历史文件 2023 年锚点逐字节相同
- `reforest` 2053 年切片应和历史文件 1850 年锚点逐字节相同,2100 年应和 2053 年相同(保持不变)
- `half_harvest` 五个 `HARVEST_*` 变量,对全部 77 年求和后新/旧比值应精确为 0.5(注意:不要
  按单一年份切片算比值——`HARVEST_VH2`/`SH2`/`SH3` 在 SEUS 域内本来就接近全零,见
  `../FUTURE_LANDUSE_TIMESERIES.md` §11.3,单年切片可能除以零得到 `nan`,不代表数据错)
- 三个文件都要确认**能被完整读回**(不只是写完没报错)——这正是 v1 那次的教训,写入"看起来
  成功"不等于文件没坏。

---

## 7. 相关文件

- `scripts/build_harvest_scenarios.py` —— 构建脚本(v2,经典格式)
- `jobs/submit_harvest_scenarios.sbatch` —— Slurm 提交脚本
- `../FUTURE_LANDUSE_TIMESERIES.md` —— 上游的 4 个 SSP landuse.timeseries 怎么来的
- `../future_climate/README_cpl_bypass_future.md` §6.1 —— 同一类 NetCDF4 分块写入坑的更早案例
- `../outputs/processed/harvest_scenarios/` —— 产出数据存放位置(不在本文件夹内,见 §0)
