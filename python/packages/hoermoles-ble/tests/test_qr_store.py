import base64
import binascii

import pytest
from hoermoles_ble.qr_store import default_qr_store_path, known_qr_serial_map, load_known_qrs, save_qr

# 31-digit prefix format verified against real hardware in test_protocol.py:
# 9-char header (2 version + 7 unclear) + 20-digit serial (prefix[9:29]) + 2 trailing digits.
_PREFIX_A = "030202000" + "0" * 19 + "1" + "00"
_PREFIX_B = "030202000" + "0" * 19 + "2" + "00"


def _qr(prefix: str, der: bytes = b"der-bytes") -> str:
    return prefix + base64.b64encode(der).decode()


def test_default_qr_store_path(tmp_path):
    assert default_qr_store_path(config_dir=tmp_path) == tmp_path / "qr_codes.txt"


def test_load_known_qrs_empty_when_missing(tmp_path):
    assert load_known_qrs(config_dir=tmp_path) == []


def test_save_qr_rejects_malformed_content(tmp_path):
    # save_qr validates via parse_qr_code, whose base64 decode raises
    # binascii.Error. Asserting the concrete type rather than bare Exception
    # keeps the test from passing for the wrong reason (a typo'd import, say).
    with pytest.raises(binascii.Error):
        save_qr("not valid base64 or digits!!!", config_dir=tmp_path)


def test_save_and_load_qr_roundtrip(tmp_path):
    content = _qr(_PREFIX_A)
    path = save_qr(content, config_dir=tmp_path)

    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert load_known_qrs(config_dir=tmp_path) == [content]


def test_save_qr_appends_distinct_serials(tmp_path):
    save_qr(_qr(_PREFIX_A), config_dir=tmp_path)
    save_qr(_qr(_PREFIX_B), config_dir=tmp_path)
    assert len(load_known_qrs(config_dir=tmp_path)) == 2


def test_save_qr_replaces_same_serial(tmp_path):
    save_qr(_qr(_PREFIX_A, der=b"old"), config_dir=tmp_path)
    new_content = _qr(_PREFIX_A, der=b"new")
    save_qr(new_content, config_dir=tmp_path)

    entries = load_known_qrs(config_dir=tmp_path)
    assert entries == [new_content]


def test_known_qr_serial_map(tmp_path):
    save_qr(_qr(_PREFIX_A), config_dir=tmp_path)
    save_qr(_qr(_PREFIX_B), config_dir=tmp_path)

    serial_map = known_qr_serial_map(config_dir=tmp_path)
    assert set(serial_map) == {1, 2}
    assert serial_map[1] == _qr(_PREFIX_A)


def test_known_qr_serial_map_skips_unparseable_lines(tmp_path):
    store_path = default_qr_store_path(config_dir=tmp_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("not-a-valid-qr-line\n" + _qr(_PREFIX_A) + "\n")

    serial_map = known_qr_serial_map(config_dir=tmp_path)
    assert serial_map == {1: _qr(_PREFIX_A)}
