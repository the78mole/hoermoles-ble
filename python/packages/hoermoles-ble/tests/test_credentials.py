import pytest

from hoermoles_ble.credentials import Credentials, default_credentials_path, list_saved_credential_paths


def test_default_credentials_path_normalizes_mac(tmp_path):
    path = default_credentials_path("f1:26:af:cc:41:86", config_dir=tmp_path)
    assert path == tmp_path / "credentials" / "F1-26-AF-CC-41-86.json"


def test_list_saved_credential_paths_empty_when_missing(tmp_path):
    assert list_saved_credential_paths(config_dir=tmp_path) == []


def test_save_and_load_roundtrip(tmp_path):
    creds = Credentials(
        device_address="F1:26:AF:CC:41:86",
        root_id=7,
        root_key=bytes(range(32)),
        qr_prefix="0302020000030262602641451030700",
    )
    path = creds.save(config_dir=tmp_path)

    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600

    loaded = Credentials.load(path)
    assert loaded.device_address == creds.device_address
    assert loaded.root_id == creds.root_id
    assert loaded.root_key == creds.root_key
    assert loaded.qr_prefix == creds.qr_prefix
    assert loaded.created_unix != 0  # save() stamps it with the current time, doesn't mutate `creds`


def test_save_uses_default_path_when_none_given(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=1, root_key=b"\x00" * 32)
    path = creds.save(config_dir=tmp_path)
    assert path == default_credentials_path("AA:BB:CC:DD:EE:FF", config_dir=tmp_path)


def test_load_for_device(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=2, root_key=b"\x01" * 32)
    creds.save(config_dir=tmp_path)

    loaded = Credentials.load_for_device("AA:BB:CC:DD:EE:FF", config_dir=tmp_path)
    assert loaded.root_id == 2


def test_load_first_raises_when_none_saved(tmp_path):
    with pytest.raises(FileNotFoundError):
        Credentials.load_first(config_dir=tmp_path)


def test_load_first_picks_lexicographically_first_mac(tmp_path):
    Credentials(device_address="FF:FF:FF:FF:FF:FF", root_id=1, root_key=b"\x00" * 32).save(config_dir=tmp_path)
    Credentials(device_address="AA:AA:AA:AA:AA:AA", root_id=2, root_key=b"\x00" * 32).save(config_dir=tmp_path)

    loaded = Credentials.load_first(config_dir=tmp_path)
    assert loaded.device_address == "AA:AA:AA:AA:AA:AA"


def test_save_defaults_qr_prefix_and_created_unix(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=1, root_key=b"\x00" * 32, created_unix=12345)
    path = creds.save(config_dir=tmp_path)
    loaded = Credentials.load(path)
    assert loaded.qr_prefix == ""
    assert loaded.created_unix == 12345
