import json

import pytest
from hoermoles_ble.bundle import (
    PREFIX_ENCRYPTED,
    PREFIX_PLAIN,
    BundleEntry,
    BundleError,
    bundle_from_json,
    bundle_to_json,
    decode_bundle,
    encode_bundle,
    is_encrypted_bundle,
)
from hoermoles_ble.credentials import Credentials
from hoermoles_ble.devices import DeviceInfo

ROOT_KEY = bytes(range(32))

# version "03" + class "02" + id "02" + 3 filler + 20-digit zero-padded serial + 2 trailing
# = the 31-digit layout protocol.serial_no_from_qr_prefix expects.
QR_PREFIX = "03" + "02" + "02" + "000" + "00302626026414510307" + "99"


def make_entry(with_device_info: bool = True, label: str | None = None) -> BundleEntry:
    credentials = Credentials(
        device_address="F1:26:AF:CC:41:86",
        root_id=1,
        root_key=ROOT_KEY,
        qr_prefix=QR_PREFIX,
        created_unix=1784850177,
    )
    device_info = (
        DeviceInfo(
            device_address="F1:26:AF:CC:41:86",
            product_class=2,
            product_id=2,
            product_name="Supramatic Serie 4",
            serial_no=302626026414510307,
            label=label,
        )
        if with_device_info
        else None
    )
    return BundleEntry(credentials=credentials, device_info=device_info)


def test_plain_text_form_round_trips():
    entry = make_entry()
    text = encode_bundle([entry])

    assert text.startswith(PREFIX_PLAIN)
    assert not is_encrypted_bundle(text)

    [restored] = decode_bundle(text)
    assert restored.credentials.root_key == ROOT_KEY
    assert restored.credentials.root_id == 1
    assert restored.credentials.device_address == "F1:26:AF:CC:41:86"
    assert restored.device_info is not None
    assert restored.device_info.product_name == "Supramatic Serie 4"
    assert restored.device_info.serial_no == 302626026414510307


def test_encrypted_form_round_trips_and_needs_the_passphrase():
    text = encode_bundle([make_entry()], passphrase="correct horse")

    assert text.startswith(PREFIX_ENCRYPTED)
    assert is_encrypted_bundle(text)

    [restored] = decode_bundle(text, passphrase="correct horse")
    assert restored.credentials.root_key == ROOT_KEY

    with pytest.raises(BundleError, match="passphrase is required"):
        decode_bundle(text)
    with pytest.raises(BundleError, match="wrong passphrase"):
        decode_bundle(text, passphrase="wrong")


def test_encryption_is_randomized():
    """Same input twice must not produce the same ciphertext - otherwise a
    reused salt/nonce would leak that two exports carry identical content."""
    entries = [make_entry()]
    assert encode_bundle(entries, passphrase="pw") != encode_bundle(entries, passphrase="pw")


def test_text_form_is_url_fragment_safe():
    """base64url without padding - the text form travels in '#import=...'."""
    text = encode_bundle([make_entry()])
    payload = text[len(PREFIX_PLAIN) :]
    assert "+" not in payload
    assert "/" not in payload
    assert "=" not in payload


def test_decode_accepts_a_full_import_url():
    text = encode_bundle([make_entry()])
    url = f"https://the78mole.github.io/hoermoles-ble/#import={text}"
    [restored] = decode_bundle(url)
    assert restored.credentials.root_key == ROOT_KEY


def test_label_round_trips_when_set():
    [restored] = decode_bundle(encode_bundle([make_entry(label="Garage")]))
    assert restored.device_info is not None
    assert restored.device_info.label == "Garage"


def test_label_absent_when_not_set():
    """An unnamed drive must not carry an empty 'label' key - keeps bundles clean
    and matches the TypeScript side, which only emits a label when there is one."""
    payload = json.loads(bundle_to_json([make_entry()]))
    assert "label" not in payload["devices"][0]

    [restored] = decode_bundle(encode_bundle([make_entry()]))
    assert restored.device_info is not None
    assert restored.device_info.label is None


def test_serial_number_is_carried_as_a_string():
    """Hoermann serials are uint64 and exceed JavaScript's
    Number.MAX_SAFE_INTEGER (2**53-1). As a JSON *number* the web app would
    silently receive a rounded value, so the wire format uses a string - this
    test exists to stop anyone "tidying" it back into an int."""
    payload = json.loads(bundle_to_json([make_entry()]))
    serial_field = payload["devices"][0]["serial_no"]

    assert isinstance(serial_field, str)
    assert serial_field == "302626026414510307"
    assert int(serial_field) > 2**53 - 1

    [restored] = decode_bundle(bundle_to_json([make_entry()]))
    assert restored.device_info.serial_no == 302626026414510307


def test_legacy_numeric_serial_still_imports():
    """Bundles written before the string change must keep working."""
    payload = json.loads(bundle_to_json([make_entry()]))
    payload["devices"][0]["serial_no"] = 302626026414510307
    [restored] = decode_bundle(json.dumps(payload))
    assert restored.device_info.serial_no == 302626026414510307


def test_json_file_form_round_trips():
    entry = make_entry()
    [restored] = bundle_from_json(bundle_to_json([entry]))
    assert restored.credentials.root_key == ROOT_KEY
    assert restored.device_info is not None


def test_decode_accepts_raw_json_without_a_prefix():
    """The file form and the text form go through the same entry point, so a
    pasted JSON file works wherever a bundle string is accepted."""
    [restored] = decode_bundle(bundle_to_json([make_entry()]))
    assert restored.credentials.root_id == 1


def test_entry_without_device_info_round_trips():
    [restored] = decode_bundle(encode_bundle([make_entry(with_device_info=False)]))
    assert restored.device_info is None
    assert restored.credentials.root_key == ROOT_KEY


def test_multiple_devices_in_one_bundle():
    first = make_entry()
    second = make_entry()
    second.credentials.device_address = "AA:BB:CC:DD:EE:FF"
    second.credentials.root_id = 7

    restored = decode_bundle(encode_bundle([first, second]))
    assert [e.credentials.device_address for e in restored] == ["F1:26:AF:CC:41:86", "AA:BB:CC:DD:EE:FF"]
    assert [e.credentials.root_id for e in restored] == [1, 7]


@pytest.mark.parametrize(
    "text, message",
    [
        ("not a bundle at all", "Unrecognized bundle format"),
        (PREFIX_PLAIN + "!!!not base64!!!", "base64url"),
        ('{"format": "something-else", "v": 1, "devices": []}', "Not a hoermoles credential bundle"),
        ('{"format": "hoermoles-credentials", "v": 99, "devices": []}', "Unsupported bundle version"),
        ('{"format": "hoermoles-credentials", "v": 1}', "missing a 'devices' list"),
        ('{"format": "hoermoles-credentials", "v": 1, "devices": [{"root_id": 1}]}', "Malformed bundle entry"),
        (PREFIX_ENCRYPTED + "AAAA", "passphrase is required"),
    ],
)
def test_rejects_malformed_input(text, message):
    with pytest.raises(BundleError, match=message):
        decode_bundle(text)


def test_rejects_truncated_encrypted_envelope():
    with pytest.raises(BundleError, match="Malformed encrypted bundle envelope"):
        decode_bundle(PREFIX_ENCRYPTED + "SE0xRQ", passphrase="pw")


def test_bundle_from_json_rejects_non_json():
    with pytest.raises(BundleError, match="Not valid JSON"):
        bundle_from_json("<html>nope</html>")
