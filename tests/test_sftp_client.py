from types import SimpleNamespace

import pytest

from sftp_merger.services.sftp_client import SftpClient, SftpError


class StubSftp:
    def __init__(self, attrs):
        self.attrs = attrs
        self.downloads = []

    def listdir_attr(self, directory):
        return self.attrs

    def get(self, remote, local):
        self.downloads.append((remote, local))


def make_attr(name, mode, size, mtime):
    return SimpleNamespace(filename=name, st_mode=mode, st_size=size, st_mtime=mtime)


def test_list_files_filtre_les_repertoires_et_trie_par_date(tmp_path):
    client = SftpClient()
    client._sftp = StubSftp(
        [
            make_attr("b.csv", 0o100644, 200, 2000),
            make_attr("sous-dossier", 0o040755, 0, 3000),
            make_attr("a.csv", 0o100644, 100, 1000),
        ]
    )
    files = client.list_files("/data")
    assert [f.name for f in files] == ["b.csv", "a.csv"]
    assert files[0].size == 200
    assert client.is_connected


def test_list_files_sans_connexion():
    with pytest.raises(SftpError, match="Non connecté"):
        SftpClient().list_files("/")


def test_download_utilise_le_nom_de_base(tmp_path):
    client = SftpClient()
    stub = StubSftp([])
    client._sftp = stub
    dest = client.download("/data", "../../evil.csv", tmp_path)
    assert dest == tmp_path / "evil.csv"
    assert stub.downloads[0][0] == "/data/evil.csv"


def test_close_sans_connexion_ne_leve_pas():
    SftpClient().close()


def test_host_entry():
    assert SftpClient.host_entry("srv.example.com", 22) == "srv.example.com"
    assert SftpClient.host_entry("srv.example.com", 2222) == "[srv.example.com]:2222"
