# CO2 / Ndep SSP 强迫构建 —— 工作记录（记忆文档）

给 ssp119/245/370/585 四个情景配齐 CPL_BYPASS 能读的 CO2(标量)和 Ndep(144×96
网格)强迫文件。2026-08-18 完成。

**这份文档只讲这两个脚本本身**(建了什么、怎么建的、怎么复现)。CPL_BYPASS 读
CO2/Ndep 的硬编码年份索引机制、met bypass 的空间映射问题、已完成历史 run 的
Ndep 2016 冻结实测——这些更大的背景在
`../future_climate/elm_cpl_bypass_forcing_constraints.md`,不在这里重复。

---

## 0. 最终成品

```
world-shared/e3sm/inputdata/atm/datm7/CO2/fco2_datm_ssp{119,245,370,585}_1765-2500_c260818.nc
world-shared/e3sm/inputdata/lnd/clm2/ndepdata/fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp{119,245,370,585}_*.nc
```

（`world-shared` = `/projects/hpcl-cli185/world-shared/e3sm/inputdata`,E3SM
正式共享 inputdata 目录,不在这个项目仓库里,不受 git 管理。）

其中 Ndep 的 ssp245/370/585 是从 E3SM 官方 LCRC 服务器下载的现成文件,不是本项目
生产的;本项目实际**新建**的是 CO2 四个情景全部,以及 Ndep 的 ssp119。

---

## 1. CO2 —— 四个情景全部新建

**做法**:每个文件是 1765-2500 连续单一文件(为什么必须连续、不能只做
"2024年往后"的独立文件,见 `../future_climate/elm_cpl_bypass_forcing_
constraints.md` §1)。拼接 NCAR CMIP6 历史段(四情景共用,1750-2013)+ 各情景
自己的 ScenarioMIP 未来段(2014-2501),裁到 1765-2500(736 条年记录),schema
对齐已在用的 `fco2_datm_rcp4.5_1765-2500_c130312.nc`(同一套 dims/vars/时间
惯例,只换 `CO2` 数值)。

**源数据**:`https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata/atm/datm7/CO2/`
(NCAR 自己的 inputdata 服务器,不是 E3SM 的 LCRC 镜像):

```
fco2_datm_global_simyr_1750-2014_CMIP6_c180929.nc            历史段,四情景共用
fco2_datm_globalSSP1-1.9_simyr_2014-2501_CMIP6_c190514.nc    ssp119 未来段
fco2_datm_globalSSP2-4.5__simyr_2014-2501_CMIP6_c190506.nc   ssp245 未来段(注意两个下划线)
fco2_datm_globalSSP3-7.0_simyr_1750-2501_CMIP6_c201101.nc    ssp370(已是完整 1750-2501,不用拼)
fco2_datm_globalSSP5-8.5__simyr_2014-2501_CMIP6_c190506.nc   ssp585 未来段
```

**交叉验证**:和 `/projects/hpcl-cli185/proj-shared/xyk/future_forcing/` 里独立
的官方 input4MIPs 原版文件(`GHG_CMIP6_SSP{370,585}-1-2-1_Annual_Global_
2015-2500`)核对,2100 年数值几乎逐位吻合:

| 年份 | ssp370(本次构建 / xyk 官方原版) | ssp585 | 
|---|---|---|
| 2015 | 399.95 / 399.948 | 399.95 / 399.949 |
| 2050 | 540.58 / 540.581 | 562.78 / 562.784 |
| 2100 | 867.19 / 867.191 | 1135.21 / 1135.21 |

也和已发表的 SSP 浓度数值(Meinshausen et al. 2020, *GMD*)对得上。

**脚本**:`build_co2_ssp.py`。

---

## 2. Ndep —— ssp245/370/585 下载,ssp119 新建

### 2.1 ssp245/370/585:和 xyk 是同一份数据

从 E3SM 官方 LCRC 服务器(`https://web.lcrc.anl.gov/public/e3sm/inputdata/
lnd/clm2/ndepdata/`)下载。**checksum 核对过,和
`/projects/hpcl-cli185/proj-shared/xyk/future_forcing/fndep/` 里 xyk 本人的
本地产出逐字节相同**——LCRC 上的官方版本就是 xyk 用 `gen_fndep.py` 生产、上传
上去的,不是两份独立数据。

### 2.2 ssp119:新建,LCRC 和 xyk 本地都没有

`gen_fndep.py` 只写了 ssp126/245/370/534 四个分支,没有 ssp119;xyk 目录里也
没有 ssp119 的原始 input4MIPs 通量源文件——一度怀疑这个数据集不存在。

后来在 ESGF 上用**精确 `source_id` 过滤**找到:全文关键词搜索在这个索引上完全
找不到(会被大量 CMIP7 内容淹没),必须直接用 `source_id=NCAR-CCMI-ssp119-1-0`
做 facet 查询才能命中。数据集确实存在,托管在两个节点:

```
esgf-node.ornl.gov       ORNL 自己的节点
eagle.alcf.anl.gov
```

drynhx/drynoy/wetnhx/wetnoy 四个变量都在,下载 URL 形如:

```
http://esgf-node.ornl.gov/thredds/fileServer/user_pub_work/input4MIPs/CMIP6/ScenarioMIP/
  NCAR/NCAR-CCMI-ssp119-1-0/atmos/mon/<var>/gn/v20190124/
  <var>_input4MIPs_surfaceFluxes_ScenarioMIP_NCAR-CCMI-ssp119-1-0_gn_201501-210012.nc
```

四个变量只需替换 `<var>`,SHA256 校验和(ESGF file-level 搜索结果自带)核对
通过。

**建法**:和 `gen_fndep.py` 同一套配方(单位换算 kg m⁻² s⁻¹ → g m⁻² yr⁻¹,填进
1849-2101 模板的对应年份位置)。唯一差异:ssp119 的源文件本来就覆盖到 **2100**
年(`201501-210012`),其余三个情景的源文件只到 2099(`201501-209912`,靠复制
2099 值补 2100/2101)——ssp119 只需要复制 2100 年的值去补 2101 年,不需要复制
两年。

**验证**:历史段(1849-2014)和 ssp245 逐格点比对,**max diff = 0.0**。2015 年
全球均值 Ndep = 0.156 g/m²/yr,2100 年降到 0.101 g/m²/yr——下降趋势符合
SSP1-1.9 低排放/强减排叙事的物理预期。

**脚本**:`build_ndep_ssp119.py`。

---

## 3. 怎么复现

```bash
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/co2_ndep_ssp_forcing
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 $PY build_co2_ssp.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 $PY build_ndep_ssp119.py
```

两个脚本运行时间都是几分钟量级(标量/单情景数据,不像 landuse 那样有大数组),
在登录节点直接跑过,没有触发过内存问题——不需要走 Slurm。原始源文件在
`src_ncar_co2/`、`src_ndep_ssp119/`(未纳入 git,数据文件),产出在 `output/`。

---

## 4. 相关文件

- `build_co2_ssp.py`、`build_ndep_ssp119.py` —— 本目录,构建脚本
- `../future_climate/elm_cpl_bypass_forcing_constraints.md` §1/§6 —— CPL_BYPASS
  读 CO2/Ndep 的硬编码机制、这次构建工作在更大背景下的记录
- `../FUTURE_LANDUSE_TIMESERIES.md` —— 同一个 future case 需要的另一块强迫
  (landuse.timeseries)
- `../harvest_scenarios/HARVEST_SCENARIOS.md` —— 同一批工作里的管理情景构建
