"""Configuration compatibility tests."""

from agent_memory.config import load_config


def test_legacy_mcp_agent_list_does_not_break_config_loading(tmp_path, monkeypatch):
    config_path = tmp_path / "agent-memory.toml"
    config_path.write_text(
        "[security]\nadmin_token_env = 'LEGACY_TEST_TOKEN'\nmcp_allowed_agents = ['pi']\n"
    )

    config = load_config(str(config_path))

    assert config.security.admin_token_env == "LEGACY_TEST_TOKEN"


def test_toml_settings_ignore_legacy_environment_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[database]\npath = '/configured.db'\n"
        "[embedding]\nendpoint = 'http://configured.example:8001'\nenabled = false\n"
        "[retrieval]\nsqlite_vec_path = '/configured/vec0.so'\n"
        "[workers]\ninterval_seconds = 7\n"
    )
    monkeypatch.setenv("AGENT_MEMORY_DATABASE_PATH", "/ignored.db")
    monkeypatch.setenv("AGENT_MEMORY_EMBEDDING_ENDPOINT", "http://ignored.example:8001")
    monkeypatch.setenv("AGENT_MEMORY_WORKERS_INTERVAL_SECONDS", "99")
    monkeypatch.setenv("SQLITE_VEC_PATH", "/ignored/vec0.so")

    config = load_config(str(config_path))

    assert config.database.path == "/configured.db"
    assert config.embedding.endpoint == "http://configured.example:8001"
    assert config.embedding.enabled is False
    assert config.retrieval.sqlite_vec_path == "/configured/vec0.so"
    assert config.workers.interval_seconds == 7
