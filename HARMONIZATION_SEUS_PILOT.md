# §13 — Harmonization method (SEUS pilot spec)

**Status: implemented.** Formulas in 13.0–13.8 are unchanged. Code:
`scripts/02_harmonize_seus.py`.

- **ELM forcing (maintained):** `02 --build-timeseries`. Reads the target
  `landuse.timeseries` (324×504) and a Chen file re-aggregated onto that grid
  (`01 --like <target>`). Writes
  `outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc`.
  Current production runs should use the smoothHARV historical target
  `landuse.timeseries_SEUS_1_24deg_nlcd2elm_smoothHARV_simyr1850-2023_c260723.nc`
  as the reference/anchor lineage. Its static fields and `PCT_NAT_PFT` match
  the original c260723 file; only historical `HARVEST_*` changed. Details:
  `FUTURE_LANDUSE_TIMESERIES.md`.
- **Standalone (not maintained):** `02` without `--build-timeseries`. Crops the
  CONUS NLCD + CONUS Chen files to the SEUS bbox as this spec describes, and
  writes `harmonized_SEUS_<SSP>_*.nc`. It exits if those CONUS Chen files are
  absent. The NLCD source grid starts at 25.0°N, so the crop is 300 rows — 24
  rows short of the 324-row target grid and cannot reach the documented 24.0°N
  southern bound.

Scope is the Southeast US pilot (bbox lon −95..−74, lat 24..37.5). The full-CONUS
version is the same method plus the boreal drop-list of §12.5/§11c, which is
inert in SEUS (see 13.3).

Produces a harmonized land-use timeseries that carries the **NLCD-derived
historical state** and applies the **Chen2022 scenario trend**, for
`PCT_NATVEG` and `PCT_NAT_PFT` only (the ELM product additionally writes
`HARVEST_*` / `GRAZING` and keeps `PCT_NATVEG` static — see 13.9). Everything
below follows from §10–§12 and the two source papers (LUH2-style delta;
Chen2022 §1.4 area calibration = additive delta; Chen2020 §2.3 marched relative
change).

---

## 13.0 Principle

> Initial / observed state from the high-resolution base map (NLCD), used for
> **every year NLCD observes (through 2023)**. Future change from the scenario
> (Chen), taking over only **past observation (from 2024)**. Joined by **delta
> harmonization anchored at NLCD's last observed year, 2023**. Only Chen's
> *change* from its own 2023 ever enters — never its absolute state.

This immunizes the product against the large *level* disagreements catalogued in
§11 (products differ by ~21% of the natveg column in composition) while
inheriting Chen's decadal transient, and it uses the full observational record
(anchoring at 2020 would discard the 2021–2023 observations).

---

## 13.1 Inputs

| role | file | vars used |
|---|---|---|
| base (history) | `.../s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc` | `PCT_NATVEG(time,lat,lon)`, `PCT_NAT_PFT(time,natpft,lat,lon)` |
| scenario (trend) | `outputs/processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc` | same two |

- Identical grid 601×1441, 1/24°, centers lat 25..50, lon −125..−65. Cell-by-cell,
  no regridding.
- NLCD time: 1850–2023 **annual**. Chen native time: 2015, 2020, 2025 … 2100
  (5-yearly). **Chen is linearly interpolated to annual on `p(j)` (13.2) before
  marching** — so `p_ch(j, 2023)`, `p_ch(j, 2024)` … come from linear
  interpolation between Chen's native 2020 and 2025 steps.
- **Only `PCT_NATVEG` and `PCT_NAT_PFT` are read.** No urban/lake/crop/glacier
  column enters (§12.4; Chen's urban effect is carried implicitly as natveg
  loss — 13.7 note).
- SEUS: crop both to the bbox before processing.

**As implemented.** `--build-timeseries` does not use these two CONUS files. It
reads the target ELM `landuse.timeseries` (anchor + static land-unit columns,
324×504) and `outputs/interim/chen_targetgrid_<SSP>_2015-2100_1_24deg.nc` from
`01 --like <target>`. The quantities (`p(j)`, groups, formula) are the same.

---

## 13.2 Working quantity — PFT share of the whole cell

The only per-PFT quantity commensurable between the two products (shared
denominator = the cell) is

```
p(j)  =  PCT_NATVEG * PCT_NAT_PFT(j) / 100        [% of the whole cell]
```

