import pytest

from dayz_server_admin_mcp.config import RemoteConfig
from dayz_server_admin_mcp.ftp_client import DayZFtpClient, WriteDisabledError


def make_client(root: str = "/server/dayz", allow_writes: bool = False) -> DayZFtpClient:
    return DayZFtpClient(
        RemoteConfig(
            host="example.com",
            user="user",
            password="password",
            root=root,
            allow_writes=allow_writes,
        )
    )


def test_resolve_path_stays_under_configured_root() -> None:
    client = make_client()

    assert client.resolve_path("serverDZ.cfg") == "/server/dayz/serverDZ.cfg"
    assert client.resolve_path("/mpmissions") == "/server/dayz/mpmissions"
    assert client.resolve_path(".") == "/server/dayz"


def test_resolve_path_rejects_parent_escape() -> None:
    client = make_client()

    with pytest.raises(ValueError):
        client.resolve_path("../../outside")


def test_resolve_path_allows_full_ftp_root_when_root_is_slash() -> None:
    client = make_client(root="/")

    assert client.resolve_path("serverDZ.cfg") == "/serverDZ.cfg"


def test_write_guard_defaults_to_disabled() -> None:
    client = make_client()

    with pytest.raises(WriteDisabledError):
        client.ensure_writes_allowed()


def test_write_guard_allows_explicit_opt_in() -> None:
    client = make_client(allow_writes=True)

    client.ensure_writes_allowed()
