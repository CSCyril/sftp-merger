import pytest

from sftp_merger.services.mapping import load_mapping


def test_load_mapping(tmp_path):
    p = tmp_path / "mapping.csv"
    p.write_text("REF-1;Titre A\nREF-2;Titre B\n\n;ignore\n", encoding="cp1252")
    assert load_mapping(p) == {"REF-1": "Titre A", "REF-2": "Titre B"}


def test_load_mapping_fichier_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_mapping(tmp_path / "absent.csv")
