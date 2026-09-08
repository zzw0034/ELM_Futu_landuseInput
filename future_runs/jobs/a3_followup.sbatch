#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1 -n 1 -c 4
#SBATCH --mem=96g
#SBATCH --time=01:00:00
#SBATCH -J a3_follow
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/a3_followup.%j.out
P=/projects/hpcl-cli185/proj-shared/zw5
C=/scratch/hpcl-cli185/zw5/cime_output_dirs/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
CASE=20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
$P/conda_envs/make_surfdata_pf/bin/python - <<PYEOF
import netCDF4, numpy as np, json
C="$C"; CASE="$CASE"
NEW=C+"/run/"+CASE+".elm.r.2024-01-01-00000.nc"
OLD=C+"/pre_A3_baseline/run/"+CASE+".elm.r.2024-01-01-00000.nc"
FC=1e35
def load(ds,n):
    a=ds.variables[n][:]
    if np.ma.isMaskedArray(a):
        m=np.ma.getmaskarray(a); a=np.ma.filled(a.astype("f8"),np.nan)
    else:
        a=np.asarray(a,dtype="f8"); m=np.zeros(a.shape,bool)
    return a, (~m)&(~(np.abs(a)>=FC))

dn=netCDF4.Dataset(NEW); do=netCDF4.Dataset(OLD)

print("== Q1. are the NaNs pre-existing? ==")
for v in ["tempavg_finrw","tempavg_somhr","tempavg_agnpp","tempavg_bgnpp"]:
    if v not in dn.variables: continue
    A,va=load(dn,v); B,vb=load(do,v)
    print("  %-16s NEW: nvalid=%-9d NaN=%-9d | OLD: nvalid=%-9d NaN=%-9d | same NaN mask: %s"
          %(v,va.sum(),np.isnan(A[va]).sum(),vb.sum(),np.isnan(B[vb]).sum(),
            bool(np.array_equal(np.isnan(A),np.isnan(B)))))

print()
print("== Q2. T_SOISNO min=0 -- snow layers or soil layers? ==")
A,va=load(dn,"T_SOISNO")
print("  shape:",A.shape,"(levtot=20 = 5 snow + 15 soil)")
for lab,sl in [("snow lev 1-5",slice(0,5)),("soil lev 6-20",slice(5,20))]:
    sub=A[:,sl]; sv=va[:,sl]; f=sub[sv&np.isfinite(sub)]
    z=(f==0).sum()
    print("  %-14s nvalid=%-9d min=%-10.6g max=%-10.6g  exactly-zero=%d (%.2f%%)"
          %(lab,sv.sum(),f.min(),f.max(),z,100.0*z/max(f.size,1)))
nz=A[:,5:][va[:,5:]]; nz=nz[np.isfinite(nz)&(nz>0)]
print("  soil layers, zeros excluded: min=%.6g max=%.6g"%(nz.min(),nz.max()))

print()
print("== Q3. slow pools: how much did they move? ==")
for v in ["deadstemc","deadcrootc","livestemc","leafc","frootc","totlitc",
          "cwdc_vr","soil1c_vr","soil2c_vr","soil3c_vr","soil4c_vr",
          "sminn_vr","solutionp_vr","totcolc" if "totcolc" in dn.variables else "leafn"]:
    if v not in dn.variables or v not in do.variables: continue
    A,va=load(dn,v); B,vb=load(do,v); both=va&vb
    if not both.any(): continue
    d=np.abs(A[both]-B[both]); d=np.where(np.isnan(d),np.inf,d)
    sc=np.maximum(np.abs(A[both]),np.abs(B[both])); sc=np.where((sc==0)|~np.isfinite(sc),1.0,sc)
    rel=d/sc
    print("  %-14s ndiff=%-9d frac=%.4f  max|d|=%-12.6g maxrel=%-12.6g  sum_new=%.8g sum_old=%.8g  dsum/sum=%.3e"
          %(v,(d>0).sum(),(d>0).sum()/both.sum(),d.max(),rel.max(),
            np.nansum(A[both]),np.nansum(B[both]),
            (np.nansum(A[both])-np.nansum(B[both]))/max(abs(np.nansum(B[both])),1e-30)))
dn.close(); do.close()
PYEOF
