"""
Persisted credentials for a taught drive: exactly the three values an
independent client (Home Assistant integration, fingerprint-reader bridge,
custom script...) needs to trigger channels - no app, no cloud, no QR code
needed anymore once this file exists once.

Default location: <config_dir>/credentials/<mac-address>.json - config_dir is
resolved via config.resolve_config_dir() (default ~/.hoermoles). Created with
restrictive permissions (0700/0600) as needed, since root_key_hex is a
plaintext secret.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .config import resolve_config_dir


def default_credentials_path(device_address: str, config_dir: Optional[Union[str, Path]] = None) -> Path:
    safe_address = device_address.replace(":", "-").upper()
    return resolve_config_dir(config_dir) / "credentials" / f"{safe_address}.json"


@dataclass
class Credentials:
    device_address: str
    root_id: int
    root_key: bytes
    qr_prefix: str = ""
    created_unix: int = 0

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Credentials":
        data = json.loads(Path(path).read_text())
        return cls(
            device_address=data["device_address"],
            root_id=data["root_id"],
            root_key=bytes.fromhex(data["root_key_hex"]),
            qr_prefix=data.get("qr_prefix", ""),
            created_unix=data.get("created_unix", 0),
        )

    @classmethod
    def load_for_device(cls, device_address: str, config_dir: Optional[Union[str, Path]] = None) -> "Credentials":
        """Loads from the default path (resolved via config_dir/ENV/.env/default)."""
        return cls.load(default_credentials_path(device_address, config_dir))

    def save(self, path: Optional[Union[str, Path]] = None,
             config_dir: Optional[Union[str, Path]] = None) -> Path:
        """Writes the credentials file. Without `path`, the default path under
        the resolved config_dir is used (see config.py). Returns the path
        actually used."""
        target = Path(path) if path is not None else default_credentials_path(self.device_address, config_dir)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        payload = {
            "device_address": self.device_address,
            "root_id": self.root_id,
            "root_key_hex": self.root_key.hex(),
            "qr_prefix": self.qr_prefix,
            "created_unix": self.created_unix or int(time.time()),
        }
        target.write_text(json.dumps(payload, indent=2))
        target.chmod(0o600)
        return target
