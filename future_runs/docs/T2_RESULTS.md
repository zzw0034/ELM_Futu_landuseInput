# T2 — 4 km future 末端测试结果（2100-12-29 → 2101-01-01）

case `20260906_seus_4km_fut_end2100`，10 节点 / 1280 tasks，构建 D
（`DEBUG=TRUE`，`-fcheck=bounds,pointer`，`-ffpe-trap` 已删），
exe md5 `9bcfc5385a61f0c69ff3edfbd8b9b6ee`，E3SM `0be814f868`。
job **512091 COMPLETED 0:0，13:13**。

`finidat` 仍是旧的 2024 存档，三个 `check_*_consistency` 关闭以允许 2024 状态
起 2100 的时钟（与历史运行用 0441 存档起 1850 是同一手法）。
**只验证驱动索引路径，模型状态无物理意义。**

## 积分

73 个时间步，2100-12-29_00:00 → **2101-01-01_00:00**，写出
`elm.r.2101-01-01-00000.nc` 和两个 h0。

零错误，且 bounds checking 开着：
`above upper bound` / `Fortran runtime error` / `ENDRUN` / `SIGSEGV` /
`cbalance` / `nbalance` 全部为 **0**。

## 1. 初始化索引 — 与推导逐位吻合

```
DIAG_INIT call=1  v=1..7 全部:  t1=227736  t2=227737  timelen=227760  tl_spinup=2920
```

`(2100−2023)×2920 + (caldaym(12)+29−2)×8 = 224840 + 2896 = 227736`。
（此前我按 12-31 算成 227752/227753 是错的，T2 的起点是 12-29；
审查时的更正在此得到实测确认。）

## 2. 末端守卫 — 触发了，被抓在现场

`DIAG_PRE` / `DIAG_POST` 逐调用比对，**唯一发生变化的是 call 71**：

```
call=71 v=1 TBOT   PRE(227760, 227761) -> POST(227760, 227760)
call=71 v=2 PSRF   PRE(227760, 227761) -> POST(227760, 227760)
call=71 v=3 QBOT   PRE(227760, 227761) -> POST(227760, 227760)
call=71 v=6 WIND   PRE(227760, 227761) -> POST(227760, 227760)
call=71 v=7 FLDS   PRE(227760, 227761) -> POST(227760, 227760)
```

`t2 = 227761` 就是缺陷 B：`atm_input` 末端之外一个元素。`fc2a4f2be1`
的守卫把它 hold 到 `timelen`。**这是 B 在 future 配置、4 km 下的首次现场捕获**；
此前 B 只在历史配置、0.5°（`npf=6`）验证过。

**`v=4 (FSDS)` 和 `v=5 (PRECTmms)` 全程没有触发守卫**，收在
`t1=227759, t2=227760`，始终在界内。原因是 T1 测到的相位差：这两个走记录
边界触发、其余五个走中点触发，4 km 的 `npf=3` 下相差一步。
**所以七个变量里只有五个会走到需要守卫的位置**——这一条无法从
`npf=6` 的 0.5° 测试外推。

## 3. `yr=2101` 的 import — 发生了，但没有回绕

```
DIAG_CELL call=72  ymd=21010101  tod_h=0        ← 确实有一次 yr=2101 的 import
DIAG_PRE  call=72  v=1,2,3,6,7   t1=227760 t2=227760
                   v=4,5         t1=227759 t2=227760
```

`yr=2101 > endyear_met_trans=2100`，所以走的是回绕分支，但该分支的条件是
`tindex > timelen`，而此刻 `tindex = 227760` 恰好*等于* `timelen`，
因此 `timelen − timelen_spinup + 1 = 224841`（回绕到 2100-01-01）
**没有发生**。末步读的仍是最后一条真实记录。

这条以前是"未定行为，待验证"，现在有实测答案。

## 4. 末端读到的是真实数据，不是 sentinel

`DIAG_READ` call 71/72（对照 sentinel 值）：

| v | 变量 | raw | sentinel | 解码值 |
|---|---|---|---|---|
| 1 | TBOT | 6487 | 22725 | 300.61 K |
| 2 | PSRF | 9324 | −23831 | 101300 Pa |
| 3 | QBOT | −10050 | −14592 | 0.01626 |
| 4 | FSDS | −10091 / −13852 | −30984 | 305.7 / 506.95 W/m² |
| 5 | PRECTmms | 0 | −32768 | 0 |
| 6 | WIND | −12773 | −14600 | 6.193 m/s |
| 7 | FLDS | −2692 | 14924 | 409.63 W/m² |

无一命中 sentinel。

`t1 == t2 == 227760` 时 `dec1 == dec2`，插值退化为最后一条真实记录——
守卫注释里 "Holding makes the final interval degenerate to the last real
record" 的实测确认。

实际 forcing（`DIAG_FORC`/`DIAG_FLUX`，call 72）：
`T=300.61 TH=300.61 PBOT=101300 Q=0.01626 LWD=409.63`；
`SOLAD1/2 = SOLAI1/2 = 0`、`RAINC/RAINL = 0`——2101-01-01 00:00 UTC 是夜间，
FSDS 走 `tindex(4,2) × wt2(4)` 且 cosz 分支把 `wt2(4)` 置 0，所以解码值
506.95 W/m² 归零。合理。

## 结论与范围限定

**T2 通过**：future 配置下的末端机制按设计工作，且是实测而非推导。

不可外推的部分，如实记录：

- 只观测了 `masterproc` 上的 `g = bounds%begg` **一个格点**。tindex 是
  per-(g,v) 的，各格点算术相同，但只有这一个被记录。
- bounds checking 证明的是**这 73 个时间步实际走过的路径**没有越界，
  不能推广到 2024–2100 全程。
- 模型状态无物理意义（2024 存档起 2100 时钟），本测试不对科学结果发言。
- `hist_avgflag_pertape='I'` 的 h0 已产出，但未做科学检查。
