from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Columns:
    ref_produit: int = 13
    titre: int = 14
    total_ttc: int = 6
    port_ttc: int = 8
    tags: int = 64
    remise_produit_ht: int = 70
    remise_produit_tva: int = 71

    @classmethod
    def resolve(cls, header: list[str]) -> Columns:
        def find(default: int, *needles: str) -> int:
            for index, cell in enumerate(header):
                low = cell.strip().lower()
                if any(needle in low for needle in needles):
                    return index
            return default

        return cls(
            total_ttc=find(6, "totalpricecents"),
            port_ttc=find(8, "totalshippingtaxincludedcents"),
            tags=find(64, "tags"),
        )