`PCT_NAT_PFT(j)` alone is NOT comparable (its denominator is each product's own
natveg column). All harmonization is done on `p(j)`; the two output variables
are recovered from it at the end (13.7):

```
PCT_NATVEG      = Σ_j p(j)                       (clip to [0,100])
PCT_NAT_PFT(j)  = 100 * p(j) / Σ_j p(j)          (0 where natveg = 0)
```

Recovery makes the sum-to-100 constraint automatic — no separate renormalization.

**Annual interpolation is done on `p(j)` directly**, not on `PCT_NATVEG` and
`PCT_NAT_PFT` separately: the product of two linearly-interpolated factors is not
the linear interpolation of the product, and `p(j)` is the quantity we march.

---

## 13.3 Functional groups and the SEUS active set

Harmonization is done at **functional-group** altitude, then re-split to PFTs
(§12.5; forced by the PFT1↔PFT7 relabel and the 9/10, 13/14 conventions, §11c).

```
GROUPS = { Bare:[0], Tree:[1,2,3,4,5,6,7,8], Shrub:[9,10,11],
           Grass:[12,13,14], Crop:[15,16] }
P_g(cell) = Σ_{j in g} p(j)                       [% of cell, per group]
```

**SEUS active PFTs (post-PFT3-fix): 0, 1, 7, 9, 10, 13, 14, 15** — the 8 "real
CONUS" PFTs. Boreal/arctic (2,3,8,11,12) are identically 0 in SEUS, so the CONUS
boreal drop-list is inert here and the seed rule (13.5) has no artifact to
filter. PFT 6 (broadleaf deciduous tropical) has 12 cells in south Florida →
force 0 (13.8).

---

## 13.4 Anchor and timeline

- **Anchor t0 = 2023** — NLCD's last observed year. Observation owns everything
  through 2023; Chen takes over only from 2024 (past observation). Requires Chen
  interpolated to annual (13.1), so `p_ch(·, 2023)` and `p_ch(·, 2024)` are
  linear interpolations inside Chen's native 2020–2025 interval.
- Output years (all annual):
  - `t ≤ 2023`: harmonized = NLCD as-is (observed passthrough).
  - `t ∈ {2024, 2025, …, 2100}`: harmonized = NLCD(2023) + Chen's marched
    annual group-delta from 2023, re-split by NLCD's frozen 2023 proportions.
- The future is **marched annually** (2023→2024→…→2100). Marching, not a single
  anchor, because the min-footprint branch (13.5) depends on the ratio that
  evolves as the harmonized state moves; annual steps re-evaluate the branch
  each year. (Additive steps telescope within a branch; the multiplicative
  branch compounds annually — the granular, faithful behaviour.)

---

## 13.5 The harmonization formula — group totals, marched annually (Chen2022 eq. 1)

For each SEUS cell, each group `g`, init `P_harm_g[2023] = P_nl_g[2023]`, then for
`t = 2024, 2025, …, 2100`:

```
Ph    = P_harm_g[t-1]           # previous harmonized group total (% of cell)
Cprev = P_ch_g[t-1]             # Chen group total (annual-interpolated), previous year
Cnow  = P_ch_g[t]               # Chen group total (annual-interpolated), this year
dC    = Cnow - Cprev            # Chen's own absolute group change over the year

if Ph == 0:                     # NLCD had none of this group here
    P_harm_g[t] = max(dC, 0)                 # SEED: add Chen's growth only (all real in SEUS)
elif Cprev <= Ph:               # ratio = Cprev/Ph < 1  → min-footprint = Chen side
    P_harm_g[t] = Ph + dC                    # ADDITIVE  (eq.1 case A; preserves Chen's absolute change)
else:                           # ratio ≥ 1              → min-footprint = harmonized side
    P_harm_g[t] = Ph * (Cnow / Cprev)        # MULTIPLICATIVE (eq.1 case B; relative change)

P_harm_g[t] = max(P_harm_g[t], 0.0)          # clip negatives
```

Notes:
- The additive branch is written `Ph + dC`, never `Ph*(1+r)`, so a Chen group
  emerging from `Cprev = 0` does not divide by zero (§12.4 pitfall).
- The two non-seed branches are exactly Chen2022 eq. (1); together they equal
  `effective absolute change = dC · min(1, Ph/Cprev)` (min-footprint), continuous
  at ratio = 1.
