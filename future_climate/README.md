# future_climate —— 未来气候强迫检查

本目录存放 **future climate forcing 的检查工作**(数据核对、完整性验证、网格/时间
一致性、诊断脚本与图)。土地利用侧的工作留在上级目录,两者不混。

- 本地:`/Users/zw5/ORNL_workplace/pathfinder/ELM_Futu_landuseInput/future_climate`
- Pathfinder:`/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate`
- 上级目录的 `AGENTS.md` 适用(remote root、Slurm、同步方向等规则不变)。

## 起点:已经知道的事

以下结论来自 `../FUTURE_LANDUSE_TIMESERIES.md` §9.3,检查时**先复核再沿用**,不要
当成已验证的前提:

| 项 | 已记录的结论 |
|---|---|
| 数据根 | `/projects/hpcl-cli185/proj-shared/TESSFA` |
| 选定组合 | `CanESM5_ssp{119,245,370,585}_r1i1p1f1_DBCCA_Daymet_TESSFA2` |
| 文件量 | 四条各 Prec/Solr/TPHWL 1032 个月文件(2015-01~2100-12),单情景约 578 GB |
| 域 | **TESSFA2 才是 SEUS**,TESSFA1/DOMAIN1 是更大的 PT 域 |
| 气候网格 | TESSFA_SE 361×625 @ 4km 投影 |
| 陆面网格 | SEUS 324×504 @ 1/24° 经纬 —— **两者不同,datm 必须重映射** |
| 已知残缺 | `MIROC-ES2L_ssp585_..._TESSFA2` 不完整,别用(见 §9.3) |

情景集合与土地利用侧一致:**SSP1-1.9 / SSP2-4.5 / SSP3-7.0 / SSP5-8.5**
(气候侧的文件名标签是 `ssp119/245/370/585`)。

## 约定

- 大文件(NetCDF/日志/图)不进 Git —— 上级 `.gitignore` 已覆盖 `*.nc`、`outputs/`、
  `*.log`/`*.out`/`*.err`。本目录只放脚本、Slurm 作业和文档。
- 计算走 Slurm,不在登录节点跑。
- 检查结论写进本目录的文档,重要的再回写到 `../FUTURE_LANDUSE_TIMESERIES.md`。
