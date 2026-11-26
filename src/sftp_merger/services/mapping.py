from __future__ import annotations

import csv
from pathlib import Path


def load_mapping(path: Path | str = "mapping.csv") -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier mapping non trouvé : {path}")
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="cp1252", newline="") as f:
        for row in csv.reader(f, delimiter=";"):
            if len(row) >= 2 and row[0].strip():
                mapping[row[0].strip()] = row[1].strip()
    return mapping
