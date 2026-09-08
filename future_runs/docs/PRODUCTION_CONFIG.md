# 七个正式 future 情景 —— 最终配置清单

**状态：仅准备，未创建 case，未提交任何作业。等最终确认。**

## 通过的前置测试

| 测试 | job | 结果 |
|---|---|---|
| T1 启动 + 七变量索引 | 511835 | 通过 |
| T2 末端（2100-12-29 → 2101-01-01） | 512091 | 通过；缺陷 B 守卫实测触发 |
| A3 初始场科学验收 | 516026 / 516030 | 通过；域内总碳相对变化 8.7e−08 |
| T1b A3 初始场 + restart 读回 | 516079 / 516107 | 通过 |
| T1c 连续对照 | 516279 / 516280 | 分段与连续**逐位相同** |
| T4 生产配置验证 | 516284 | 200g 通过；13.22 分/模式年 |
| T3 生产布局 restart 一致性 | 516288 / 516291 / 516292 | 通过；三处差异全部定位 |

## 共同配置（七个 case 完全相同）

| 项 | 值 |
|---|---|
| 源码 | `0be814f868`（含 A `3cf28db19f` + B `fc2a4f2be1`） |
| exe | **复用 T4 的生产构建**，md5 `e8b487b04a27adfd8f683359dfd73df5`，`DEBUG=FALSE`，0 SourceMods |
| `finidat` | `/scratch/…/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC/run/*.elm.r.2024-01-01-00000.nc`（A3，14,851,804,800 B，sha256 `20e9c29b13b5…`） |
| `fsurdat` | `ELM_makeSurfdata/…/s7_updataPdata/surfdata_UpdatedsoilP_SEUS_1_24deg_simyr1850_c260712.nc` |
| domain | `e3sm_run/20260712_…/run/domain.nc` |
| `paramfile` / `fsoilordercon` | `e3sm_run/20260712_…/run/{clm_params,CNP_parameters}.nc` |
| `metdata_type` | `'era5-daymet-fut'` |
| `aero_file` | `aerosoldep_rcp4.5_monthly_1849-2104_1.9x2.5_c100402.nc`（**不随 SSP 变**） |
| `stream_fldfilename_popdens` | `s8_update_hdm/elmforc.Li_hdm_1_24x1_24_bilinear_SEUS_simyr1850-2100.nc`，`1850/2100`（**不随 SSP 变**） |
| `stream_year_first/last_ndep` | `1850 / 2101` |
| `check_*_consistency` ×3 | `.false.` |
| history | `hist_nhtfrq=0,0`；`hist_mfilt=12,12`；`hist_dov2xy=.true.,.false.`；`hist_avgflag_pertape='A','A'`；`hist_fincl2` 同生产 |
| `PIO_TYPENAME` | `netcdf`（**pnetcdf 按指示跳过**） |
| 时间 | `RUN_TYPE=startup`、`RUN_STARTDATE=2024-01-01`、`CONTINUE_RUN=FALSE` |
| 分段 | `STOP_OPTION=nyears`、**`STOP_N=11`**、`REST_OPTION=nyears`、**`REST_N=11`**、**`RESUBMIT=6`** → 7 段 × 11 年 = **77 年，终点 2101-01-01** |
| PE | `NTASKS_*=2560`、`MAX_MPITASKS_PER_NODE=128`、`NTHRDS_*=1` → **20 节点** |
| Slurm | `-p parallel -A hpcl-cli185 -q hpcl-cli185 --mem=200g --constraint=BL --exclude=blc051,blc052` |
| `JOB_WALLCLOCK_TIME` | **`04:00:00`**（每段积分实测 2.42 h，余量 1.65×） |
| 并发上限 | **3 个情景**（60 节点），按 **3 + 3 + 1** 分批 |

## 七个情景的差异（只有四项）

