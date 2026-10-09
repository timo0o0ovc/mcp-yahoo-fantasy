import stat

from yahoo import auth


def test_write_env_is_private_and_creates_parent(tmp_path, monkeypatch):
    path = tmp_path / "nested" / ".env"
    path.parent.mkdir()
    path.write_text("OLD=1\n")
    path.chmod(0o644)
    monkeypatch.setattr(auth, "ENV_FILE", path)
    auth.write_env({"YAHOO_CONSUMER_KEY": "k"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert auth._parse_env(path.read_text()) == {"OLD": "1", "YAHOO_CONSUMER_KEY": "k"}


def test_bridged_oauth_file_is_private(tmp_path, monkeypatch):
    oauth = tmp_path / "cfg" / "oauth2.json"
    monkeypatch.setattr(auth, "OAUTH_FILE", oauth)
    monkeypatch.setenv("YAHOO_CONSUMER_KEY", "k")
    monkeypatch.setenv("YAHOO_CONSUMER_SECRET", "s")
    assert auth._bridge_env_to_oauth_file()
    assert stat.S_IMODE(oauth.stat().st_mode) == 0o600
