from types import SimpleNamespace

import pytest
from hoermoles_ble import devices, menu_settings
from hoermoles_ble.credentials import Credentials

from hoermoles_ble_cli.cli import _load_credentials, _menu_group_or_exit, _resolve_menu_table


def _args(**kwargs):
    defaults = {"key_file": None, "address": None, "config_dir": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# --- _load_credentials ---------------------------------------------------


def test_load_credentials_from_key_file(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=1, root_key=b"\x00" * 32)
    path = creds.save(config_dir=tmp_path)

    loaded = _load_credentials(_args(key_file=str(path)))
    assert loaded.device_address == "AA:BB:CC:DD:EE:FF"


def test_load_credentials_from_address(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=2, root_key=b"\x01" * 32)
    creds.save(config_dir=tmp_path)

    loaded = _load_credentials(_args(address="AA:BB:CC:DD:EE:FF", config_dir=tmp_path))
    assert loaded.root_id == 2


def test_load_credentials_falls_back_to_first(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=3, root_key=b"\x02" * 32)
    creds.save(config_dir=tmp_path)

    loaded = _load_credentials(_args(config_dir=tmp_path))
    assert loaded.root_id == 3


def test_load_credentials_exits_when_none_saved(tmp_path):
    with pytest.raises(SystemExit):
        _load_credentials(_args(config_dir=tmp_path))


# --- _menu_group_or_exit ---------------------------------------------------


def test_menu_group_or_exit_found():
    table = menu_settings.DRIVE_MENU_TABLES[0]
    setting = table.settings[0]
    assert _menu_group_or_exit(table, setting.menu_number) == setting.menu_group


def test_menu_group_or_exit_unknown_menu_number_exits():
    table = menu_settings.DRIVE_MENU_TABLES[0]
    with pytest.raises(SystemExit):
        _menu_group_or_exit(table, 999999)


# --- _resolve_menu_table ---------------------------------------------------


def test_resolve_menu_table_success(tmp_path):
    creds = Credentials(device_address="F1:26:AF:CC:41:86", root_id=1, root_key=b"\x00" * 32)
    devices.save_device_info(
        devices.DeviceInfo(device_address=creds.device_address, product_class=2, product_id=2),
        config_dir=tmp_path,
    )

    table = _resolve_menu_table(_args(config_dir=tmp_path), creds)
    assert table.settings == menu_settings.SUPRAMATIC_E4_MENU_TABLE


def test_resolve_menu_table_exits_when_device_unknown(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=1, root_key=b"\x00" * 32)
    with pytest.raises(SystemExit):
        _resolve_menu_table(_args(config_dir=tmp_path), creds)


def test_resolve_menu_table_exits_when_product_unknown(tmp_path):
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=1, root_key=b"\x00" * 32)
    devices.save_device_info(
        devices.DeviceInfo(device_address=creds.device_address, product_class=99, product_id=99),
        config_dir=tmp_path,
    )
    with pytest.raises(SystemExit):
        _resolve_menu_table(_args(config_dir=tmp_path), creds)
