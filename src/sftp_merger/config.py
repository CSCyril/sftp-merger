from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path("config.ini")


@dataclass
class SftpConfig:
    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    directory: str = "/"

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> SftpConfig:
        parser = configparser.RawConfigParser()
        if not path.exists():
            return cls()
        parser.read(path, encoding="utf-8")
        if not parser.has_section("SFTP"):
            return cls()
        section = parser["SFTP"]
        try:
            port = int(section.get("port", "22"))
        except ValueError:
            port = 22
        return cls(
            host=section.get("host", ""),
            port=port,
            user=section.get("user", ""),
            password=section.get("password", ""),
            directory=section.get("directory", "/"),
        )

    def save(self, path: Path = CONFIG_PATH) -> None:
        parser = configparser.RawConfigParser()
        parser["SFTP"] = {
            "host": self.host,
            "port": str(self.port),
            "user": self.user,
            "password": self.password,
            "directory": self.directory,
        }
        with open(path, "w", encoding="utf-8") as f:
            parser.write(f)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def validate(self) -> list[str]:
        errors = []
        if not self.host.strip():
            errors.append("Le serveur est requis.")
        if not 0 < self.port < 65536:
            errors.append("Le port doit être compris entre 1 et 65535.")
        if not self.user.strip():
            errors.append("L'utilisateur est requis.")
        if not self.directory.startswith("/"):
            errors.append("Le répertoire doit être un chemin absolu (commençant par /).")
        return errors
