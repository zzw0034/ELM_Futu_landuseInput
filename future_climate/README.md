# future_climate —— 未来气候强迫检查

本目录存放 **future climate forcing 的检查工作**(数据核对、完整性验证、网格/时间
一致性、诊断脚本与图)。土地利用侧的工作留在上级目录,两者不混。

- 本地:`/Users/zw5/ORNL_workplace/pathfinder/ELM_Futu_landuseInput/future_climate`
- Pathfinder:`/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate`
- 上级目录的 `AGENTS.md` 适用(remote root、Slurm、同步方向等规则不变)。
- 计算全部走 Slurm,`-p serial -q normal`。

---

## 0. 结论速览（2026-08-03）

**未来模拟可以直接从 2024 年接上,历史段跑到 2023 为止。**

| 变量 | 偏差(CanESM5-DBCCA 减 Daymet_ERA5,1980–2014,35 年) | 处置 |
|---|---|---|
| 降水 | **+5.7 mm/yr(+0.4%)**,逐月 ±5% 以内 | **不订正**,本来就准 |
| 温度 | **+0.563 °C**,12 个月全为正(+0.38 ~ +0.84) | 记录在案即可;约 1σ 年际变率 |

温度那个暖偏移是系统性的、贯穿整个未来段、不会自己平均掉,但量级在陆面模拟里
可接受。要订正就减一个常数(保留增温信号),逐月因子存在
`outputs/canesm5_hist_bias.npz`。

---

## 1. 数据位置（已核实）

**未来**:`/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5/`

```
CanESM5_{historical,ssp119,ssp245,ssp370,ssp585}_r1i1p1f1_DBCCA_Daymet_TESSFA2/
    Precip3Hrly/clmforc.4km.Prec.YYYY-MM.nc     PRECTmms (time,lat,lon)  mm/s   ~51 MB
    TPHWL3Hrly/clmforc.4km.TPQWL.YYYY-MM.nc     TBOT/QBOT/PSRF/WIND/FLDS  K 等  ~447 MB
    Solar3Hrly/ , DBCCA_dy/
```

- 四条 SSP:**2015-01 ~ 2100-12**(1032 月),单情景约 578 GB,**无缺月**(已逐月核对)
- historical 成员:**1980-01 ~ 2014-12**(420 月),同样无缺月

**历史**:`/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/`

```
Daymet_ERA5_TESSFA.4km_<VAR>_1980-2023_z01.nc    VAR(n=225625, DTIME=128480)
VAR ∈ {TBOT, PRECTmms, FLDS, FSDS, PSRF, QBOT, WIND}   各 54 GB
```

情景标签对应:气候侧 `ssp119/245/370/585` ↔ 土地利用侧
`SSP1-1.9 / SSP2-4.5 / SSP3-7.0 / SSP5-8.5`。

---

## 2. 格式陷阱（记忆重点，都踩过）

1. **cpl_bypass 用 int16 哨兵值标记无效格,不是 NaN。** 这是最坑的一条。
   变量是 int16 + `scale_factor`/`add_offset`,陆地掩膜外的格子存的是整数哨兵,
   **解码后是完全有限的数**,`np.isfinite` 过滤不掉:

   | 变量 | 原始 int | 解码后 | 真实范围 |
   |---|---|---|---|
   | `TBOT` | 22725 | **396.001 K** | ~250–300 K |
   | `PRECTmms` | −32768 | **−0.088 mm/s** | ≥ 0 |

   一半以上的格子是这种哨兵。不掩膜直接求域平均会得到 **67 °C 和负降水**
   (第一次跑就是这个结果)。掩膜逻辑在 `scripts/tessfa_mask.py`,从 TBOT 自身
   导出(不依赖单独的 domain 文件,避免与强迫场脱节),并断言时间不变。

2. **两侧掩膜完全一致**:历史与未来都是 **117964 / 225625** 个有效格,且逐元素
   相等(对 `clmforc.4km.TPQWL.2024-01.nc` 核对过)。未来用 NaN,历史用哨兵。
   掩膜之后两边的域平均覆盖同一片区域,才可比。

3. **`n` 的排列是 lat 最快**:`n = ilon*361 + ilat`,所以
   `mask.reshape(625, 361).T` 才是未来文件的 `(lat, lon)` 布局。

4. **日历不同**:历史是 **noleap**(128480 = 44 yr × 365 d × 8,每年恒 2920 步);
   未来**含闰日**(2024-02 有 232 步)。年降水总量必须用各年自己的步数,不能写死 365。

5. **网格完全一致**:历史 `LONGXY/LATIXY` 展平后与未来 `lat`/`lon`(361×625)
   在 1e-3 内相等。两者都是 TESSFA2,不是 TESSFA1。

