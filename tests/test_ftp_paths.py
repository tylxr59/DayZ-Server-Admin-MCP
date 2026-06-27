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


def test_read_text_chunk_uses_next_offset_and_eof(monkeypatch) -> None:
    client = make_client(root="/", allow_writes=False)

    def fake_read_range(path: str, offset: int, length: int) -> tuple[bytes, int]:
        assert path == "types.xml"
        assert offset == 5
        assert length == 7
        return b"example", 12

    monkeypatch.setattr(client, "_read_sftp_range", fake_read_range)

    result = client.read_text_chunk("types.xml", offset=5, length=7)

    assert result["content"] == "example"
    assert result["offset"] == 5
    assert result["next_offset"] == 12
    assert result["bytes_read"] == 7
    assert result["file_size"] == 12
    assert result["eof"] is True


def test_read_text_chunk_rejects_lengths_above_configured_limit() -> None:
    client = make_client()

    with pytest.raises(ValueError):
        client.read_text_chunk("types.xml", length=client.config.max_read_bytes + 1)
