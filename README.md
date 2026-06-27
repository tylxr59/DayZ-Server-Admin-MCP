# DayZ Server Admin MCP

An MCP server for inspecting and managing DayZ server files over SFTP, FTP, or FTPS.

It exposes focused tools for browsing server files, reading configuration, listing installed mods and missions, and optionally writing files back to the server.

Write operations are disabled by default.

## Features

- Browse files under a configured server root.
- Read text files and binary files with size limits.
- List DayZ mod directories and mission folders.
- Read `serverDZ.cfg` with best-effort assignment parsing.
- Optionally write, upload, create directories, and rename paths.
- Support SFTP, FTP, and explicit FTPS.

## Installation

```bash
uv sync
```

## Configuration

Copy the example config and fill in your server details:

```bash
cp dayz-server-admin-mcp.example.toml dayz-server-admin-mcp.toml
```

The real config file is gitignored so credentials stay out of source control.

```toml
[remote]
protocol = "sftp"
host = "example.com"
port = 22
user = "dayz-admin"
password = "change-me"
root = "/path/to/dayz/server"
timeout = 30

[mcp]
allow_writes = false
max_read_bytes = 1048576
max_download_bytes = 52428800
```

By default, the server reads `./dayz-server-admin-mcp.toml`. To use a different path, set:

```bash
export DAYZ_MCP_CONFIG="/absolute/path/to/dayz-server-admin-mcp.toml"
```

Environment variables override config-file values:

| Config value | Environment variable |
| --- | --- |
| `remote.protocol` | `DAYZ_REMOTE_PROTOCOL` |
| `remote.host` | `DAYZ_REMOTE_HOST` |
| `remote.port` | `DAYZ_REMOTE_PORT` |
| `remote.user` | `DAYZ_REMOTE_USER` |
| `remote.password` | `DAYZ_REMOTE_PASSWORD` |
| `remote.root` | `DAYZ_REMOTE_ROOT` |
| `remote.timeout` | `DAYZ_REMOTE_TIMEOUT` |
| `remote.passive` | `DAYZ_FTP_PASSIVE` |
| `remote.strict_host_key_checking` | `DAYZ_SFTP_STRICT_HOST_KEY_CHECKING` |
| `remote.known_hosts_file` | `DAYZ_SFTP_KNOWN_HOSTS` |
| `mcp.allow_writes` | `DAYZ_MCP_ALLOW_WRITES` |
| `mcp.max_read_bytes` | `DAYZ_MCP_MAX_READ_BYTES` |
| `mcp.max_download_bytes` | `DAYZ_MCP_MAX_DOWNLOAD_BYTES` |
| `mcp.download_dir` | `DAYZ_MCP_DOWNLOAD_DIR` |

For FTP or FTPS servers, set `protocol = "ftp"` or `protocol = "ftps"`.

## Running

```bash
uv run dayz-server-admin-mcp
```

To inspect the MCP server during development:

```bash
uv run mcp dev src/dayz_server_admin_mcp/server.py
```

## MCP Client Example

For clients that launch stdio MCP servers, use:

```json
{
  "mcpServers": {
    "dayz-server-admin": {
      "command": "uv",
      "args": ["run", "dayz-server-admin-mcp"],
      "env": {
        "DAYZ_MCP_CONFIG": "/absolute/path/to/dayz-server-admin-mcp.toml"
      }
    }
  }
}
```

## Tools

- `remote_status`: Show the active remote configuration and test connectivity without revealing the password.
- `ftp_status`: Compatibility alias for `remote_status`.
- `list_remote_directory`: List files and directories under the configured remote root.
- `get_remote_file_info`: Show file metadata, including size when available.
- `read_text_file`: Read a text file with a byte limit.
- `read_text_file_chunk`: Read a large text file in byte chunks.
- `read_file_base64`: Read a binary file as base64 with a byte limit.
- `download_remote_file`: Download a remote file to a local temp/configured directory and return its path.
- `write_text_file`: Write a text file. Requires writes to be enabled.
- `upload_file_base64`: Upload binary content from base64. Requires writes to be enabled.
- `create_remote_directory`: Create a directory. Requires writes to be enabled.
- `rename_remote_path`: Rename or move a path. Requires writes to be enabled.
- `list_dayz_mods`: List DayZ mod folders that start with `@`.
- `list_dayz_missions`: List entries in the `mpmissions` directory.
- `read_dayz_server_config`: Read `serverDZ.cfg` and return best-effort parsed assignments.

## Write Safety

Write tools are blocked unless `mcp.allow_writes = true` or `DAYZ_MCP_ALLOW_WRITES=true`.

When write tools replace an existing file, they create a timestamped `.bak.YYYYMMDDHHMMSS` copy first by default.

## Large Files

Use `get_remote_file_info` before reading large files such as `types.xml`.

For files larger than `mcp.max_read_bytes`, use `read_text_file_chunk` and pass the returned `next_offset` into the next call until `eof` is true. This keeps credentials inside the MCP server and avoids oversized single responses.

`download_remote_file` can copy a remote file into a local download directory when another tool needs filesystem access. Downloads are limited by `mcp.max_download_bytes` and are written under `mcp.download_dir` or the system temp directory.

## Development

Run the test suite:

```bash
uv run pytest
```

## Security

Use a server-specific account scoped to the DayZ server directory when possible. The MCP server normalizes paths under the configured remote root, but server-side permissions should still be constrained by the hosting provider or operating system.
