from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

_PROTOCOLS = {"ftp", "ftps", "sftp"}
DEFAULT_CONFIG_PATH = Path("dayz-server-admin-mcp.toml")


def _load_config_file() -> dict[str, Any]:
    raw_config_path = os.getenv("DAYZ_MCP_CONFIG")
    config_path = Path(raw_config_path) if raw_config_path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        if raw_config_path:
            raise ValueError(f"Config file not found: {config_path}")
        return {}

    with config_path.open("rb") as file:
        loaded = tomllib.load(file)

    if not isinstance(loaded, dict):
        raise ValueError(f"{config_path} must contain a TOML table")

    return loaded


def _config_section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"[{name}] in config file must be a TOML table")
    return value


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value != "":
            return value
    return default


def _first_config(section: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = section.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_setting(
    env_names: tuple[str, ...],
    section: Mapping[str, Any],
    config_keys: tuple[str, ...],
    *,
    default: Any = None,
) -> Any:
    env_value = _first_env(*env_names)
    if env_value is not None:
        return env_value

    config_value = _first_config(section, *config_keys)
    if config_value is not None:
        return config_value

    return default


def _parse_bool_value(name: str, raw: Any, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in {0, 1}:
        return bool(raw)

    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value")


def _parse_bool(name: str, default: bool) -> bool:
    return _parse_bool_value(name, os.getenv(name), default)


def _parse_int_value(
    name: str,
    raw: Any,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be an integer")

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")

    return value


def _parse_str_value(name: str, raw: Any, default: str | None = None) -> str | None:
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise ValueError(f"{name} must be a string")
    return raw


@dataclass(frozen=True)
class RemoteConfig:
    host: str
    user: str
    password: str
    protocol: str = "sftp"
    root: str = "/"
    port: int = 22
    passive: bool = True
    strict_host_key_checking: bool = False
    known_hosts_file: str | None = None
    timeout_seconds: int = 30
    allow_writes: bool = False
    max_read_bytes: int = 1_048_576

    @classmethod
    def from_env(cls) -> "RemoteConfig":
        config = _load_config_file()
        remote = _config_section(config, "remote")
        mcp = _config_section(config, "mcp")

        protocol = _first_setting(
            ("DAYZ_REMOTE_PROTOCOL",), remote, ("protocol",), default=None
        )
        if protocol is None and os.getenv("DAYZ_FTP_HOST"):
            protocol = "ftps" if _parse_bool("DAYZ_FTP_TLS", True) else "ftp"
        protocol = (
            _parse_str_value(
                "DAYZ_REMOTE_PROTOCOL or [remote].protocol", protocol, "sftp"
            )
            or "sftp"
        ).strip().lower()
        if protocol not in _PROTOCOLS:
            allowed = ", ".join(sorted(_PROTOCOLS))
            raise ValueError(f"DAYZ_REMOTE_PROTOCOL must be one of: {allowed}")

        required = {
            "host": (("DAYZ_REMOTE_HOST", "DAYZ_FTP_HOST"), ("host",)),
            "user": (("DAYZ_REMOTE_USER", "DAYZ_FTP_USER"), ("user",)),
            "password": (("DAYZ_REMOTE_PASSWORD", "DAYZ_FTP_PASSWORD"), ("password",)),
        }
        missing = [
            f"{env_names[0]} or [remote].{config_keys[0]}"
            for env_names, config_keys in required.values()
            if not _first_setting(env_names, remote, config_keys)
        ]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required configuration value(s): {joined}")

        root = _first_setting(
            ("DAYZ_REMOTE_ROOT", "DAYZ_FTP_ROOT"), remote, ("root",), default="/"
        )
        root = _parse_str_value("DAYZ_REMOTE_ROOT or [remote].root", root, "/") or "/"
        root = root.strip() or "/"
        if not root.startswith("/"):
            root = f"/{root}"

        port_default = 22 if protocol == "sftp" else 21
        port = _parse_int_value(
            "DAYZ_REMOTE_PORT or [remote].port",
            _first_setting(
                ("DAYZ_REMOTE_PORT", "DAYZ_FTP_PORT"),
                remote,
                ("port",),
                default=port_default,
            ),
            port_default,
            minimum=1,
        )
        timeout = _parse_int_value(
            "DAYZ_REMOTE_TIMEOUT or [remote].timeout",
            _first_setting(
                ("DAYZ_REMOTE_TIMEOUT", "DAYZ_FTP_TIMEOUT"),
                remote,
                ("timeout", "timeout_seconds"),
                default=30,
            ),
            30,
            minimum=1,
        )

        return cls(
            host=_parse_str_value(
                "DAYZ_REMOTE_HOST or [remote].host",
                _first_setting(("DAYZ_REMOTE_HOST", "DAYZ_FTP_HOST"), remote, ("host",)),
            )
            or "",
            user=_parse_str_value(
                "DAYZ_REMOTE_USER or [remote].user",
                _first_setting(("DAYZ_REMOTE_USER", "DAYZ_FTP_USER"), remote, ("user",)),
            )
            or "",
            password=_parse_str_value(
                "DAYZ_REMOTE_PASSWORD or [remote].password",
                _first_setting(
                    ("DAYZ_REMOTE_PASSWORD", "DAYZ_FTP_PASSWORD"),
                    remote,
                    ("password",),
                ),
            )
            or "",
            protocol=protocol,
            root=root,
            port=port,
            passive=_parse_bool_value(
                "DAYZ_FTP_PASSIVE or [remote].passive",
                _first_setting(
                    ("DAYZ_FTP_PASSIVE",), remote, ("passive",), default=True
                ),
                True,
            ),
            strict_host_key_checking=_parse_bool_value(
                "DAYZ_SFTP_STRICT_HOST_KEY_CHECKING or [remote].strict_host_key_checking",
                _first_setting(
                    ("DAYZ_SFTP_STRICT_HOST_KEY_CHECKING",),
                    remote,
                    ("strict_host_key_checking",),
                    default=False,
                ),
                False,
            ),
            known_hosts_file=_parse_str_value(
                "DAYZ_SFTP_KNOWN_HOSTS or [remote].known_hosts_file",
                _first_setting(
                    ("DAYZ_SFTP_KNOWN_HOSTS",),
                    remote,
                    ("known_hosts_file", "known_hosts"),
                ),
            ),
            timeout_seconds=timeout,
            allow_writes=_parse_bool_value(
                "DAYZ_MCP_ALLOW_WRITES or [mcp].allow_writes",
                _first_setting(
                    ("DAYZ_MCP_ALLOW_WRITES",),
                    mcp,
                    ("allow_writes",),
                    default=False,
                ),
                False,
            ),
            max_read_bytes=_parse_int_value(
                "DAYZ_MCP_MAX_READ_BYTES or [mcp].max_read_bytes",
                _first_setting(
                    ("DAYZ_MCP_MAX_READ_BYTES",),
                    mcp,
                    ("max_read_bytes",),
                    default=1_048_576,
                ),
                1_048_576,
                minimum=1024,
            ),
        )

    def public_dict(self) -> dict[str, str | int | bool]:
        return {
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password_configured": bool(self.password),
            "root": self.root,
            "passive": self.passive,
            "strict_host_key_checking": self.strict_host_key_checking,
            "known_hosts_configured": bool(self.known_hosts_file),
            "timeout_seconds": self.timeout_seconds,
            "allow_writes": self.allow_writes,
            "max_read_bytes": self.max_read_bytes,
        }


FtpConfig = RemoteConfig
