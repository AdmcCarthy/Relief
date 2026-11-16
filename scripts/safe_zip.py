"""Extract a downloaded zip without trusting its member paths."""
from __future__ import annotations

import zipfile
from pathlib import Path


def extract_all(z: zipfile.ZipFile, dest: Path) -> None:
    """Like ZipFile.extractall, but a member that would land outside `dest` stops the extraction."""
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for member in z.infolist():
        target = (dest / member.filename).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"unsafe path in archive: {member.filename}")
        z.extract(member, dest)
