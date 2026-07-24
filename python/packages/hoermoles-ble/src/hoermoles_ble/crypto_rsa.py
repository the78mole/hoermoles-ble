"""
RSA part of the registration, deliberately kept separate from protocol.py:
this keeps protocol.py 100% free of third-party dependencies, while this
module encapsulates the one spot that needs a crypto library.

Corresponds to HAL.Android.RSA.RSAEngine.Encrypt(data, fOAEP: false), i.e.
RSAES-PKCS1-v1_5 (no OAEP!). For a port to C/C++, the equivalent mbedTLS
function would be `mbedtls_rsa_pkcs1_encrypt` with MBEDTLS_RSA_PKCS_V15.
"""

from __future__ import annotations

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key


def load_device_public_key(der_bytes: bytes) -> RSAPublicKey:
    return load_der_public_key(der_bytes, backend=default_backend())


def rsa_pkcs1v15_encrypt(pubkey: RSAPublicKey, data: bytes) -> bytes:
    return pubkey.encrypt(data, padding.PKCS1v15())
