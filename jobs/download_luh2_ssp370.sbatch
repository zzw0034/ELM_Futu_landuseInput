#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -J download_luh2_ssp370
#SBATCH -t 02:00:00
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=8g
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/luh/download_luh2_ssp370_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/luh/download_luh2_ssp370_%j.err

# Fetch the LUH2 v2f SSP3-7.0 transitions file, to pair with the Chen2022
# SSP3_RCP70 land-use trend in 02_harmonize_seus.py (Stage B wood harvest).
#
# Must run on a compute node: luh.umd.edu:443 is refused from the login nodes.
# The server's certificate is not trusted by the system CA bundle, so
# --no-check-certificate is required (same as the ssp119/245/460/585 pulls).
#
# The per-IAM subdirectory under LUH2_v2f/ is NOT uniform across scenarios
# (observed: IMAGE_SSP1_RCP19/, MESSAGE/, GCAM60/, MAGPIE/), so the correct
# path for AIM/ssp370 is discovered rather than assumed.

set -uo pipefail

LUH_DIR=/projects/hpcl-cli185/proj-shared/zw5/luh
BASE=https://luh.umd.edu/LUH2/LUH2_v2f
FNAME=multiple-transitions_input4MIPs_landState_ScenarioMIP_UofMD-AIM-ssp370-2-1-f_gn_2015-2100.nc
DEST="$LUH_DIR/ssp3rcp70_transitions.nc"

WGET=(wget --no-check-certificate --tries=3 --timeout=60)
CURL=(curl -sk --max-time 60)

cd "$LUH_DIR" || { echo "FATAL: cannot cd to $LUH_DIR"; exit 1; }

if [ -s "$DEST" ]; then
    echo "SKIP: $DEST already exists ($(stat -c %s "$DEST") bytes). Remove it to re-download."
    exit 0
fi

# ---- 1. locate the file -----------------------------------------------------
URL=""
for sub in AIM AIM_SSP3_RCP70 AIM370 AIM70 AIM_SSP3 AIM-ssp370; do
    cand="$BASE/$sub/$FNAME"
    code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' -r 0-0 "$cand")
    echo "probe $sub -> HTTP $code"
    if [ "$code" = "200" ] || [ "$code" = "206" ]; then
        URL="$cand"
        break
    fi
done

# Fallback: parse the v2f index for any ssp370 transitions link.
if [ -z "$URL" ]; then
    echo "No candidate subdirectory matched; parsing $BASE/ index ..."
    hit=$("${CURL[@]}" "$BASE/" \
          | grep -oE 'href="[^"]*ssp370[^"]*transitions[^"]*\.nc"' \
          | head -1 | sed 's/^href="//; s/"$//')
    if [ -n "$hit" ]; then
        case "$hit" in
            http*) URL="$hit" ;;
            /*)    URL="https://luh.umd.edu$hit" ;;
            *)     URL="$BASE/$hit" ;;
        esac
        echo "index gave: $URL"
    fi
fi

if [ -z "$URL" ]; then
    echo "FATAL: could not locate the ssp370 transitions file under $BASE/."
    echo "       Open https://luh.umd.edu/data.shtml and read the LUH2 v2f"
    echo "       scenario table for the AIM/SSP3-7.0 path, then set URL by hand."
    exit 1
fi

echo "Downloading: $URL"

# ---- 2. download ------------------------------------------------------------
"${WGET[@]}" -c -O "$DEST.part" "$URL" || {
    echo "FATAL: wget failed for $URL"
    exit 1
}

# ---- 3. sanity-check before publishing the final name -----------------------
sz=$(stat -c %s "$DEST.part")
if [ "$sz" -lt 500000000 ]; then
    echo "FATAL: $DEST.part is only $sz bytes; the sibling scenario files are 1.3-1.6 GB."
    echo "       Left in place as .part for inspection."
    exit 1
fi

magic=$(head -c 4 "$DEST.part" | tr -d '\0')
case "$magic" in
    CDF*|*HDF*) : ;;
    *) echo "FATAL: $DEST.part is not netCDF/HDF5 (magic='$magic'); probably an error page."
       exit 1 ;;
esac

mv "$DEST.part" "$DEST"
echo "OK: $DEST ($sz bytes)"
ls -lh "$DEST"
