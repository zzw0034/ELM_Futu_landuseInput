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
# Must run on a compute node: neither source is reachable from the login nodes.
#
# Primary source is the ESGF replica at DKRZ, not luh.umd.edu: the UMD host
# (gsweb28.umd.edu) has been refusing TCP on both 80 and 443 since at least
# 2026-07-28, while ORNL egress is otherwise healthy. The DKRZ copy is the same
# product -- source_id UofMD-landState-AIM-ssp370-2-1-f ("-2-1-f" = LUH2 v2f),
# version v20171005, identical filename to the UMD one, and the same vintage as
# the ssp460/ssp585 files already on disk (server mtime 2017-10-05). It needs no
# ESGF credentials: the THREDDS fileServer URL returns 200 directly, so none of
# the OpenID/MyProxy machinery in the generated ESGF wget script is required.
#
# URL and checksum taken from the ESGF wget script generated at
# esgf-data.dkrz.de on 2026-07-29 for dataset
#   input4MIPs.CMIP6.ScenarioMIP.UofMD.UofMD-landState-AIM-ssp370-2-1-f
#     .land.yr.multiple-transitions.gn.v20171005

set -uo pipefail

LUH_DIR=/projects/hpcl-cli185/proj-shared/zw5/luh
DEST="$LUH_DIR/ssp3rcp70_transitions.nc"

FNAME=multiple-transitions_input4MIPs_landState_ScenarioMIP_UofMD-AIM-ssp370-2-1-f_gn_2015-2100.nc
DKRZ="https://esgf1.dkrz.de/thredds/fileServer/input4mips/input4MIPs/CMIP6/ScenarioMIP/UofMD/UofMD-landState-AIM-ssp370-2-1-f/land/yr/multiple-transitions/gn/v20171005/$FNAME"
SHA256_EXPECT=159cadf427a4944751d1c0ceb0a5aed965ce9af87e150a88fbe151560bb4d887
SIZE_EXPECT=1430100552

UMD_BASE=https://luh.umd.edu/LUH2/LUH2_v2f
WGET=(wget --no-check-certificate --tries=3 --timeout=60)
CURL=(curl -sk --max-time 60)

cd "$LUH_DIR" || { echo "FATAL: cannot cd to $LUH_DIR"; exit 1; }

if [ -s "$DEST" ]; then
    echo "SKIP: $DEST already exists ($(stat -c %s "$DEST") bytes). Remove it to re-download."
    exit 0
fi

# ---- 1. pick a source -------------------------------------------------------
URL=""
code=$("${CURL[@]}" -o /dev/null -w '%{http_code}' -L -r 0-0 "$DKRZ")
echo "DKRZ (ESGF replica) -> HTTP $code"
if [ "$code" = "200" ] || [ "$code" = "206" ]; then
    URL="$DKRZ"
else
    echo "DKRZ unavailable; falling back to luh.umd.edu ..."
    for sub in AIM AIM_SSP3_RCP70 AIM370 AIM70 AIM_SSP3 AIM-ssp370; do
        cand="$UMD_BASE/$sub/$FNAME"
        c=$("${CURL[@]}" -o /dev/null -w '%{http_code}' -L -r 0-0 "$cand")
        echo "  probe $sub -> HTTP $c"
        if [ "$c" = "200" ] || [ "$c" = "206" ]; then URL="$cand"; break; fi
    done
fi

if [ -z "$URL" ]; then
    echo "FATAL: no source reachable for $FNAME."
    echo "       DKRZ:  $DKRZ"
    echo "       UMD :  $UMD_BASE/<AIM subdir>/$FNAME"
    exit 1
fi

echo "Downloading: $URL"

# ---- 2. download ------------------------------------------------------------
"${WGET[@]}" -c -O "$DEST.part" "$URL" || { echo "FATAL: wget failed"; exit 1; }

# ---- 3. verify before publishing the final name -----------------------------
sz=$(stat -c %s "$DEST.part")
echo "size: $sz (expected $SIZE_EXPECT)"
if [ "$sz" != "$SIZE_EXPECT" ]; then
    echo "FATAL: size mismatch. Left as .part for inspection."
    exit 1
fi

echo -n "sha256: "
sha=$(sha256sum "$DEST.part" | awk '{print $1}')
echo "$sha"
if [ "$sha" != "$SHA256_EXPECT" ]; then
    echo "FATAL: checksum mismatch (expected $SHA256_EXPECT). Left as .part."
    exit 1
fi

mv "$DEST.part" "$DEST"
echo "OK: $DEST ($sz bytes, sha256 verified)"
ls -lh "$DEST"
