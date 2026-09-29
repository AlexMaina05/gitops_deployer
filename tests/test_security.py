import pytest
import hmac
import hashlib
from src.security import verify_github_signature

# Chiave segreta finta per i test
TEST_SECRET = "my_super_secret_key"
# Payload finto di esempio
TEST_PAYLOAD = b'{"action": "push", "repository": {"name": "homelab"}}'

def generate_signature(secret: str, payload: bytes) -> str:
    """Funzione helper per generare la firma corretta nei test."""
    mac = hmac.new(secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"

def test_verify_signature_valid():
    """Testa che una firma valida venga accettata."""
    valid_signature = generate_signature(TEST_SECRET, TEST_PAYLOAD)
    assert verify_github_signature(TEST_PAYLOAD, TEST_SECRET, valid_signature) is True

def test_verify_signature_invalid():
    """Testa che una firma errata venga rifiutata."""
    invalid_signature = "sha256=1234567890abcdef"
    assert verify_github_signature(TEST_PAYLOAD, TEST_SECRET, invalid_signature) is False

def test_verify_signature_missing():
    """Testa il comportamento se la firma è vuota o mancante."""
    assert verify_github_signature(TEST_PAYLOAD, TEST_SECRET, "") is False
