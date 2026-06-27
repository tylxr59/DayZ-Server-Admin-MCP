from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import RemoteConfig
from .dayz_config import parse_server_config
from .remote_client import DayZRemoteClient

mcp = FastMCP("DayZ Server Admin")


def _client() -> DayZRemoteClient:
    return DayZRemoteClient(RemoteConfig.from_env())


@mcp.tool()
def remote_status() -> dict[str, Any]:
    """Show remote connection configuration and verify the configured server root."""

    client = _client()
    status = client.config.public_dict()
    status.update(client.test_connection())
    return status


@mcp.tool()
def ftp_status() -> dict[str, Any]:
    """Compatibility alias for remote_status."""

    return remote_status()


@mcp.tool()
def list_remote_directory(path: str = ".") -> list[dict[str, Any]]:
    """List files and directories under the configured remote root."""

    return _client().list_directory(path)


@mcp.tool()
def get_remote_file_info(path: str) -> dict[str, Any]:
    """Show remote file metadata, including size when available."""

    return _client().file_info(path)


@mcp.tool()
def read_text_file(
    path: str,
    encoding: str = "utf-8",
    max_bytes: int | None = None,
) -> str:
    """Read a text file from the configured remote root."""

    return _client().read_text(path, encoding=encoding, max_bytes=max_bytes)


@mcp.tool()
def read_text_file_chunk(
    path: str,
    offset: int = 0,
    length: int | None = None,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """Read part of a large text file by byte offset.

    Use this for large files such as types.xml. The returned next_offset can be
    passed into the next call until eof is true.
    """

    return _client().read_text_chunk(
        path,
        offset=offset,
        length=length,
        encoding=encoding,
    )


@mcp.tool()
def read_file_base64(path: str, max_bytes: int | None = None) -> dict[str, Any]:
    """Read a binary file as base64 from the configured remote root."""

    return _client().read_base64(path, max_bytes=max_bytes)


@mcp.tool()
def download_remote_file(path: str) -> dict[str, Any]:
    """Download a remote file to a local temp/configured directory and return its path."""

    return _client().download_file(path)


@mcp.tool()
def write_text_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    create_backup: bool = True,
) -> dict[str, Any]:
    """Write a text file. Requires DAYZ_MCP_ALLOW_WRITES=true."""

    return _client().write_text(
        path,
        content,
        encoding=encoding,
        create_backup=create_backup,
    )


@mcp.tool()
def upload_file_base64(
    path: str,
    content_base64: str,
    create_backup: bool = True,
) -> dict[str, Any]:
    """Upload binary content from base64. Requires DAYZ_MCP_ALLOW_WRITES=true."""

    return _client().upload_base64(
        path,
        content_base64,
        create_backup=create_backup,
    )


@mcp.tool()
def create_remote_directory(path: str) -> dict[str, Any]:
    """Create a directory under the configured remote root. Requires DAYZ_MCP_ALLOW_WRITES=true."""

    return _client().make_directory(path)


@mcp.tool()
def rename_remote_path(source: str, destination: str) -> dict[str, Any]:
    """Rename or move a path under the configured remote root. Requires DAYZ_MCP_ALLOW_WRITES=true."""

    return _client().rename(source, destination)


@mcp.tool()
def list_dayz_mods() -> list[dict[str, Any]]:
    """List DayZ mod directories at the server root. Mod folders usually start with @."""

    entries = _client().list_directory(".")
    return [
        entry
        for entry in entries
        if entry.get("type") == "dir" and str(entry.get("name", "")).startswith("@")
    ]


@mcp.tool()
def list_dayz_missions() -> list[dict[str, Any]]:
    """List installed mission files and folders under mpmissions."""

    return _client().list_directory("mpmissions")


@mcp.tool()
def read_dayz_server_config(path: str = "serverDZ.cfg") -> dict[str, Any]:
    """Read serverDZ.cfg and return raw text plus best-effort parsed assignments."""

    text = _client().read_text(path)
    return {
        "path": path,
        "raw": text,
        "parsed_assignments": parse_server_config(text),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
