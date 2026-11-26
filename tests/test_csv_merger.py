import csv

import pytest

from sftp_merger.columns import Columns
from sftp_merger.services.csv_merger import (
    detect_separator,
    merge_csv,
    parse_remises,
    to_int_cents,
)

HEADER = [f"col{i}" for i in range(72)]


def make_row(
    ref="REF-1",
    total="10000",
    port="500",
    tags="Manomano discount: 1500",
    disc="-200",
    tax="-40",
):
    row = ["0"] * 72
    row[6] = total
    row[8] = port
    row[13] = ref
    row[14] = "Titre original"
    row[64] = tags
    row[70] = disc
    row[71] = tax
    return row


def write_csv(path, rows, sep=";", encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.writer(f, delimiter=sep)
        writer.writerow(HEADER)
        writer.writerows(rows)


def test_to_int_cents():
    assert to_int_cents("1234") == 1234
    assert to_int_cents("1234.0") == 1234
    assert to_int_cents(" 12,4 ") == 12


def test_parse_remises_valeur_entiere_en_centimes():
    row = make_row(tags="Manomano discount: 1500")
    remise_produit, total = parse_remises(row, Columns())
    assert remise_produit == 240
    assert total == 1500


def test_parse_remises_valeur_decimale_en_euros():
    row = make_row(tags="Remise Manomano discount: 15,50 euros")
    _, total = parse_remises(row, Columns())
    assert total == 1550


def test_parse_remises_sans_remise():
    row = make_row(tags="", disc="0", tax="0")
    remise_produit, total = parse_remises(row, Columns())
    assert (remise_produit, total) == (0, 0)


def test_detect_separator():
    assert detect_separator("a;b;c;d") == ";"
    assert detect_separator("a,b,c") == ","
    assert detect_separator("a\tb\tc") == "\t"


def test_columns_resolve_depuis_entete():
    header = ["x"] * 72
    header[3] = "totalPriceCents"
    header[9] = "totalShippingTaxIncludedCents"
    header[40] = "Tags"
    cols = Columns.resolve(header)
    assert cols.total_ttc == 3
    assert cols.port_ttc == 9
    assert cols.tags == 40


def test_merge_csv_transformations(tmp_path):
    f1 = tmp_path / "a.csv"
    f2 = tmp_path / "b.csv"
    write_csv(f1, [make_row(ref="REF-1")])
    write_csv(f2, [make_row(ref="REF-2", total="200", port="0", tags="", disc="0", tax="0")])
    out = tmp_path / "out.csv"

    report = merge_csv([f1, f2], out, {"REF-1": "Nouveau titre"})

    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == HEADER
    assert len(rows) == 3
    r1 = rows[1]
    assert r1[14] == "Nouveau titre"
    assert r1[6] == str(10000 + 1500)
    assert r1[8] == str(500 + (1500 - 240))
    r2 = rows[2]
    assert r2[6] == "200"
    assert r2[8] == "0"
    assert r2[14] == "Titre original"
    assert report.unmatched_refs == ["REF-2"]
    assert report.files_merged == 2
    assert report.rows_written == 2


def test_merge_csv_entete_incompatible(tmp_path):
    f1 = tmp_path / "a.csv"
    f2 = tmp_path / "b.csv"
    write_csv(f1, [make_row()])
    with open(f2, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["autre"] * 10)
        writer.writerow(make_row())
    with pytest.raises(ValueError, match="En-tête incompatible"):
        merge_csv([f1, f2], tmp_path / "out.csv", {})


def test_merge_csv_fichier_cp1252(tmp_path):
    f1 = tmp_path / "a.csv"
    row = make_row(tags="")
    row[14] = "Titre accentué éèà"
    write_csv(f1, [row], encoding="cp1252")
    out = tmp_path / "out.csv"

    merge_csv([f1], out, {})

    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[1][14] == "Titre accentué éèà"


def test_merge_csv_separateur_virgule(tmp_path):
    f1 = tmp_path / "a.csv"
    write_csv(f1, [make_row()], sep=",")
    out = tmp_path / "out.csv"

    report = merge_csv([f1], out, {})

    assert report.rows_written == 1
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 2
