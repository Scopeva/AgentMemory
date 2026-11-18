"""Configuration compatibility tests."""

from agent_memory.config import load_config


def test_legacy_mcp_agent_list_does_not_break_config_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY_SECURITY_ADMIN_TOKEN_ENV", raising=False)
    config_path = tmp_path / "agent-memory.toml"
    config_path.write_text(
        "[security]\nadmin_token_env = 'LEGACY_TEST_TOKEN'\nmcp_allowed_agents = ['pi']\n"
    )

    config = load_config(str(config_path))

    assert config.security.admin_token_env == "LEGACY_TEST_TOKEN"
