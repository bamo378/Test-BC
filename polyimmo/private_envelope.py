"""Authenticated encrypted snapshots; compatible with the browser Web Crypto API."""
import base64,json,os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
FORMAT='polyimmo-private-v1'
def key(password,salt):
    if not isinstance(password,str) or len(password)<12:raise ValueError('A separate data password of at least 12 characters is required')
    return PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=250000).derive(password.encode())
def encrypt(value,password):
    salt=os.urandom(16);iv=os.urandom(12)
    data=AESGCM(key(password,salt)).encrypt(iv,json.dumps(value,ensure_ascii=False,separators=(',',':')).encode(),FORMAT.encode())
    return dict(format=FORMAT,iterations=250000,salt=base64.b64encode(salt).decode(),iv=base64.b64encode(iv).decode(),data=base64.b64encode(data).decode())
def decrypt(envelope,password):
    if envelope.get('format')!=FORMAT or envelope.get('iterations')!=250000:raise ValueError('Unknown encrypted snapshot')
    salt,iv,data=[base64.b64decode(envelope[k],validate=True) for k in ('salt','iv','data')]
    if len(salt)!=16 or len(iv)!=12:raise ValueError('Invalid encrypted snapshot')
    return json.loads(AESGCM(key(password,salt)).decrypt(iv,data,FORMAT.encode()))
