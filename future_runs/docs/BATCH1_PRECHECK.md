# 七个正式 case —— 预检记录

**批 1（ssp119 / ssp245 / ssp370）已于 2026-09-08 提交并运行中。**
**批 2（ssp585 / RF / DF）与批 3（RH）已创建并通过全部预检，未提交。**

批次划分（主结果优先，可改）：

| 批 | 情景 |
|---|---|
| **1（本次）** | Default **ssp119 / ssp245 / ssp370** |
| 2 | Default ssp585 + **RF** + **DF** |
| 3 | **RH** |

RF/DF/RH 共用 ssp370 的气象/CO2/Ndep，只差 landuse，放后批不影响主线。

## 建立方式

`cases/setup_production_case.sh <scenario>`，从 T4 `--keepexe` 克隆，
**三个 case 共用 T4 的生产构建**（`EXEROOT` 指向
`…/20260908_seus_4km_fut_t4_n20/bld`，md5 `e8b487b04a27adfd8f683359dfd73df5`），
各自独立 `RUNDIR`。脚本**不提交作业**。

## 预检结果（每项失败即退出）

| 检查 | ssp119 | ssp245 | ssp370 |
|---|---|---|---|
| A3 初始场 sha256 `20e9c29b…` | ✓ | ✓ | ✓ |
| landuse / CO2 / Ndep 文件存在 | ✓ | ✓ | ✓ |
| 气象目录 7 个变量文件 | ✓ | ✓ | ✓ |
| 源码对 `0be814f868`（已提交 + 工作树） | ✓ | ✓ | ✓ |
| exe md5 | ✓ | ✓ | ✓ |
| `RUNDIR` 已重指、`EXEROOT` 为 T4 构建 | ✓ | ✓ | ✓ |
| 13 项 xml 设置逐项核对 | ✓ | ✓ | ✓ |
| SourceMods 覆盖数 = 0 | ✓ | ✓ | ✓ |
| **`lnd_in`** 六项输入逐条 grep | ✓ | ✓ | ✓ |
| `sbatch --test-only` | ✓ 517994 | ✓ 517995 | ✓ 517996 |

13 项 xml：`RUN_TYPE=startup`、`RUN_STARTDATE=2024-01-01`、
`CONTINUE_RUN=FALSE`、`STOP_OPTION=nyears`、`STOP_N=11`、
`REST_OPTION=nyears`、`REST_N=11`、`RESUBMIT=6`、`DEBUG=FALSE`、
`NTASKS_LND=2560`、`MAX_MPITASKS_PER_NODE=128`、`DOUT_S=FALSE`、
`JOB_WALLCLOCK_TIME=04:00:00`。

**`lnd_in` 而不是 `user_nl_elm`**：前者才是模型真正读取的文件。

## 三者只在 4 个字段上不同

对三个 `lnd_in` 互相 diff，差异行仅有：

```
co2_file
flanduse_timeseries
metdata_bypass
stream_fldfilename_ndep
```

（另有一行 `!#` 注释，记录 build-namelist 命令里的 case 名，是元数据不是设置。）

`finidat`、`fsurdat`、`aero_file`、`stream_fldfilename_popdens`、
`stream_year_*_ndep`、三个 `check_*_consistency`、全部 history 设置在三者间
**逐字节相同**。

## `sbatch --test-only`

```
--time 04:00:00 -p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g \
  --constraint=BL --exclude=blc051,blc052 -N 20 -n 2560 -c 1
→ 2560 processors on nodes blc[081-100] in partition parallel
```

三个 case 的 `preview_run` SUBMIT CMD 与上述一致，仅 `.case.run` 路径不同。

## 建立过程中被 fail-closed 检查拦下两次

两次都是**我读取设置的方式错**，不是设置本身错——但两次都在 case 提交前停住，
这正是把 fail-open 改成 fail-closed 的目的：

1. `xmlquery` 多变量时按**字母序**返回，位置解析比错了对（报
   `RUN_TYPE is 'FALSE'`，那其实是 `CONTINUE_RUN` 的值）。改为逐个查询。
2. `JOB_WALLCLOCK_TIME` 是**按作业分组**的变量（`case.run` /
   `case.st_archive` / `case.post_run_io`），返回
   `04:00:00,04:00:00,04:00:00`。改为要求每个字段都相等。

两次的半成品 case 都已删除后重建（均无运行输出）。

## 提交方式（待确认后执行）

三个 case 各自 `./case.submit`，`RESUBMIT=6` 会自动接续后 6 段。
并发 3 个 × 20 节点 = **60 节点**。单 run 约 17.05 h 积分加段间排队。


---

# 批 2 与批 3（2026-09-08 创建，未提交）

| 批 | 情景 | CASEROOT | 状态 |
|---|---|---|---|
| 2 | ssp585 | `…_fut_ssp585` | 已建，预检通过，未提交 |
| 2 | RF | `…_fut_ssp370_RF` | 同上 |
| 2 | DF | `…_fut_ssp370_DF` | 同上 |
| 3 | RH | `…_fut_ssp370_RH` | 同上 |

四者与批 1 走同一个 `setup_production_case.sh`，通过同样的全部检查，
并新增 **`PIO_TYPENAME` 检查**：四个 case 均报告 "all 10 components netcdf"。

## 七个 case 的交叉核对

**RF / DF / RH 相对 ssp370，`lnd_in` 只差一个字段**：

```
flanduse_timeseries
```

气象、CO2、Ndep 三项与 ssp370 逐字节相同——这正是管理情景的设计：
只改土地利用轨迹，其余不动。

**ssp585 相对 ssp370** 差预期的四项：`co2_file`、`flanduse_timeseries`、
`metdata_bypass`、`stream_fldfilename_ndep`。

**七个 landuse 各不相同**，RF 是情景无关的那一份：

| case | landuse |
|---|---|
| ssp119 | `…nlcd2elm_SSP1_RCP19_simyr2024-2100.nc` |
| ssp245 | `…nlcd2elm_SSP2_RCP45_…` |
| ssp370 | `…nlcd2elm_SSP3_RCP70_…` |
| ssp585 | `…nlcd2elm_SSP5_RCP85_…` |
| RF | `…nlcd2elm_RF_…`（情景无关） |
| DF | `…nlcd2elm_SSP3_RCP70_DF_…` |
| RH | `…nlcd2elm_SSP3_RCP70_RH_…` |

**七个 case 的分段与 PE 设置完全一致**：
`STOP_N=11`、`REST_N=11`、`RESUBMIT=6`、`NTASKS_LND=2560`。

## 存储前提

批 2/3 的提交时机取决于 `/scratch` 余量。2026-09-08 删除
`/scratch/.../future_clim` 冗余副本（2.7 TiB）后，项目用量从 191.2 TiB
回落到约 188.5 TiB，软限 200 TiB 以内余量约 11.4 TiB，
七个情景所需 10.6 TiB 可完全容纳。**提交批 2 前应重新核对当时的实际余量**，
因为 `/scratch` 是全项目共享的。
