from pathlib import Path

import hoermoles_ble.config as config


def test_resolve_config_dir_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR_CONFIG_DIR, str(tmp_path / "env-dir"))
    override_dir = tmp_path / "override-dir"
    assert config.resolve_config_dir(override_dir) == override_dir.expanduser().resolve()


def test_resolve_config_dir_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv(config.ENV_VAR_CONFIG_DIR, raising=False)
    monkeypatch.setenv(config.ENV_VAR_CONFIG_DIR, str(tmp_path / "env-dir"))
    monkeypatch.chdir(tmp_path)
    assert config.resolve_config_dir() == (tmp_path / "env-dir").expanduser().resolve()


def test_resolve_config_dir_default(monkeypatch):
    # load_dotenv() (no usecwd=True) searches upward from config.py's own file
    # location, not the process cwd - so it would find this dev repo's real
    # .env (which sets HOERMOLES_CONF_DIR) regardless of chdir. Stub it out to
    # exercise the true "nothing configured at all" default path.
    monkeypatch.delenv(config.ENV_VAR_CONFIG_DIR, raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    assert config.resolve_config_dir() == Path.home() / ".hoermoles"


def test_resolve_config_dir_expands_user(monkeypatch):
    monkeypatch.delenv(config.ENV_VAR_CONFIG_DIR, raising=False)
    assert config.resolve_config_dir("~/some-dir") == (Path.home() / "some-dir").resolve()
