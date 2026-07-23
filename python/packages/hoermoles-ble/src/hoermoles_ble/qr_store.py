"""
Storage for known QR code contents: as long as a proper app doesn't yet offer
a camera scan, QR code text (e.g. photographed and typed off, or read with a
separate scanner app) can be collected here. `register()` can then
automatically look up the matching QR code by BLE address (see
discovery.find_qr_for_address), instead of passing --qr-file every time.

Format: qr_codes.txt, one QR code content per line. When saving, entries are
deduplicated by the embedded serial number (protocol.serial_no_from_qr_prefix) -
saving the same device again replaces the existing line instead of duplicating
it. QR codes without a recognizable serial number are simply appended.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

from .config import resolve_config_dir
from .protocol import parse_qr_code, serial_no_from_qr_prefix


def default_qr_store_path(config_dir: Optional[Union[str, Path]] = None) -> Path:
    return resolve_config_dir(config_dir) / "qr_codes.txt"


def load_known_qrs(config_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """All saved QR code contents, one line per entry. Empty list if nothing
    has been saved yet."""
    target = default_qr_store_path(config_dir)
    if not target.exists():
        return []
    return [line.strip() for line in target.read_text().splitlines() if line.strip()]


def known_qr_serial_map(config_dir: Optional[Union[str, Path]] = None) -> Dict[int, str]:
    """Serial number -> QR code content, for all entries with a recognizable
    prefix format. Entries without a decodable serial number are skipped."""
    result: Dict[int, str] = {}
    for content in load_known_qrs(config_dir):
        try:
            prefix, _ = parse_qr_code(content)
        except Exception:
            continue
        serial_no = serial_no_from_qr_prefix(prefix)
        if serial_no is not None:
            result[serial_no] = content
    return result


def save_qr(content: str, config_dir: Optional[Union[str, Path]] = None) -> Path:
    """Validates the QR code content (raises on an invalid format) and appends
    it to the list of known QR codes. If a QR code with the same serial number
    is already saved, it is replaced instead of duplicated. Returns the path
    used."""
    content = content.strip()
    prefix, _ = parse_qr_code(content)  # raises on malformed content
    new_serial = serial_no_from_qr_prefix(prefix)

    entries = load_known_qrs(config_dir)
    if new_serial is not None:
        entries = [e for e in entries if serial_no_from_qr_prefix(parse_qr_code(e)[0]) != new_serial]
    entries.append(content)

    target = default_qr_store_path(config_dir)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_text("\n".join(entries) + "\n")
    target.chmod(0o600)
    return target
