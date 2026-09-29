import hmac
import hashlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.config import load_config

TEST_SECRET = "super_secret_test_token"
TEST_REPO_PATH = "/test/git/repo"
TEST_CONFIG = {
    "webhook": {"secret": TEST_SECRET},
    "deploy": {"repo_path": TEST_REPO_PATH},
    "notifications": {
        "active_targets": ["telegram", "n8n"],
        "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
        "n8n": {"webhook_url": "https://n8n.example.com/test"},
    },
}


def compute_signature(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("src.main.notify")
@patch("src.main.deploy")
@patch("src.main.load_config")
def test_webhook_missing_signature(mock_load_cfg, mock_deploy, mock_notify, client):
    mock_load_cfg.return_value = TEST_CONFIG
    payload = b'{"ref": "refs/heads/main"}'

    response = client.post("/webhook", content=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid signature"}
    mock_deploy.assert_not_called()
    mock_notify.assert_not_called()


@patch("src.main.notify")
@patch("src.main.deploy")
@patch("src.main.load_config")
def test_webhook_invalid_signature(mock_load_cfg, mock_deploy, mock_notify, client):
    mock_load_cfg.return_value = TEST_CONFIG
    payload = b'{"ref": "refs/heads/main"}'

    headers = {"X-Hub-Signature-256": "sha256=invalid_hex_digest_1234567890"}
    response = client.post("/webhook", content=payload, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid signature"}
    mock_deploy.assert_not_called()
    mock_notify.assert_not_called()


@patch("src.main.notify")
@patch("src.main.deploy")
@patch("src.main.load_config")
def test_webhook_valid_signature_deploy_success(
    mock_load_cfg, mock_deploy, mock_notify, client
):
    mock_load_cfg.return_value = TEST_CONFIG
    mock_deploy.return_value = True

    payload = b'{"ref": "refs/heads/main", "repository": {"full_name": "org/repo"}}'
    sig = compute_signature(TEST_SECRET, payload)
    headers = {"X-Hub-Signature-256": sig}

    response = client.post("/webhook", content=payload, headers=headers)

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
def test_webhook_valid_signature_deploy_failure(
    mock_load_cfg, mock_deploy, mock_notify, client
):
    mock_load_cfg.return_value = TEST_CONFIG
    mock_deploy.return_value = False

    payload = b'{"ref": "refs/heads/main", "repository": {"full_name": "org/repo"}}'
    sig = compute_signature(TEST_SECRET, payload)
    headers = {"X-Hub-Signature-256": sig}

    response = client.post("/webhook", content=payload, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "failed", "deployed": False}
    mock_deploy.assert_called_once_with(TEST_REPO_PATH)
    mock_notify.assert_called_once_with(
        status=False,
        repo_path=TEST_REPO_PATH,
        config=TEST_CONFIG,
    )


@patch("src.main.notify")
@patch("src.main.deploy")
@patch("src.main.load_config")
def test_webhook_empty_body_valid_signature(
    mock_load_cfg, mock_deploy, mock_notify, client
):
    mock_load_cfg.return_value = TEST_CONFIG
    mock_deploy.return_value = True

    payload = b""
    sig = compute_signature(TEST_SECRET, payload)
    headers = {"X-Hub-Signature-256": sig}

    response = client.post("/webhook", content=payload, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "success", "deployed": True}
    mock_deploy.assert_called_once_with(TEST_REPO_PATH)
    mock_notify.assert_called_once()


def test_config_loader_and_overrides(monkeypatch, tmp_path):
    # Test loading fallback defaults
    non_existent = str(tmp_path / "missing.yaml")
    cfg = load_config(non_existent)
    assert cfg["webhook"]["secret"] == "your_webhook_secret_here"
    assert cfg["deploy"]["repo_path"] == "e:/Code/gitops_deployer"

    # Test environment variable overrides
    monkeypatch.setenv("WEBHOOK_SECRET", "custom_secret_123")
    monkeypatch.setenv("REPO_PATH", "/custom/repo/path")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg_token_override")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://custom.n8n/hook")
    monkeypatch.setenv("ACTIVE_TARGETS", "telegram")

    cfg_overridden = load_config(non_existent)
    assert cfg_overridden["webhook"]["secret"] == "custom_secret_123"
    assert cfg_overridden["deploy"]["repo_path"] == "/custom/repo/path"
    assert cfg_overridden["notifications"]["telegram"]["bot_token"] == "tg_token_override"
    assert cfg_overridden["notifications"]["telegram"]["chat_id"] == "12345678"
    assert cfg_overridden["notifications"]["n8n"]["webhook_url"] == "https://custom.n8n/hook"
    assert cfg_overridden["notifications"]["active_targets"] == ["telegram"]


@patch("src.main.notify")
@patch("src.main.deploy")
def test_webhook_with_actual_config_file(mock_deploy, mock_notify, client):
    # Tests loading secret and repo_path directly from existing config.yaml without mocking load_config
    cfg = load_config("config.yaml")
    secret = cfg["webhook"]["secret"]
    repo_path = cfg["deploy"]["repo_path"]

    mock_deploy.return_value = True

    payload = b'{"ref": "refs/heads/main", "commits": []}'
    sig = compute_signature(secret, payload)
    headers = {"X-Hub-Signature-256": sig}

    response = client.post("/webhook", content=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "success", "deployed": True}
    mock_deploy.assert_called_once_with(repo_path)
    mock_notify.assert_called_once()