| # | case 名建议 | landuse | `metdata_bypass` | `co2_file` | `stream_fldfilename_ndep` |
|---|---|---|---|---|---|
| 1 | `…_fut_ssp119` | `…nlcd2elm_SSP1_RCP19_simyr2024-2100.nc` | `…/future_clim/ssp119` | `fco2_datm_ssp119_1765-2500_c260818.nc` | `…_ssp119_c260818.nc` |
| 2 | `…_fut_ssp245` | `…nlcd2elm_SSP2_RCP45_…` | `…/ssp245` | `…ssp245_c260818.nc` | `…_ssp245_c240903.nc` |
| 3 | `…_fut_ssp370` | `…nlcd2elm_SSP3_RCP70_…` | `…/ssp370` | `…ssp370_c260818.nc` | `…_ssp370_c220614.nc` |
| 4 | `…_fut_ssp585` | `…nlcd2elm_SSP5_RCP85_…` | `…/ssp585` | `…ssp585_c260818.nc` | `…_ssp585_c190103.nc` |
| 5 | `…_fut_ssp370_RF` | `harvest_scenarios/…nlcd2elm_RF_…` | `…/ssp370` | 同 #3 | 同 #3 |
| 6 | `…_fut_ssp370_DF` | `harvest_scenarios/…nlcd2elm_SSP3_RCP70_DF_…` | `…/ssp370` | 同 #3 | 同 #3 |
| 7 | `…_fut_ssp370_RH` | `harvest_scenarios/…nlcd2elm_SSP3_RCP70_RH_…` | `…/ssp370` | 同 #3 | 同 #3 |

landuse 根目录 `/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/`；
其余在 `/projects/hpcl-cli185/world-shared/e3sm/inputdata/`。

**输入现状已核实（2026-09-08）**：四个 Default 与 DF、RH 是 **2026-09-05 PFT 和
修复后重建**的版本；**RF 为 2026-08-19 原版**（它本来就通过 `1e-14` 判据，
无需重建）。四个 SSP 气象目录各 7 个变量文件齐全。

## 资源与时间预算

```
单段     11 年 × 13.22 分 = 2.42 h  （walltime 4 h，余量 1.65×）
单 run   7 段 = 16.97 h 积分 + 7 × 39 s 初始化 ≈ 17.05 h，加段间排队
批次     3 + 3 + 1；每批约 17 h + 排队
存储     单 run ≈ 1.51 TiB（history 1454 + restart 97 GiB）
         七个 ≈ 10.6 TiB，对 /scratch 当前 15 TiB 余量约 30%
```

## 提交前必查（每个 case）

1. `RUNDIR` / `EXEROOT` 指向自己的目录，`EXEROOT` 可共用 T4 构建
2. `--keepexe` 克隆后必须 `case.setup`（否则无 `.case.run`），随后恢复
   `BATCH_COMMAND_FLAGS`、`JOB_WALLCLOCK_TIME`、`BUILD_COMPLETE`、`-DCPL_BYPASS`
3. `lnd_in`（不是 `user_nl_elm`）里 ndep/co2/metdata/flanduse 指向本情景
4. `RESUBMIT=6`、`CONTINUE_RUN=FALSE`（不能是上次测试的残留值）
5. `./preview_run` 的 SUBMIT CMD 四个参数齐全
6. `sbatch --test-only`
7. 起跑 5 分钟后 `check_node_freq.sh`

## 正式输出里会出现、但不是物理信号的三样（T3 已定位）

6 个重启边界上：`SEEDC_GRC` 归零重累；`BTRANAVG_VALUE`/`BTRAN_MIN` 约 515 个
PFT 点转填充；每段第一个 h0 多带 8 个时间常量场。详见 `T3_RESULTS.md` §5。

## 另需在分析时排除的

194 个 sentinel 格点（方案 c，固定 mask
`SEUS_halfdeg/data/processed/contamination_masks_SEUS.nc`，
sha256 `1df4dc18…`）。详见 `SENTINEL_CELLS.md`。
