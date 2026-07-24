import asyncio
from types import SimpleNamespace

import pytest
from hoermoles_ble import devices, menu_settings
from hoermoles_ble.bundle import encode_bundle
from hoermoles_ble.credentials import Credentials
from hoermoles_ble_cli.cli import (
    _collect_bundle_entries,
    _load_credentials,
    _menu_group_or_exit,
    _read_bundle_source,
    _resolve_menu_table,
    cmd_export,
    cmd_import,
)


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


# --- export / import -------------------------------------------------------


def _seed_drive(tmp_path, address="F1:26:AF:CC:41:86", root_id=1, with_device_info=True):
    Credentials(device_address=address, root_id=root_id, root_key=bytes(range(32))).save(config_dir=tmp_path)
    if with_device_info:
        devices.save_device_info(
            devices.DeviceInfo(
                device_address=address,
                product_class=2,
                product_id=2,
                product_name="Supramatic Serie 4",
                serial_no=302626026414510307,
            ),
            config_dir=tmp_path,
        )


def _export_args(tmp_path, **kwargs):
    defaults = {"address": None, "config_dir": tmp_path, "encrypt": False, "out": None, "stdout": True}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _bundle_line(capsys, prefix):
    return next(line for line in capsys.readouterr().out.splitlines() if line.startswith(prefix))


def test_collect_bundle_entries_attaches_device_info(tmp_path):
    _seed_drive(tmp_path)
    [entry] = _collect_bundle_entries(_export_args(tmp_path))
    assert entry.credentials.root_id == 1
    assert entry.device_info is not None
    assert entry.device_info.product_name == "Supramatic Serie 4"


def test_collect_bundle_entries_without_device_info(tmp_path):
    _seed_drive(tmp_path, with_device_info=False)
    [entry] = _collect_bundle_entries(_export_args(tmp_path))
    assert entry.device_info is None


def test_collect_bundle_entries_exits_when_nothing_saved(tmp_path):
    with pytest.raises(SystemExit, match="No saved credentials"):
        _collect_bundle_entries(_export_args(tmp_path))


def test_collect_bundle_entries_exits_for_unknown_address(tmp_path):
    _seed_drive(tmp_path)
    with pytest.raises(SystemExit, match="No saved credentials for"):
        _collect_bundle_entries(_export_args(tmp_path, address="AA:BB:CC:DD:EE:FF"))


def test_export_import_round_trip_via_text(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _seed_drive(source)

    asyncio.run(cmd_export(_export_args(source)))
    bundle_text = _bundle_line(capsys, "HMOLES1:")

    asyncio.run(cmd_import(SimpleNamespace(source=bundle_text, config_dir=target, force=False)))

    restored = Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target)
    assert restored.root_key == bytes(range(32))
    assert restored.root_id == 1
    assert devices.get_device_info("F1:26:AF:CC:41:86", config_dir=target).product_id == 2


def test_export_stdout_carries_nothing_but_the_bundle(tmp_path, capsys):
    """`--stdout` exists to be copied or piped, so stdout must hold the bundle
    and nothing else. Progress lines and the plaintext warning belong on
    stderr - when they shared stdout, the output could not be piped into
    `import -` without filtering."""
    _seed_drive(tmp_path)
    asyncio.run(cmd_export(_export_args(tmp_path)))
    captured = capsys.readouterr()

    assert captured.out.strip().startswith("HMOLES1:")
    assert len(captured.out.strip().splitlines()) == 1

    # The warning must still be emitted - just not into the copyable stream.
    assert "UNENCRYPTED" in captured.err


def test_export_stdout_piped_into_import(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _seed_drive(source)

    asyncio.run(cmd_export(_export_args(source)))
    piped = capsys.readouterr().out  # exactly what a shell pipe would carry

    asyncio.run(cmd_import(SimpleNamespace(source=piped, config_dir=target, force=False)))
    assert Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target).root_id == 1


