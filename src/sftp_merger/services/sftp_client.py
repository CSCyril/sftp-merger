from __future__ import annotations

import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..models import RemoteFile

if TYPE_CHECKING:
    import paramiko

HostConfirmCallback = Callable[[str, int, str], bool]

KNOWN_HOSTS_PATH = Path.home() / ".ssh" / "known_hosts"


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

    @staticmethod
    def host_entry(host: str, port: int) -> str:
        return host if port == 22 else f"[{host}]:{port}"

    def connect(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        confirm_unknown_host: HostConfirmCallback | None = None,
    ) -> None:
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
        except paramiko.SSHException as exc:
            if "not found in known_hosts" not in str(exc):
                ssh.close()
                raise SftpError(str(exc)) from exc
            key = self._fetch_server_key(host, port)
            fingerprint = ":".join(f"{b:02x}" for b in key.get_fingerprint())
            accepted = confirm_unknown_host is not None and confirm_unknown_host(
                host, port, fingerprint
            )
            if not accepted:
                ssh.close()
                raise SftpError(
                    f"Clé d'hôte inconnue pour {host}:{port} — connexion refusée."
                ) from exc
            self._persist_server_key(host, port, key)
            ssh.get_host_keys().add(self.host_entry(host, port), key.get_name(), key)
            try:
                ssh.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    timeout=self.timeout,
                )
            except Exception as retry_exc:
                ssh.close()
                raise SftpError(str(retry_exc)) from retry_exc
        self._ssh = ssh
        self._sftp = ssh.open_sftp()

    def _fetch_server_key(self, host: str, port: int):
        import paramiko

        transport = paramiko.Transport((host, port))
        try:
            transport.start_client(timeout=self.timeout)
            return transport.get_remote_server_key()
        except Exception as exc:
            raise SftpError(
                f"Impossible de récupérer la clé du serveur {host}:{port} : {exc}"
            ) from exc
        finally:
            transport.close()

    def _persist_server_key(self, host: str, port: int, key) -> None:
        import paramiko

        host_keys = paramiko.HostKeys()
        if KNOWN_HOSTS_PATH.exists():
            host_keys.load(str(KNOWN_HOSTS_PATH))
        host_keys.add(self.host_entry(host, port), key.get_name(), key)
        KNOWN_HOSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        host_keys.save(str(KNOWN_HOSTS_PATH))

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
