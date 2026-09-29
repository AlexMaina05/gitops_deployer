import os
import time
import hmac
import hashlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.security import verify_github_signature

TEST_SECRET = "adversarial_secret_token_xyz123!@#"
TEST_REPO_PATH = "/test/adversarial/repo"
TEST_CONFIG = {
    "webhook": {"secret": TEST_SECRET},
    "deploy": {"repo_path": TEST_REPO_PATH},
    "notifications": {
        "active_targets": ["telegram", "n8n"],
        "telegram": {"bot_token": "mock_tg_token", "chat_id": "mock_chat_id"},
        "n8n": {"webhook_url": "https://n8n.mock.domain/hook"},
    },
}

STANDARD_PAYLOAD = b'{"ref": "refs/heads/main", "repository": {"name": "test-repo"}, "pusher": {"name": "alice"}}'


def compute_signature(secret: str, payload: bytes) -> str:
    """Helper to compute valid HMAC-SHA256 signature."""
    mac = hmac.new(secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.fixture(autouse=True)
def isolate_app_state():
    """
    Ensures test isolation by resetting app.state.config before and after every test,
    preventing state pollution across test modules.
    """
    if hasattr(app.state, "config"):
        delattr(app.state, "config")
    yield
    if hasattr(app.state, "config"):
        delattr(app.state, "config")


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. BIT-FLIP ATTACKS ON HMAC SIGNATURE
# ==============================================================================

class TestBitFlipAttacks:
    """
    Stress-testing single and multiple bit flips across the HMAC signature.
    Verifies that altering any character in the 64-hex string is rejected with 401.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_bit_flip_first_character(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
        digest = valid_sig[7:]
        flipped_char = "0" if digest[0] != "0" else "1"
        corrupted_sig = f"sha256={flipped_char}{digest[1:]}"

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": corrupted_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_bit_flip_last_character(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
        digest = valid_sig[7:]
        flipped_char = "0" if digest[-1] != "0" else "1"
        corrupted_sig = f"sha256={digest[:-1]}{flipped_char}"

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": corrupted_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_bit_flip_across_all_positions(self, mock_load_cfg, mock_deploy, mock_notify, client):
        """Test mutating characters at multiple intermediate positions across the 64-hex digest."""
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
        digest = valid_sig[7:]

        test_indices = list(range(0, 64, 4)) + [63]
        for idx in test_indices:
            orig_char = digest[idx]
            corrupt_char = "a" if orig_char != "a" else "b"
            corrupted_digest = digest[:idx] + corrupt_char + digest[idx + 1:]
            corrupted_sig = f"sha256={corrupted_digest}"

            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": corrupted_sig})
            assert response.status_code == 401, f"Failed at flip index {idx}: expected 401, got {response.status_code}"
            assert response.json() == {"detail": "Invalid signature"}

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_signature_truncation(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)

        for length in [63, 32, 16, 1]:
            truncated_sig = valid_sig[: 7 + length]
            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": truncated_sig})
            assert response.status_code == 401
            assert response.json() == {"detail": "Invalid signature"}

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_signature_elongation(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)

        elongated_sig = valid_sig + "0"
        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": elongated_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()


# ==============================================================================
# 2. ALGORITHM CONFUSION & PREFIX MUTATION ATTACKS
# ==============================================================================

class TestAlgorithmConfusion:
    """
    Stress-testing algorithm confusion (sha1, md5, sha512, raw hex, wrong case).
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_sha1_algorithm_confusion(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mac_sha1 = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.sha1).hexdigest()
        sha1_sig = f"sha1={mac_sha1}"

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": sha1_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_md5_algorithm_confusion(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mac_md5 = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.md5).hexdigest()
        md5_sig = f"md5={mac_md5}"

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": md5_sig})
        assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_sha512_algorithm_confusion(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mac_sha512 = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.sha512).hexdigest()
        sha512_sig = f"sha512={mac_sha512}"

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": sha512_sig})
        assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_raw_hex_without_prefix(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        raw_hex = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.sha256).hexdigest()

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": raw_hex})
        assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_uppercase_prefix_and_digest(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        raw_hex = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.sha256).hexdigest()

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": f"SHA256={raw_hex}"})
        assert response.status_code == 401

        response2 = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": f"sha256={raw_hex.upper()}"})
        assert response2.status_code == 401

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_corrupted_prefix_variants(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        raw_hex = hmac.new(TEST_SECRET.encode(), STANDARD_PAYLOAD, hashlib.sha256).hexdigest()

        bad_prefixes = [
            f"sha256:{raw_hex}",
            f"sha256 {raw_hex}",
            f"sha256={raw_hex}=",
            f"sha256=sha256={raw_hex}",
            f"sha-256={raw_hex}",
            "sha256=",
            "sha256= ",
        ]
        for sig in bad_prefixes:
            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": sig})
            assert response.status_code == 401, f"Prefix variant {sig} expected 401, got {response.status_code}"

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()


# ==============================================================================
# 3. MISSING, EMPTY, AND MALFORMED SIGNATURE HEADERS
# ==============================================================================

class TestMissingAndMalformedHeaders:
    """
    Stress-testing missing, empty, whitespace-only, and injection-like headers.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_missing_header(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        response = client.post("/webhook", content=STANDARD_PAYLOAD)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_empty_string_header(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": ""})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_whitespace_headers(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        for ws in [" ", "   ", "\t", "\n", "\r\n"]:
            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": ws})
            assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_injection_strings_as_header(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        injections = [
            "' OR '1'='1",
            "; rm -rf /",
            "$(whoami)",
            "{{ 7 * 7 }}",
            "sha256=' OR '1'='1",
            "sha256=\x00something",
            "sha256=" + "\x00" * 64,
            "sha256=../../etc/passwd",
        ]
        for inj in injections:
            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": inj})
            assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    def test_unicode_signature_header_raises_typeerror(self):
        """
        Adversarial Defect Check:
        When non-ASCII characters appear in signature_header, hmac.compare_digest in
        src/security.py:16 raises TypeError: comparing strings with non-ASCII characters is not supported.
        In secure code, this should return False (or 401 in main.py) instead of crashing with TypeError / 500.
        """
        unicode_sig = "sha256=\u26a1unicode_attack_payload"
        # Expecting safe False, but src/security.py crashes with TypeError
        assert verify_github_signature(STANDARD_PAYLOAD, TEST_SECRET, unicode_sig) is False


# ==============================================================================
# 4. WRONG SECRET KEY ATTACKS
# ==============================================================================

class TestWrongSecretKey:
    """
    Stress-testing signature calculation with incorrect, mutated, or empty secrets.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_wrong_secrets(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        wrong_secrets = [
            TEST_SECRET + " ",
            " " + TEST_SECRET,
            TEST_SECRET[:-1],
            TEST_SECRET.lower() if TEST_SECRET != TEST_SECRET.lower() else TEST_SECRET.upper(),
            "completely_wrong_secret",
            "",
            "None",
            "null",
            "0",
        ]
        for bad_sec in wrong_secrets:
            sig = compute_signature(bad_sec, STANDARD_PAYLOAD)
            response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": sig})
            assert response.status_code == 401, f"Secret '{bad_sec}' unexpectedly succeeded"
            assert response.json() == {"detail": "Invalid signature"}

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()


# ==============================================================================
# 5. PAYLOAD TAMPERING ATTACKS
# ==============================================================================

class TestPayloadTampering:
    """
    Stress-testing payload tampering: signature matches payload A, but request transmits payload B.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_payload_substitution(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        payload_a = b'{"ref": "refs/heads/main", "legitimate": true}'
        payload_b = b'{"ref": "refs/heads/main", "attacker_override": true}'

        sig_a = compute_signature(TEST_SECRET, payload_a)

        response = client.post("/webhook", content=payload_b, headers={"X-Hub-Signature-256": sig_a})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_whitespace_and_newline_tampering(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)

        tampered_variants = [
            STANDARD_PAYLOAD + b" ",
            b" " + STANDARD_PAYLOAD,
            STANDARD_PAYLOAD + b"\n",
            STANDARD_PAYLOAD + b"\r\n",
            STANDARD_PAYLOAD + b"\t",
            STANDARD_PAYLOAD + b"\x00",
        ]
        for tampered in tampered_variants:
            response = client.post("/webhook", content=tampered, headers={"X-Hub-Signature-256": valid_sig})
            assert response.status_code == 401
            assert response.json() == {"detail": "Invalid signature"}

        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_single_character_payload_modification(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)

        tampered_payload = STANDARD_PAYLOAD.replace(b"main", b"rain")
        response = client.post("/webhook", content=tampered_payload, headers={"X-Hub-Signature-256": valid_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()


# ==============================================================================
# 6. NON-JSON, MALFORMED, AND MASSIVE PAYLOAD BODIES
# ==============================================================================

class TestNonJsonAndMassivePayloads:
    """
    Stress-testing plain text, arbitrary binary data, empty bodies, and large payloads.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_plain_text_payload_invalid_sig(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        plain_text = b"echo 'Hello World'"
        response = client.post("/webhook", content=plain_text, headers={"X-Hub-Signature-256": "sha256=bad123"})
        assert response.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_plain_text_payload_valid_sig(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mock_deploy.return_value = True
        plain_text = b"echo 'Hello World'"
        sig = compute_signature(TEST_SECRET, plain_text)

        response = client.post("/webhook", content=plain_text, headers={"X-Hub-Signature-256": sig})
        assert response.status_code == 200
        assert response.json() == {"status": "success", "deployed": True}
        mock_deploy.assert_called_once_with(TEST_REPO_PATH)
        mock_notify.assert_called_once()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_arbitrary_binary_payload(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mock_deploy.return_value = True
        binary_payload = bytes([i % 256 for i in range(2048)])
        sig = compute_signature(TEST_SECRET, binary_payload)

        bad_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
        response_bad = client.post("/webhook", content=binary_payload, headers={"X-Hub-Signature-256": bad_sig})
        assert response_bad.status_code == 401
        mock_deploy.assert_not_called()

        response_ok = client.post("/webhook", content=binary_payload, headers={"X-Hub-Signature-256": sig})
        assert response_ok.status_code == 200
        mock_deploy.assert_called_once_with(TEST_REPO_PATH)

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_huge_payload_1mb_invalid_signature(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        huge_payload = b"X" * (1024 * 1024)
        bad_sig = "sha256=" + "a" * 64

        response = client.post("/webhook", content=huge_payload, headers={"X-Hub-Signature-256": bad_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_huge_payload_5mb_valid_and_tampered(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mock_deploy.return_value = True
        huge_payload = b'{"data": "' + (b"A" * (5 * 1024 * 1024)) + b'"}'
        valid_sig = compute_signature(TEST_SECRET, huge_payload)

        response = client.post("/webhook", content=huge_payload, headers={"X-Hub-Signature-256": valid_sig})
        assert response.status_code == 200
        assert response.json() == {"status": "success", "deployed": True}
        mock_deploy.assert_called_once_with(TEST_REPO_PATH)

        mock_deploy.reset_mock()
        mock_notify.reset_mock()

        tampered_huge = huge_payload[:-2] + b'B"}'
        response_tampered = client.post("/webhook", content=tampered_huge, headers={"X-Hub-Signature-256": valid_sig})
        assert response_tampered.status_code == 401
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_excessively_long_signature_header(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        long_sig = "sha256=" + "a" * 10000

        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": long_sig})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid signature"}
        mock_deploy.assert_not_called()
        mock_notify.assert_not_called()


# ==============================================================================
# 7. CONSTANT-TIME / TIMING RESISTANCE VERIFICATION
# ==============================================================================

class TestTimingAttackResistance:
    """
    Verifies that hmac.compare_digest is utilized and constant-time behavior holds.
    """

    def test_verify_github_signature_uses_compare_digest(self):
        with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_cmp:
            valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
            result = verify_github_signature(STANDARD_PAYLOAD, TEST_SECRET, valid_sig)
            assert result is True
            mock_cmp.assert_called_once()

    def test_timing_differential_first_vs_last_char_flip(self):
        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
        digest = valid_sig[7:]

        def measure_times(corrupted_sig: str, iterations: int = 5000) -> float:
            start = time.perf_counter()
            for _ in range(iterations):
                verify_github_signature(STANDARD_PAYLOAD, TEST_SECRET, corrupted_sig)
            return (time.perf_counter() - start) / iterations

        sig_pos_0 = f"sha256={'0' if digest[0] != '0' else '1'}{digest[1:]}"
        sig_pos_31 = f"sha256={digest[:31]}{'0' if digest[31] != '0' else '1'}{digest[32:]}"
        sig_pos_63 = f"sha256={digest[:-1]}{'0' if digest[-1] != '0' else '1'}"

        measure_times(sig_pos_0, iterations=500)

        t_0 = measure_times(sig_pos_0, iterations=5000)
        t_31 = measure_times(sig_pos_31, iterations=5000)
        t_63 = measure_times(sig_pos_63, iterations=5000)

        assert abs(t_0 - t_63) < 0.0001, f"Unusual timing difference detected: t_0={t_0:.8f}s, t_63={t_63:.8f}s"
        assert abs(t_0 - t_31) < 0.0001, f"Unusual timing difference detected: t_0={t_0:.8f}s, t_31={t_31:.8f}s"


# ==============================================================================
# 8. POSITIVE CONTROLS & STATE INVARIANTS
# ==============================================================================

class TestPositiveControlsAndStateInvariants:
    """
    Ensure valid requests succeed and failure paths leave no side effects.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_positive_control_complete_flow(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mock_deploy.return_value = True

        sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)
        response = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": sig})

        assert response.status_code == 200
        assert response.json() == {"status": "success", "deployed": True}
        mock_deploy.assert_called_once_with(TEST_REPO_PATH)
        mock_notify.assert_called_once_with(
            status=True,
            repo_path=TEST_REPO_PATH,
            config=TEST_CONFIG,
        )

    @patch("src.main.notify")
    @patch("src.main.deploy")
    @patch("src.main.load_config")
    def test_multiple_sequential_adversarial_requests_isolation(self, mock_load_cfg, mock_deploy, mock_notify, client):
        mock_load_cfg.return_value = TEST_CONFIG
        mock_deploy.return_value = True

        valid_sig = compute_signature(TEST_SECRET, STANDARD_PAYLOAD)

        for i in range(20):
            bad_sig = f"sha256={'bad'*21}{i%10}"
            resp = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": bad_sig})
            assert resp.status_code == 401

        assert mock_deploy.call_count == 0
        assert mock_notify.call_count == 0

        resp_valid = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": valid_sig})
        assert resp_valid.status_code == 200
        assert mock_deploy.call_count == 1
        assert mock_notify.call_count == 1

    def test_invalid_http_methods(self, client):
        """GET, PUT, DELETE, PATCH on /webhook must return 405 Method Not Allowed."""
        assert client.get("/webhook").status_code == 405
        assert client.put("/webhook").status_code == 405
        assert client.delete("/webhook").status_code == 405
        assert client.patch("/webhook").status_code == 405


# ==============================================================================
# 9. ADVERSARIAL DEFECTS & VULNERABILITIES IDENTIFIED
# ==============================================================================

class TestAdversarialDefectsIdentified:
    """
    Empirical proof of security defects identified in webhook endpoint & signature validation.
    """

    @patch("src.main.notify")
    @patch("src.main.deploy")
    def test_empty_secret_authentication_bypass_vulnerability(self, mock_deploy, mock_notify, client):
        """
        DEFECT: When config has webhook.secret='', an attacker can authenticate using an HMAC
        calculated with empty secret b'', obtaining 200 OK and triggering arbitrary deployments.
        In secure implementations, empty secrets must be rejected outright with 401/error.
        """
        app.state.config = {"webhook": {"secret": ""}, "deploy": {"repo_path": "/repo"}, "notifications": {}}
        mock_deploy.return_value = True
        mac = hmac.new(b"", msg=STANDARD_PAYLOAD, digestmod=hashlib.sha256).hexdigest()
        empty_sec_sig = f"sha256={mac}"

        resp = client.post("/webhook", content=STANDARD_PAYLOAD, headers={"X-Hub-Signature-256": empty_sec_sig})
        # Asserting secure requirement: must be rejected with 401.
        # This assertion FAILS because the server returns 200 and calls deploy!
        assert resp.status_code == 401, f"CRITICAL: Empty secret allowed authentication! Status: {resp.status_code}, deployed: {mock_deploy.called}"

    @patch("src.main.deploy")
    def test_null_secret_in_config_crashes_with_500(self, mock_deploy, client):
        """
        DEFECT: When config has webhook.secret=None, verify_github_signature crashes with
        AttributeError: 'NoneType' object has no attribute 'encode', causing unhandled 500.
        In secure implementations, this should safely return 401 or handled rejection.
        """
        app.state.config = {"webhook": {"secret": None}, "deploy": {"repo_path": "/repo"}}
        unhandled_client = TestClient(app, raise_server_exceptions=False)
        response = unhandled_client.post(
            "/webhook",
            content=STANDARD_PAYLOAD,
            headers={"X-Hub-Signature-256": "sha256=1234"},
        )
        assert response.status_code == 401, f"Expected 401 safe rejection, got {response.status_code}"

    @patch("src.main.deploy")
    def test_null_webhook_block_in_config_crashes_with_500(self, mock_deploy, client):
        """
        DEFECT: When config has webhook=None, main.py crashes with AttributeError on None.get('secret').
        """
        app.state.config = {"webhook": None, "deploy": {"repo_path": "/repo"}}
        unhandled_client = TestClient(app, raise_server_exceptions=False)
        response = unhandled_client.post(
            "/webhook",
            content=STANDARD_PAYLOAD,
            headers={"X-Hub-Signature-256": "sha256=1234"},
        )
        assert response.status_code == 401, f"Expected 401 safe rejection, got {response.status_code}"
