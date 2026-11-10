"""Fetch the Köppen-Geiger climate raster that the climate-zone textures and the base tints are built from.

Beck and others (2023), 1 km, 1991 to 2020, CC BY 4.0, figshare article 21789074. The 131 MB zip is checked against the
published md5 and only the one GeoTIFF is kept, at data/raw/climate/1991_2020/ (git-ignored with the rest of data/raw).
render_region.py and render_demo.py call `ensure()`, so a fresh checkout downloads it the first time it is needed and never again.

  python scripts/fetch_climate.py          # fetch if absent
  python scripts/fetch_climate.py --force  # fetch again
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
KOPPEN = ROOT / "data" / "raw" / "climate" / "1991_2020" / "koppen_geiger_0p00833333.tif"
URL = "https://ndownloader.figshare.com/files/61012822"  # koppen_geiger_tif.zip
MD5 = "7fc2f5a15d4f5fe0ce59c9a9b502aa09"
MEMBER = "1991_2020/koppen_geiger_0p00833333.tif"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure(dest: Path = KOPPEN, force: bool = False) -> Path:
    """The raster's path, downloading it first when it is not on disk."""
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "koppen_geiger_tif.zip"
        print(f"fetching Köppen-Geiger 1991-2020 (131 MB) from {URL}")
        with requests.get(URL, stream=True, timeout=120) as r:
            r.raise_for_status()
            with zpath.open("wb") as f:
                for block in r.iter_content(1 << 20):
                    f.write(block)
        if md5_of(zpath) != MD5:
            raise RuntimeError("Köppen-Geiger download failed its md5 check; delete nothing and retry")
        with zipfile.ZipFile(zpath) as z:
            name = next((n for n in z.namelist() if n.replace("\\", "/").endswith(MEMBER)), None)
            if name is None:
                raise RuntimeError(f"{MEMBER} not found in the Köppen-Geiger zip")
            with z.open(name) as src, dest.open("wb") as out:
                while block := src.read(1 << 20):
                    out.write(block)
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true")
    print(ensure(force=ap.parse_args().force))
