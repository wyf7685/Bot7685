import base64
import hashlib
import json
import os
import struct
from typing import Any

from Crypto.Cipher import ChaCha20_Poly1305

# ref: https://github.com/munew/wplace.live-pawtect-reverse/blob/d56700f/src/lib.rs
KEY = bytes([19, 55] * 16)
HOSTS = ["backend.wplace.live"]
_HEAD = bytes([105, 19, 131, 172, 0])


def _build_plaintext(body: bytes) -> bytearray:
    plaintext = bytearray()
    plaintext.extend(_HEAD)
    plaintext.extend(hashlib.sha256(body).digest())
    plaintext.extend([0, 0])
    plaintext.extend(struct.pack("<I", len(HOSTS)))
    for host in HOSTS:
        encoded_host = host.encode("ascii")
        plaintext.extend(struct.pack("<I", len(encoded_host)))
        plaintext.extend(encoded_host)
    return plaintext


def pawtect_sign(payload: dict[str, Any]) -> str:
    body = json.dumps(payload).encode("ascii")
    plaintext = _build_plaintext(body)
    cipher = ChaCha20_Poly1305.new(key=KEY, nonce=os.urandom(24))
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    encrypted = base64.b64encode(ciphertext + tag).decode()
    nonce = base64.b64encode(cipher.nonce).decode()
    return f"{encrypted}.{nonce}"