- Urban (eq. 2) is **not** used — we carry no urban column; Chen's urban
  expansion enters implicitly as a decline of the vegetated groups (their
  `P_ch_g` shrink), which the formula transfers as negative `dC`.

---

## 13.6 Re-split group totals back to 17 PFTs (NLCD-frozen basis)

Freeze the within-group NLCD proportions at the anchor:

```
w_nl(j) = p_nl(j, 2023) / P_nl_g(2023)          for j in group g,  if P_nl_g(2023) > 0
```

Then for every future year `t`:

```
p_harm(j, t) = P_harm_g[t] * w_nl(j)            for j in g
```

- This makes Chen set only the **group total**, while NLCD keeps the **PFT
  identity**: the PFT1/PFT7 tree mix, the 13/14 C3/C4 split, the 9/10 shrub
  split, and the low-% understory "sprinkle" that Chen (categorical, peaky) lacks
  are all inherited from NLCD and frozen (§ "peaky Chen / spread NLCD").
- **Fallback** when `P_nl_g(2023) = 0` (group seeded from zero, no NLCD basis):
  split by Chen's within-group proportion at `t`,
  `w = p_ch(j,t) / P_ch_g(t)`. In SEUS this is essentially only Crop
  (→ PFT15) and occasionally Grass (→ Chen's 13/14).

---

## 13.7 Recover output variables

```
PCT_NATVEG_harm(t)     = clip( Σ_j p_harm(j,t), 0, 100 )
PCT_NAT_PFT_harm(j,t)  = 100 * p_harm(j,t) / Σ_j p_harm(j,t)     (0 if Σ = 0)
force PCT_NAT_PFT_harm(j,t) = 0 for j in {2,3,6,8,11,12}          (SEUS: no boreal/tropical)
```

Note (urban): because `p(j)` is % of the whole cell, Chen's urbanization shows up
as a shrinking Σ_j p_ch(j), i.e. negative group deltas, so `PCT_NATVEG_harm`
declines with Chen's projected urban expansion without ever touching an urban
column. The freed cell fraction is simply not reported (out of scope); the cell
budget is intentionally not closed.

---

## 13.8 Seed / drop rules (SEUS)

| situation | rule |
|---|---|
| Chen group grows from a NLCD-zero base (`Ph=0, dC>0`) | seed additively `= dC` (all groups real in SEUS) |
| Chen group flat/shrinking on NLCD-zero base | stays 0 (level difference, frozen) |
| NLCD has a PFT, Chen does not (the "sprinkle") | frozen (Chen Δ=0), preserved by construction |
| boreal PFTs 2,3,8,11,12 | 0 in SEUS — no drop-list needed |
| PFT 6 (12 south-FL cells) | force 0 (negligible tropical artifact) |

No "boreal-artifact vs real-PFT" judgement is required in SEUS — the CONUS
method's thorniest branch is empty here.

---

## 13.9 Output

- Spec file: `outputs/processed/harmonized_SEUS_SSP1_RCP19_1850-2100_1_24deg.nc`
  - grid: SEUS-cropped (bbox lon −95..−74, lat 24..37.5), lat ascending.
  - `PCT_NATVEG(time,lat,lon)`, `PCT_NAT_PFT(time,natpft,lat,lon)`.
  - `time`: **annual 1850..2100** — 1850..2023 = NLCD observed (unchanged),
    2024..2100 = harmonized. (A shorter 2023..2100 file is fine for a first pass;
    the full annual series is the drop-in ELM forcing.)
  - global attrs: method = "delta-harmonization, anchor 2023, group-level eq.1,
    NLCD-frozen re-split, Chen interpolated to annual"; base and scenario source
    paths; SEUS bbox.
- Diagnostics (interim/figures):
  1. budget residual map — `Σ_g ΔP_ch,g  −  Σ_g ΔP_harm,g` per cell per year (≈0 expected).
  2. per-group harmonized trajectory 2023→2100 vs NLCD-2023 and Chen.
  3. before/after composition bars at a few sample cells (pine-belt, cropland, mixed).

**As implemented.**

- Standalone: `outputs/processed/harmonized_SEUS_<SSP>_<hist-start>-2100_1_24deg.nc`.
  `--hist-start` defaults to **2024**, not 1850. Not the maintained path (see Status).
- ELM forcing: `outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc`
  - grid 324×504 (`lsmlat`/`lsmlon`), copied from the target historical file.
  - static land-unit columns copied verbatim (`PCT_NATVEG` included).
  - time-varying 2024–2100: `PCT_NAT_PFT`, `HARVEST_*`×5, `GRAZING`.
  - natveg=0 cells: `PFT0 (bare) = 100` (ELM convention), not all-zero composition.
- Diagnostics written:
  - `outputs/interim/harmonize_seus_diag_<SSP>.npz`
  - `outputs/figures/fig_harmonize_seus_diag_<SSP>.png` (`scripts/analysis/03_harmonize_seus_diag.py`)
  - `outputs/figures/fig_harmonize_seus_scenario_compare.png` (`scripts/analysis/06_harmonize_seus_compare.py`; SSP1/2/4/5)

---

## 13.10 Validation (must pass)

1. `PCT_NAT_PFT_harm` sums to 100 within natveg for all t (atol 1e-3).
2. `PCT_NATVEG_harm ∈ [0,100]`.
3. **Anchor identity**: at t=2023, harmonized == NLCD 2023 (exactly); and
   `t ≤ 2023` equals NLCD unchanged.
4. Boreal PFTs (2,3,8,11,12) and PFT6 are 0 for all t.
5. Group-total sign check: `P_harm_g` trend 2023→t matches sign of Chen's
   `P_ch_g` trend where NLCD had the group (no sign inversion introduced).
6. Budget residual small and confined to any seeded/clipped cells.
7. Chen annual interpolation reproduces Chen's native 5-year values at native
   years (2025, 2030, …).

---

## 13.11 Open parameters (defaults chosen)

| # | choice | default | alt |
|---|---|---|---|
| 1 | anchor year | **2023** (NLCD last observed) | 2020 (if 2021–23 frac_pred distrusted) |
| 2 | re-split basis | **NLCD frozen 2023 proportions** | time-varying / Chen-blended |
| 3 | future cadence | **annual** (Chen interpolated to annual, march annually) | Chen's native 5-yearly |
| 4 | history in file | **full annual 1850–2023 NLCD prepended** | 2023–2100 only |
| 5 | PFT6 south-FL | **force 0** | keep |
| 6 | non-SEUS cells | **omit (SEUS subgrid file)** | full grid, NLCD passthrough |

`--hist-start` in `02` defaults to 2024 (the alt of row 4), not 1850. The ELM
product is 2024–2100 only; historical 1850–2023 stays in the target file.

---

## 13.12 Implementation

```
scripts/02_harmonize_seus.py
  --build-timeseries --scenario <SSP>     # ELM forcing (maintained)
  [--scenario <SSP>]                      # standalone diagnostic (not maintained)

  Stage A: §13 group-level min-footprint march + NLCD-frozen re-split
           (--build-timeseries: natveg=0 → PFT0=100; Crop group is [15], PFT 16 force-zeroed)
  Stage B: LUH2 harvest downscale (timeseries mode only). Since 2026-08-28 the
           coarse 0.25 deg LUH2 field is pre-smoothed (normalized-convolution
           Gaussian, ported from s4_2_donwscale_LUH2harvest.py) before the
           area-conserving downscale -- see FUTURE_LANDUSE_TIMESERIES.md §13
           for the full rationale/validation; the formula/units here are
           unchanged, only the coarse input to it is smoothed first.
  Stage C: assemble target-schema landuse.timeseries (timeseries mode only)

jobs/submit_chen_targetgrid.sbatch         # 01 --like <target>, 4 SSPs
jobs/submit_chen_targetgrid_ssp370.sbatch  # same, SSP3_RCP70 only
jobs/submit_landuse_future_array.sbatch    # 02 --build-timeseries, 4 SSPs as one
                                            # --array=0-3 job; -p serial -q normal
                                            # -c 1 --mem=64g -t 00:40:00 (2026-08-28,
                                            # preferred entry point for rebuilding
                                            # all 4 SSPs together, e.g. after a
                                            # pipeline-wide change like Stage B above)
jobs/submit_landuse_future.sbatch          # loops SSP1/2/5 only, single job; kept for
                                            # single/partial reruns; -p serial -q normal
jobs/submit_landuse_future_ssp370.sbatch   # same, SSP3_RCP70 only; -p serial -q normal
jobs/submit_harmonize_seus.sbatch          # standalone 02; --mem=48g; not the forcing path
jobs/submit_harmonize_regen.sbatch         # standalone 4 SSPs + analysis/03 + analysis/06
```