def test_export_import_round_trip_via_json_file(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    bundle_file = tmp_path / "bundle.json"
    _seed_drive(source)

    asyncio.run(cmd_export(_export_args(source, stdout=False, out=str(bundle_file))))
    assert bundle_file.exists()

    asyncio.run(cmd_import(SimpleNamespace(source=str(bundle_file), config_dir=target, force=False)))
    assert Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target).root_id == 1


def test_export_encrypted_round_trip(tmp_path, capsys, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _seed_drive(source)

    monkeypatch.setattr("getpass.getpass", lambda *_: "s3cret")
    asyncio.run(cmd_export(_export_args(source, encrypt=True)))
    bundle_text = _bundle_line(capsys, "HMOLES1E:")

    asyncio.run(cmd_import(SimpleNamespace(source=bundle_text, config_dir=target, force=False)))
    assert Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target).root_id == 1


def test_export_rejects_encrypt_with_out(tmp_path, monkeypatch):
    _seed_drive(tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda *_: "s3cret")
    with pytest.raises(SystemExit, match="text/QR form only"):
        asyncio.run(cmd_export(_export_args(tmp_path, encrypt=True, stdout=False, out=str(tmp_path / "b.json"))))


def test_import_skips_existing_credentials_without_force(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _seed_drive(source)
    _seed_drive(target, root_id=99, with_device_info=False)

    asyncio.run(cmd_export(_export_args(source)))
    bundle_text = _bundle_line(capsys, "HMOLES1:")

    asyncio.run(cmd_import(SimpleNamespace(source=bundle_text, config_dir=target, force=False)))
    assert Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target).root_id == 99

    asyncio.run(cmd_import(SimpleNamespace(source=bundle_text, config_dir=target, force=True)))
    assert Credentials.load_for_device("F1:26:AF:CC:41:86", config_dir=target).root_id == 1


def test_import_rejects_garbage(tmp_path):
    with pytest.raises(SystemExit, match="Unrecognized bundle format"):
        asyncio.run(cmd_import(SimpleNamespace(source="not a bundle", config_dir=tmp_path, force=False)))


def test_read_bundle_source_handles_text_longer_than_a_filename(tmp_path):
    """A bundle string exceeds every filesystem's filename limit, and on Python
    <= 3.11 Path.exists() raises OSError(ENAMETOOLONG) rather than returning
    False. Probing the path before recognising the text form therefore crashed
    `hoermoles-ble import "<code>"` on 3.10/3.11 while passing on 3.12+."""
    _seed_drive(tmp_path)
    [entry] = _collect_bundle_entries(_export_args(tmp_path))
    long_text = encode_bundle([entry])

    assert len(long_text) > 255  # i.e. longer than NAME_MAX
    assert _read_bundle_source(long_text) == long_text


def test_read_bundle_source_reads_a_file(tmp_path):
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text('{"format": "hoermoles-credentials", "v": 1, "devices": []}')
    assert _read_bundle_source(str(bundle_file)).startswith("{")


def test_read_bundle_source_passes_through_an_import_url(tmp_path):
    _seed_drive(tmp_path)
    [entry] = _collect_bundle_entries(_export_args(tmp_path))
    url = f"https://the78mole.github.io/hoermoles-ble/#import={encode_bundle([entry])}"
    assert _read_bundle_source(url) == url


def test_export_empty_passphrase_aborts(tmp_path, monkeypatch):
    _seed_drive(tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda *_: "")
    with pytest.raises(SystemExit, match="Empty passphrase"):
        asyncio.run(cmd_export(_export_args(tmp_path, encrypt=True)))


def test_export_mismatched_passphrase_aborts(tmp_path, monkeypatch):
    _seed_drive(tmp_path)
    answers = iter(["one", "two"])
    monkeypatch.setattr("getpass.getpass", lambda *_: next(answers))
    with pytest.raises(SystemExit, match="do not match"):
        asyncio.run(cmd_export(_export_args(tmp_path, encrypt=True)))
