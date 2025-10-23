import base64
import hashlib
import json
import os
import struct
from typing import Any

from Crypto.Cipher import ChaCha20_Poly1305

# ref: https://github.com/munew/wplace.live-pawtect-reverse/blob/d56700f/src/lib.rs
KEY = bytes([19, 55] * 16)
HOST = b"backend.wplace.live"
_PLAIN_HEAD = bytes([105, 19, 131, 172, 0])
_PLAIN_TAIL = bytes([0, 0]) + struct.pack("<I", 1) + struct.pack("<I", len(HOST)) + HOST


def pawtect_sign(payload: dict[str, Any]) -> str:
    body = json.dumps(payload).encode("utf-8")
    plaintext = b"".join([_PLAIN_HEAD, hashlib.sha256(body).digest(), _PLAIN_TAIL])
    cipher = ChaCha20_Poly1305.new(key=KEY, nonce=os.urandom(24))
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    encrypted = base64.b64encode(ciphertext + tag).decode()
    nonce = base64.b64encode(cipher.nonce).decode()
    return f"{encrypted}.{nonce}"
