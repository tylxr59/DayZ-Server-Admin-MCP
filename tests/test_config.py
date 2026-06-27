from dayz_server_admin_mcp.config import RemoteConfig


def clear_remote_env(monkeypatch, tmp_path) -> None:
    for name in (
        "DAYZ_MCP_CONFIG",
        "DAYZ_REMOTE_PROTOCOL",
        "DAYZ_REMOTE_HOST",
        "DAYZ_REMOTE_PORT",
        "DAYZ_REMOTE_USER",
        "DAYZ_REMOTE_PASSWORD",
        "DAYZ_REMOTE_ROOT",
        "DAYZ_REMOTE_TIMEOUT",
        "DAYZ_FTP_HOST",
        "DAYZ_FTP_PORT",
        "DAYZ_FTP_USER",
        "DAYZ_FTP_PASSWORD",
        "DAYZ_FTP_ROOT",
        "DAYZ_FTP_TLS",
        "DAYZ_FTP_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_remote_config_defaults_to_sftp(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_REMOTE_HOST", "example.com")
    monkeypatch.setenv("DAYZ_REMOTE_USER", "dayz-admin")
    monkeypatch.setenv("DAYZ_REMOTE_PASSWORD", "secret")

    config = RemoteConfig.from_env()

    assert config.protocol == "sftp"
    assert config.port == 22
    assert config.root == "/"


def test_remote_config_uses_explicit_sftp_port(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_REMOTE_PROTOCOL", "sftp")
    monkeypatch.setenv("DAYZ_REMOTE_HOST", "example.com")
    monkeypatch.setenv("DAYZ_REMOTE_PORT", "2022")
    monkeypatch.setenv("DAYZ_REMOTE_USER", "dayz-admin")
    monkeypatch.setenv("DAYZ_REMOTE_PASSWORD", "secret")

    config = RemoteConfig.from_env()

    assert config.port == 2022


def test_legacy_ftp_env_uses_ftps_by_default(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_FTP_HOST", "ftp.example.com")
    monkeypatch.setenv("DAYZ_FTP_USER", "dayz-admin")
    monkeypatch.setenv("DAYZ_FTP_PASSWORD", "secret")

    config = RemoteConfig.from_env()

    assert config.protocol == "ftps"
    assert config.port == 21


def test_remote_timeout_precedes_legacy_timeout(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_REMOTE_HOST", "example.com")
    monkeypatch.setenv("DAYZ_REMOTE_USER", "dayz-admin")
    monkeypatch.setenv("DAYZ_REMOTE_PASSWORD", "secret")
    monkeypatch.setenv("DAYZ_REMOTE_TIMEOUT", "12")
    monkeypatch.setenv("DAYZ_FTP_TIMEOUT", "99")

    config = RemoteConfig.from_env()

    assert config.timeout_seconds == 12


def test_remote_timeout_zero_is_invalid(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_REMOTE_HOST", "example.com")
    monkeypatch.setenv("DAYZ_REMOTE_USER", "dayz-admin")
    monkeypatch.setenv("DAYZ_REMOTE_PASSWORD", "secret")
    monkeypatch.setenv("DAYZ_REMOTE_TIMEOUT", "0")

    try:
        RemoteConfig.from_env()
    except ValueError as exc:
        assert "DAYZ_REMOTE_TIMEOUT" in str(exc)
    else:
        raise AssertionError("expected invalid timeout")


def test_config_file_values(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    config_path = tmp_path / "dayz-server-admin-mcp.toml"
    config_path.write_text(
        """
        [remote]
        protocol = "sftp"
        host = "example.com"
        port = 2022
        user = "dayz-admin"
        password = "secret"
        root = "/"
        timeout = 12
        strict_host_key_checking = true

        [mcp]
        allow_writes = true
        max_read_bytes = 2048
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("DAYZ_MCP_CONFIG", str(config_path))

    config = RemoteConfig.from_env()

    assert config.protocol == "sftp"
    assert config.host == "example.com"
    assert config.port == 2022
    assert config.user == "dayz-admin"
    assert config.password == "secret"
    assert config.timeout_seconds == 12
    assert config.strict_host_key_checking is True
    assert config.allow_writes is True
    assert config.max_read_bytes == 2048


def test_environment_overrides_config_file(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    config_path = tmp_path / "dayz-server-admin-mcp.toml"
    config_path.write_text(
        """
        [remote]
        host = "config.example.com"
        port = 22
        user = "from-config"
        password = "from-config"

        [mcp]
        allow_writes = false
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("DAYZ_MCP_CONFIG", str(config_path))
    monkeypatch.setenv("DAYZ_REMOTE_HOST", "env.example.com")
    monkeypatch.setenv("DAYZ_REMOTE_PORT", "2022")
    monkeypatch.setenv("DAYZ_MCP_ALLOW_WRITES", "true")

    config = RemoteConfig.from_env()

    assert config.host == "env.example.com"
    assert config.port == 2022
    assert config.user == "from-config"
    assert config.allow_writes is True


def test_explicit_missing_config_file_errors(monkeypatch, tmp_path) -> None:
    clear_remote_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DAYZ_MCP_CONFIG", str(tmp_path / "missing.toml"))

    try:
        RemoteConfig.from_env()
    except ValueError as exc:
        assert "Config file not found" in str(exc)
    else:
        raise AssertionError("expected missing config error")
