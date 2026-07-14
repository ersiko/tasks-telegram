from cryptography.fernet import Fernet


class TokenCipher:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())

    def encrypt(self, token: str) -> bytes:
        return self._fernet.encrypt(token.encode())

    def decrypt(self, blob: bytes) -> str:
        return self._fernet.decrypt(blob).decode()
