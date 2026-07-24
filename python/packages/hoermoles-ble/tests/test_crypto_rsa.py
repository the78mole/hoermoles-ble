from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from hoermoles_ble.crypto_rsa import load_device_public_key, rsa_pkcs1v15_encrypt


def test_load_device_public_key_and_encrypt_roundtrip():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der_bytes = private_key.public_key().public_bytes(encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo)

    pubkey = load_device_public_key(der_bytes)
    plaintext = b"root-key-bytes-32-long-padding!!"
    ciphertext = rsa_pkcs1v15_encrypt(pubkey, plaintext)

    assert ciphertext != plaintext
    decrypted = private_key.decrypt(ciphertext, padding.PKCS1v15())
    assert decrypted == plaintext
