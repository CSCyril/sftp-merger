from __future__ import annotations

import csv
import re
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..columns import Columns
from ..models import MergeReport

ProgressCallback = Callable[[int, int], None]

ENCODINGS = ("utf-8-sig", "cp1252")
SAMPLE_SIZE = 262144


def to_int_cents(value: object) -> int:
    s = str(value).strip().replace(" ", "").replace(",", ".")
    return int(round(float(s)))


def parse_remises(row: Sequence[str], cols: Columns) -> tuple[int, int]:
    remise_produit_ttc = 0
    try:
        disc = to_int_cents(row[cols.remise_produit_ht] or 0)
        tax = to_int_cents(row[cols.remise_produit_tva] or 0)
        remise_produit_ttc = -(disc + tax)
    except (IndexError, ValueError):
        remise_produit_ttc = 0

    total_remise_ttc = 0
    if len(row) > cols.tags:
        m = re.search(
            r"Manomano discount:\s*([0-9]+(?:[.,][0-9]+)?)",
            str(row[cols.tags]),
            re.IGNORECASE,
        )
        if m:
            brut = m.group(1)
            if re.search(r"[.,]", brut):
                total_remise_ttc = int(round(float(brut.replace(",", ".")) * 100))
            else:
                total_remise_ttc = int(brut)
    return remise_produit_ttc, total_remise_ttc


def detect_separator(line: str) -> str:
    try:
        return csv.Sniffer().sniff(line, delimiters=";,\t|").delimiter
    except csv.Error:
        return max(";,\t|", key=lambda s: line.count(s))


@contextmanager
def open_csv_text(path: Path, sample_size: int = SAMPLE_SIZE) -> Iterator:
    handle = None
    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS:
        try:
            candidate = open(path, "r", encoding=encoding, newline="")
            candidate.read(sample_size)
            candidate.seek(0)
            handle = candidate
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            candidate.close()
    if handle is None:
        if last_error is not None:
            raise last_error
        raise UnicodeDecodeError("unknown", b"", 0, 1, "aucun encodage testé ne convient")
    try:
        yield handle
    finally:
        handle.close()


def _transform_row(
    row: list[str],
    cols: Columns,
    mapping: dict[str, str],
    report: MergeReport,
) -> None:
    if len(row) > cols.titre:
        cle = str(row[cols.ref_produit]).strip()
        if cle in mapping:
            row[cols.titre] = mapping[cle]
        elif cle:
            report.unmatched_refs.append(cle)

    remise_produit_ttc, total_remise_ttc = parse_remises(row, cols)
    coupon_port = max(total_remise_ttc - remise_produit_ttc, 0)

    if len(row) > cols.port_ttc and str(row[cols.port_ttc]).strip():
        try:
            row[cols.port_ttc] = str(to_int_cents(row[cols.port_ttc]) + coupon_port)
        except ValueError:
            pass

    if len(row) > cols.total_ttc and str(row[cols.total_ttc]).strip():
        try:
            row[cols.total_ttc] = str(to_int_cents(row[cols.total_ttc]) + total_remise_ttc)
        except ValueError:
            pass


def merge_csv(
    files: Sequence[Path],
    output: Path,
    mapping: dict[str, str],
    on_progress: ProgressCallback | None = None,
) -> MergeReport:
    report = MergeReport()
    if not files:
        return report

    header: list[str] | None = None
    cols = Columns()

    with open(output, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL)
        for index, file in enumerate(files, start=1):
            with open_csv_text(file) as infile:
                first_line = infile.readline()
                sep = detect_separator(first_line)
                infile.seek(0)
                reader = csv.reader(infile, delimiter=sep)
                current_header = next(reader, None)
                if current_header is None:
                    continue
                if header is None:
                    header = current_header
                    cols = Columns.resolve(header)
                    writer.writerow(header)
                elif current_header != header:
                    raise ValueError(
                        f"En-tête incompatible dans {file.name} : "
                        f"{len(current_header)} colonnes reçues, {len(header)} attendues."
                    )
                for row in reader:
                    if not row:
                        continue
                    _transform_row(row, cols, mapping, report)
                    writer.writerow(row)
                    report.rows_written += 1
            report.files_merged += 1
            if on_progress is not None:
                on_progress(index, len(files))

    report.unmatched_refs = sorted(set(report.unmatched_refs))
    return report
