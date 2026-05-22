from __future__ import annotations

import zipfile
from pathlib import Path


def make_zip(zip_path: Path, file_paths: list[Path]) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in file_paths:
            zf.write(p, arcname=p.name)
    return zip_path
