from sftp_merger.config import SftpConfig


def test_aller_retour(tmp_path):
    cfg = SftpConfig(host="srv", port=2222, user="u", password="p", directory="/data")
    path = tmp_path / "config.ini"
    cfg.save(path)
    assert SftpConfig.load(path) == cfg


def test_chargement_fichier_absent(tmp_path):
    assert SftpConfig.load(tmp_path / "absent.ini") == SftpConfig()


def test_port_invalide_retombe_sur_22(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[SFTP]\nhost = h\nport = abc\nuser = u\npassword = p\ndirectory = /\n")
    assert SftpConfig.load(path).port == 22


def test_validate():
    assert SftpConfig().validate() != []
    assert SftpConfig(host="h", port=22, user="u", directory="/").validate() == []
    assert SftpConfig(host="h", port=99999, user="u", directory="/").validate() != []
    assert SftpConfig(host="h", port=22, user="u", directory="relatif").validate() != []
