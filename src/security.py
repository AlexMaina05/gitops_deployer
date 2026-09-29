import hmac
import hashlib

def verify_github_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool:
    """
    Verifica la firma HMAC-SHA256 inviata da GitHub.
    """
    if not secret_token or not isinstance(secret_token, str):
        return False

    if not signature_header or not isinstance(signature_header, str) or not signature_header.startswith("sha256="):
        return False

    if not isinstance(payload_body, (bytes, bytearray)):
        return False

    try:
        # Generiamo la firma attesa in locale
        hash_object = hmac.new(secret_token.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
        expected_signature = "sha256=" + hash_object.hexdigest()

        # hmac.compare_digest protegge contro i timing attacks
        return hmac.compare_digest(expected_signature, signature_header)
    except (TypeError, UnicodeError):
        return False