6. **温度要用 3 小时的 `TBOT`,不要用 `DBCCA_dy` 的 `(tmax+tmin)/2`。**
   日数据便宜约 20 倍,但 `(tmax+tmin)/2` 与真实 3 小时平均差零点几度,**这个方法学
   偏差恰好落在 2023/2024 接缝上**,等于自己制造一个假跳变。降水两者等价
   (已验证:年总量逐字相同),温度不等价。

7. **未来数据从 2015 开始,与历史重叠 2015–2023**。这 9 年是唯一的配对比较窗口。

---

## 3. 接缝检查：做法与结论

### 3.1 为什么不能只看 2023→2024 那一步

单年跳变把「真实偏移」和「一年的天气」混在一起。实测降水单年跳变
**−207 ~ +282 mm/yr,连符号都不一致**——纯粹是天气。温度 SSP2 那年跳了 +1.84σ,
但同情景 9 年重叠期的偏差只有 +0.20σ。

### 3.2 9 年窗口也不够 —— 这条是教训

先用 2015–2023 重叠期比,得出「四个情景全部偏干 10–20%」的结论。**这个结论是错的。**

```
观测 2015-2023                        1420.2 mm/yr
观测 1980-2014 长期平均                1279.1 mm/yr
观测 1980-2014 内所有 9 年滑动窗口      1220.4 ~ 1337.6
```

**2015–2023 比前 35 年里任何一个 9 年窗口都湿。** 拿模式跟记录上最湿的 9 年比,
凭空造出一个 11% 的缺口。

另一个标尺:四个 SSP 在 2015–2023 本该气候上几乎相同(情景强迫尚未分岔),它们
之间却相差 **137 mm/yr(std 56,占均值 4.7%)**。这就是 9 年内部变率的量级,
和所谓「缺口」同量级。

### 3.3 可信的做法：拿 historical 成员比 35 年

`CanESM5_historical_..._TESSFA2` 覆盖 1980–2014,与 Daymet_ERA5 重叠 **35 年**,
且出自同一条降尺度链但不是 SSP 文件。结果见 §0 的表:降水 +0.4%,温度 +0.563 °C。

**降水的偏差订正 DBCCA 做得很好**,不需要再补。温度有小幅系统暖偏差。

顺带纠正:9 年窗口里看到的「12 月四情景一致偏冷 −1.5 °C」也是噪声——
historical 成员 12 月是 **+0.84 °C 偏暖**,方向相反。

### 3.4 保留的不确定性

SSP 时段本身只有 9 年可比,无法完全排除 SSP 文件有小幅降水偏移;但从情景间离散度
看证据很弱。等未来段跑起来,用 2024–2050 的模式气候态跟历史比会更有说服力。

---

## 4. 脚本

| 脚本 | 作用 |
|---|---|
| `tessfa_mask.py` | 共用的有效格掩膜 + 物理量程断言(见 §2.1) |
| `01_hist_annual_means.py` | 历史年均 2000–2023 |
| `02_future_annual_means.py` | 未来年均 2015–2100,`--scenario` |
| `03_plot_splice.py` | 年尺度接缝图 |
| `04_hist_monthly_means.py` | 历史月均,`--y0/--y1/--out` |
| `05_future_monthly_means.py` | 未来月均,`--scenario`(含 `historical`)`--y0/--y1` |
| `06_plot_monthly_splice.py` | **月尺度接缝图**(主图) |
| `07_canesm5_hist_bias.py` | **35 年 historical 对照**(定论的那个)+ 逐月订正因子 |

```bash
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
sbatch --export=NONE jobs/submit_hist_monthly.sbatch        # 历史月均 2010-2023
sbatch --export=NONE jobs/submit_future_monthly.sbatch      # 未来月均 2015-2029 ×4
sbatch --export=NONE jobs/submit_plot_monthly.sbatch        # -> 月尺度接缝图
sbatch --export=NONE jobs/submit_canesm5_hist_bias.sbatch   # 1980-2014 两侧 ×2
sbatch --export=NONE jobs/submit_hbias_compare.sbatch       # -> 35 年对照图
```

耗时参考(五个作业并发时):历史年均 2000–2023 约 40 min(读约 59 GB);
未来年均 2015–2100 单情景约 41 min(约 145 GB);窄窗口月均约 10–20 min。
`DBCCA_dy` 便宜 20 倍但温度不可用,见 §2.6。

产出:`outputs/*.npz`、`outputs/figures/*.png`、`outputs/logs/`。
`outputs/` 被上级 `.gitignore` 排除,本目录只进脚本、sbatch 和文档。

---

## 5. 待办

- 决定温度 +0.56 °C 是否订正(见 §0)
- SSP 时段降水的最终确认,等未来段跑出 2024–2050 再比(见 §3.4)
- 其余强迫量(`FSDS`/`FLDS`/`QBOT`/`WIND`/`PSRF`)尚未做接缝检查,只查了 T 和 P
