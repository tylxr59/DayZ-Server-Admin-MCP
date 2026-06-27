from dayz_server_admin_mcp.dayz_config import parse_server_config, strip_line_comment


def test_strip_line_comment_preserves_url_like_text_inside_quotes() -> None:
    line = 'motd[] = {"https://example.com"}; // comment'

    assert strip_line_comment(line) == 'motd[] = {"https://example.com"}; '


def test_parse_server_config_extracts_common_assignments() -> None:
    text = """
    hostname = "Example DayZ";
    password = "";
    maxPlayers = 60;
    verifySignatures = 2;
    enableWhitelist = false;
    motd[] = {"Line one", "Line // two"};
    // ignored = true;
    class Missions
    {
        class DayZ
        {
            template = "dayzOffline.chernarusplus";
        };
    };
    """

    parsed = parse_server_config(text)

    assert parsed["hostname"] == "Example DayZ"
    assert parsed["password"] == ""
    assert parsed["maxPlayers"] == 60
    assert parsed["verifySignatures"] == 2
    assert parsed["enableWhitelist"] is False
    assert parsed["template"] == "dayzOffline.chernarusplus"
    assert "ignored" not in parsed


def test_parse_server_config_ignores_array_assignment_for_now() -> None:
    text = 'motd[] = {"Line one", "Line two"};'

    assert parse_server_config(text) == {}
