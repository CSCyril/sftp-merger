from __future__ import annotations

import stat
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..models import RemoteFile

if TYPE_CHECKING:
    import paramiko


class SftpError(Exception):
    pass


class SftpClient:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    @property
    def is_connected(self) -> bool:
        return self._sftp is not None

    def connect(self, host: str, port: int, user: str, password: str) -> None:
        import paramiko

        self.close()
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            ssh.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                timeout=self.timeout,
            )
        except Exception as exc:
            ssh.close()
            raise SftpError(str(exc)) from exc
        self._ssh = ssh
        self._sftp = ssh.open_sftp()

    def list_files(self, directory: str) -> list[RemoteFile]:
        if self._sftp is None:
            raise SftpError("Non connecté au serveur SFTP.")
        files: list[RemoteFile] = []
        for attr in self._sftp.listdir_attr(directory):
            if not stat.S_ISREG(attr.st_mode or 0):
                continue
            files.append(
                RemoteFile(
                    name=attr.filename,
                    modified=datetime.fromtimestamp(attr.st_mtime or 0),
                    size=attr.st_size or 0,
                )
            )
        files.sort(key=lambda f: f.modified, reverse=True)
        return files

    def download(self, directory: str, filename: str, dest_dir: Path) -> Path:
        if self._sftp is None:
            raise SftpError("Non connecté au serveur SFTP.")
        safe_name = Path(filename).name
        remote = directory.rstrip("/") + "/" + safe_name
        dest = dest_dir / safe_name
        self._sftp.get(remote, str(dest))
        return dest

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None
