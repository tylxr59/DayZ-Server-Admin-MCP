from __future__ import annotations

import base64
import io
import posixpath
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP, FTP_TLS, error_perm

import paramiko
from paramiko import SFTPClient, SSHClient

from .config import RemoteConfig


class RemoteError(RuntimeError):
    pass


class WriteDisabledError(RemoteError):
    pass


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    path: str
    type: str
    size: int | None = None
    modified: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "size": self.size,
            "modified": self.modified,
        }


class DayZRemoteClient:
    def __init__(self, config: RemoteConfig):
        self.config = config

    @contextmanager
    def connect_ftp(self) -> Iterator[FTP]:
        ftp_cls: type[FTP] = FTP_TLS if self.config.protocol == "ftps" else FTP
        ftp = ftp_cls(timeout=self.config.timeout_seconds)
        try:
            ftp.connect(self.config.host, self.config.port)
            ftp.login(self.config.user, self.config.password)
            if isinstance(ftp, FTP_TLS):
                ftp.prot_p()
            ftp.set_pasv(self.config.passive)
            yield ftp
        except Exception as exc:
            raise RemoteError(str(exc)) from exc
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()

    @contextmanager
    def connect_sftp(self) -> Iterator[SFTPClient]:
        ssh = SSHClient()
        sftp: SFTPClient | None = None
        try:
            if self.config.strict_host_key_checking:
                ssh.load_system_host_keys()
                if self.config.known_hosts_file:
                    ssh.load_host_keys(self.config.known_hosts_file)
                ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                self.config.host,
                port=self.config.port,
                username=self.config.user,
                password=self.config.password,
                timeout=self.config.timeout_seconds,
                banner_timeout=self.config.timeout_seconds,
                auth_timeout=self.config.timeout_seconds,
                look_for_keys=False,
                allow_agent=False,
            )
            sftp = ssh.open_sftp()
            yield sftp
        except Exception as exc:
            raise RemoteError(str(exc)) from exc
        finally:
            if sftp is not None:
                sftp.close()
            ssh.close()

    def resolve_path(self, path: str | None = None) -> str:
        raw_path = (path or "").strip()
        root = posixpath.normpath(self.config.root)
        if root != "/" and root.endswith("/"):
            root = root.rstrip("/")

        if not raw_path or raw_path == ".":
            candidate = root
        else:
            relative = raw_path.lstrip("/")
            candidate = posixpath.normpath(posixpath.join(root, relative))

        if root == "/":
            return candidate if candidate.startswith("/") else f"/{candidate}"

        if candidate != root and not candidate.startswith(f"{root}/"):
            raise ValueError(f"Path escapes configured remote root: {path}")

        return candidate

    def relative_path(self, absolute_path: str) -> str:
        root = posixpath.normpath(self.config.root)
        if root == "/":
            return absolute_path
        if absolute_path == root:
            return "."
        return absolute_path.removeprefix(f"{root}/")

    def ensure_writes_allowed(self) -> None:
        if not self.config.allow_writes:
            raise WriteDisabledError(
                "Write tools are disabled. Set DAYZ_MCP_ALLOW_WRITES=true to enable them."
            )

    def test_connection(self) -> dict[str, str | int | bool]:
        if self.config.protocol == "sftp":
            return self._test_sftp_connection()
        return self._test_ftp_connection()

    def list_directory(self, path: str = ".") -> list[dict[str, str | int | None]]:
        if self.config.protocol == "sftp":
            entries = self._list_sftp_directory(path)
        else:
            entries = self._list_ftp_directory(path)
        entries.sort(key=lambda item: (item.type != "dir", item.name.lower()))
        return [entry.to_dict() for entry in entries]

    def read_bytes(self, path: str, max_bytes: int | None = None) -> bytes:
        limit = max_bytes or self.config.max_read_bytes
        if limit > self.config.max_read_bytes:
            raise ValueError(
                f"max_bytes cannot exceed configured limit {self.config.max_read_bytes}"
            )

        if self.config.protocol == "sftp":
            return self._read_sftp_bytes(path, limit)
        return self._read_ftp_bytes(path, limit)

    def read_text(
        self,
        path: str,
        encoding: str = "utf-8",
        max_bytes: int | None = None,
    ) -> str:
        data = self.read_bytes(path, max_bytes=max_bytes)
        return data.decode(encoding)

    def read_base64(self, path: str, max_bytes: int | None = None) -> dict[str, str | int]:
        data = self.read_bytes(path, max_bytes=max_bytes)
        return {
            "path": path,
            "bytes": len(data),
            "base64": base64.b64encode(data).decode("ascii"),
        }

    def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_backup: bool = True,
    ) -> dict[str, str | int | bool | None]:
        self.ensure_writes_allowed()
        data = content.encode(encoding)

        if self.config.protocol == "sftp":
            backup_path = self._write_sftp_bytes(path, data, create_backup)
        else:
            backup_path = self._write_ftp_bytes(path, data, create_backup)

        return {
            "path": path,
            "bytes": len(data),
            "backup_path": self.relative_path(backup_path) if backup_path else None,
            "wrote": True,
        }

    def upload_base64(
        self,
        path: str,
        content_base64: str,
        create_backup: bool = True,
    ) -> dict[str, str | int | bool | None]:
        self.ensure_writes_allowed()
        data = base64.b64decode(content_base64, validate=True)

        if self.config.protocol == "sftp":
            backup_path = self._write_sftp_bytes(path, data, create_backup)
        else:
            backup_path = self._write_ftp_bytes(path, data, create_backup)

        return {
            "path": path,
            "bytes": len(data),
            "backup_path": self.relative_path(backup_path) if backup_path else None,
            "uploaded": True,
        }

    def make_directory(self, path: str) -> dict[str, str | bool]:
        self.ensure_writes_allowed()
        absolute = self.resolve_path(path)
        if self.config.protocol == "sftp":
            with self.connect_sftp() as sftp:
                sftp.mkdir(absolute)
        else:
            with self.connect_ftp() as ftp:
                ftp.mkd(absolute)
        return {"path": path, "created": True}

    def rename(self, source: str, destination: str) -> dict[str, str | bool]:
        self.ensure_writes_allowed()
        source_absolute = self.resolve_path(source)
        destination_absolute = self.resolve_path(destination)
        if self.config.protocol == "sftp":
            with self.connect_sftp() as sftp:
                sftp.rename(source_absolute, destination_absolute)
        else:
            with self.connect_ftp() as ftp:
                ftp.rename(source_absolute, destination_absolute)
        return {"source": source, "destination": destination, "renamed": True}

    def _test_sftp_connection(self) -> dict[str, str | int | bool]:
        root = self.resolve_path(".")
        with self.connect_sftp() as sftp:
            normalized_root = sftp.normalize(root)
            sftp.chdir(normalized_root)
            return {
                "connected": True,
                "protocol": self.config.protocol,
                "server_cwd": sftp.getcwd() or "",
                "resolved_root": normalized_root,
            }

    def _test_ftp_connection(self) -> dict[str, str | int | bool]:
        root = self.resolve_path(".")
        with self.connect_ftp() as ftp:
            pwd = ftp.pwd()
            ftp.cwd(root)
            return {
                "connected": True,
                "protocol": self.config.protocol,
                "server_cwd": pwd,
                "resolved_root": root,
                "welcome": ftp.getwelcome() or "",
            }

    def _list_sftp_directory(self, path: str) -> list[RemoteEntry]:
        absolute = self.resolve_path(path)
        entries: list[RemoteEntry] = []
        with self.connect_sftp() as sftp:
            for attrs in sftp.listdir_attr(absolute):
                name = attrs.filename
                if name in {".", ".."}:
                    continue
                entry_absolute = posixpath.join(absolute, name)
                entries.append(
                    RemoteEntry(
                        name=name,
                        path=self.relative_path(entry_absolute),
                        type=_mode_type(attrs.st_mode),
                        size=attrs.st_size,
                        modified=_format_unix_time(attrs.st_mtime),
                    )
                )
        return entries

    def _list_ftp_directory(self, path: str) -> list[RemoteEntry]:
        absolute = self.resolve_path(path)
        with self.connect_ftp() as ftp:
            entries = list(self._list_ftp_with_mlsd(ftp, absolute))
            if not entries:
                entries = list(self._list_ftp_with_nlst(ftp, absolute))
        return entries

    def _read_sftp_bytes(self, path: str, limit: int) -> bytes:
        absolute = self.resolve_path(path)
        with self.connect_sftp() as sftp:
            size = sftp.stat(absolute).st_size
            if size is not None and size > limit:
                raise ValueError(f"File is {size} bytes, which exceeds limit {limit}")

            buffer = io.BytesIO()
            with sftp.open(absolute, "rb") as remote_file:
                while True:
                    chunk = remote_file.read(65_536)
                    if not chunk:
                        break
                    if buffer.tell() + len(chunk) > limit:
                        raise ValueError(f"File exceeds read limit {limit} bytes")
                    buffer.write(chunk)
            return buffer.getvalue()

    def _read_ftp_bytes(self, path: str, limit: int) -> bytes:
        absolute = self.resolve_path(path)
        with self.connect_ftp() as ftp:
            try:
                size = ftp.size(absolute)
            except Exception:
                size = None

            if size is not None and size > limit:
                raise ValueError(f"File is {size} bytes, which exceeds limit {limit}")

            buffer = io.BytesIO()

            def append(chunk: bytes) -> None:
                if buffer.tell() + len(chunk) > limit:
                    raise ValueError(f"File exceeds read limit {limit} bytes")
                buffer.write(chunk)

            ftp.retrbinary(f"RETR {absolute}", append)
            return buffer.getvalue()

    def _write_sftp_bytes(
        self,
        path: str,
        data: bytes,
        create_backup: bool,
    ) -> str | None:
        absolute = self.resolve_path(path)
        backup_path = None

        with self.connect_sftp() as sftp:
            if create_backup and self._sftp_exists(sftp, absolute):
                backup_path = self._backup_existing_sftp_file(sftp, absolute)

            with sftp.open(absolute, "wb") as remote_file:
                remote_file.write(data)

        return backup_path

    def _write_ftp_bytes(
        self,
        path: str,
        data: bytes,
        create_backup: bool,
    ) -> str | None:
        absolute = self.resolve_path(path)
        backup_path = None

        with self.connect_ftp() as ftp:
            if create_backup and self._ftp_exists(ftp, absolute):
                backup_path = self._backup_existing_ftp_file(ftp, absolute)

            ftp.storbinary(f"STOR {absolute}", io.BytesIO(data))

        return backup_path

    def _list_ftp_with_mlsd(self, ftp: FTP, absolute: str) -> Iterator[RemoteEntry]:
        try:
            for name, facts in ftp.mlsd(absolute):
                if name in {".", ".."}:
                    continue
                entry_type = facts.get("type", "unknown")
                size = _safe_int(facts.get("size"))
                modified = _format_mlsd_time(facts.get("modify"))
                entry_absolute = posixpath.join(absolute, name)
                yield RemoteEntry(
                    name=name,
                    path=self.relative_path(entry_absolute),
                    type=entry_type,
                    size=size,
                    modified=modified,
                )
        except error_perm:
            return

    def _list_ftp_with_nlst(self, ftp: FTP, absolute: str) -> Iterator[RemoteEntry]:
        try:
            names = ftp.nlst(absolute)
        except error_perm:
            return

        for item in names:
            name = posixpath.basename(item.rstrip("/"))
            if name in {"", ".", ".."}:
                continue
            entry_absolute = item if item.startswith("/") else posixpath.join(absolute, item)
            entry_type = "dir" if self._ftp_is_directory(ftp, entry_absolute) else "file"
            size = None
            if entry_type == "file":
                try:
                    size = ftp.size(entry_absolute)
                except Exception:
                    size = None
            yield RemoteEntry(
                name=name,
                path=self.relative_path(entry_absolute),
                type=entry_type,
                size=size,
            )

    def _ftp_is_directory(self, ftp: FTP, absolute: str) -> bool:
        current = ftp.pwd()
        try:
            ftp.cwd(absolute)
            return True
        except Exception:
            return False
        finally:
            try:
                ftp.cwd(current)
            except Exception:
                pass

    def _ftp_exists(self, ftp: FTP, absolute: str) -> bool:
        try:
            ftp.size(absolute)
            return True
        except Exception:
            parent = posixpath.dirname(absolute) or "/"
            name = posixpath.basename(absolute)
            try:
                return name in {posixpath.basename(item) for item in ftp.nlst(parent)}
            except Exception:
                return False

    def _sftp_exists(self, sftp: SFTPClient, absolute: str) -> bool:
        try:
            sftp.stat(absolute)
            return True
        except OSError:
            return False

    def _backup_existing_sftp_file(self, sftp: SFTPClient, absolute: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_absolute = f"{absolute}.bak.{timestamp}"
        with sftp.open(absolute, "rb") as source:
            with sftp.open(backup_absolute, "wb") as destination:
                while True:
                    chunk = source.read(65_536)
                    if not chunk:
                        break
                    destination.write(chunk)
        return backup_absolute

    def _backup_existing_ftp_file(self, ftp: FTP, absolute: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_absolute = f"{absolute}.bak.{timestamp}"
        buffer = io.BytesIO()
        ftp.retrbinary(f"RETR {absolute}", buffer.write)
        buffer.seek(0)
        ftp.storbinary(f"STOR {backup_absolute}", buffer)
        return backup_absolute


def _mode_type(mode: int | None) -> str:
    if mode is None:
        return "unknown"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "link"
    return "other"


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _format_mlsd_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return value
    return parsed.isoformat()


def _format_unix_time(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


FtpError = RemoteError
DayZFtpClient = DayZRemoteClient
