from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RemoteFile:
    name: str
    modified: datetime
    size: int

    @property
    def size_human(self) -> str:
        value = float(self.size)
        for unit in ("o", "Ko", "Mo", "Go", "To"):
            if value < 1024 or unit == "To":
                if unit == "o":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}".replace(".", ",")
            value /= 1024
        return f"{value:.1f} To"


@dataclass
class MergeReport:
    files_merged: int = 0
    rows_written: int = 0
    unmatched_refs: list[str] = field(default_factory=list)
