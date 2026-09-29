"""
Adversarial Stress Test Suite for GitOps Auto-Deployer Notifier & Config Modules.
Created by Challenger 2 (Empirical Adversary).
"""

import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest
import httpx
from fastapi.testclient import TestClient

from src.notifier import (
    send_telegram_notification,
    send_n8n_notification,
    notify,
)
from src.config import load_config
from src.main import app
import hmac
import hashlib


# ============================================================================
# 1. NETWORK FAULT SIMULATION (Timeouts, DNS failures, Protocol errors)
# ============================================================================

@pytest.mark.parametrize(
    "exception_cls",
    [
        httpx.ConnectTimeout("Connection timed out"),
        httpx.ReadTimeout("Read timed out"),
        httpx.WriteTimeout("Write timed out"),
        httpx.PoolTimeout("Pool exhausted"),
        httpx.ConnectError("getaddrinfo failed: DNS resolution failure"),
        httpx.NetworkError("Network socket closed abruptly"),
        httpx.RemoteProtocolError("Server disconnected without response"),
        httpx.TooManyRedirects("Exceeded 30 redirects"),
    ],
)
@patch("src.notifier.httpx.post")
def test_telegram_network_faults_handled_gracefully(mock_post, exception_cls):
    """Verify send_telegram_notification never crashes on network exceptions."""
    mock_post.side_effect = exception_cls
    result = send_telegram_notification("token123", "chat456", "Test message")
    assert result is False


@pytest.mark.parametrize(
    "exception_cls",
    [
        httpx.ConnectTimeout("Connection timed out"),
        httpx.ReadTimeout("Read timed out"),
        httpx.WriteTimeout("Write timed out"),
        httpx.PoolTimeout("Pool exhausted"),
        httpx.ConnectError("getaddrinfo failed: DNS resolution failure"),
        httpx.NetworkError("Network socket closed abruptly"),
        httpx.RemoteProtocolError("Server disconnected without response"),
        httpx.TooManyRedirects("Exceeded 30 redirects"),
    ],
)
@patch("src.notifier.httpx.post")
def test_n8n_network_faults_handled_gracefully(mock_post, exception_cls):
    """Verify send_n8n_notification never crashes on network exceptions."""
    mock_post.side_effect = exception_cls
    result = send_n8n_notification("https://n8n.example.com/webhook", {"event": "deploy"})
    assert result is False


# ============================================================================
# 2. SERVER-SIDE HTTP ERROR STATUS CODES (4xx, 5xx)
# ============================================================================

@pytest.mark.parametrize(
    "status_code,response_text",
    [
        (400, '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'),
        (401, '{"ok":false,"error_code":401,"description":"Unauthorized: invalid bot token"}'),
        (403, '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'),
        (404, '{"ok":false,"error_code":404,"description":"Not Found"}'),
        (429, '{"ok":false,"error_code":429,"description":"Too Many Requests: retry after 30"}'),
        (500, "Internal Server Error"),
        (502, "Bad Gateway"),
        (503, "Service Unavailable: Telegram backend overloaded"),
        (504, "Gateway Timeout"),
    ],
)
@patch("src.notifier.httpx.post")
def test_telegram_server_errors_handled_gracefully(mock_post, status_code, response_text):
    """Verify send_telegram_notification returns False on any non-200 HTTP response."""
    mock_post.return_value = MagicMock(status_code=status_code, text=response_text)
    result = send_telegram_notification("token123", "chat456", "Test message")
    assert result is False


@pytest.mark.parametrize(
    "status_code,response_text",
    [
        (400, "Bad Request: Workflow payload validation failed"),
        (401, "Unauthorized: missing webhook authentication"),
        (403, "Forbidden"),
        (404, "Workflow webhook not found"),
        (429, "Too Many Requests"),
        (500, "Workflow execution failed with internal error"),
        (502, "Bad Gateway"),
        (503, "Service Temporarily Unavailable"),
        (504, "Gateway Timeout waiting for workflow node"),
    ],
)
@patch("src.notifier.httpx.post")
def test_n8n_server_errors_handled_gracefully(mock_post, status_code, response_text):
    """Verify send_n8n_notification returns False on any non-2xx HTTP response."""
    mock_post.return_value = MagicMock(status_code=status_code, text=response_text)
    result = send_n8n_notification("https://n8n.example.com/webhook", {"event": "deploy"})
    assert result is False


# ============================================================================
# 3. PROVIDER FAULT ISOLATION (Failure in one provider never stops the other)
# ============================================================================

@patch("src.notifier.send_telegram_notification")
@patch("src.notifier.send_n8n_notification")
def test_isolation_telegram_connect_timeout_does_not_block_n8n(mock_n8n, mock_tg):
    """Telegram times out with ConnectTimeout; n8n must still be called and succeed."""
    mock_tg.side_effect = httpx.ConnectTimeout("Telegram connection timed out")
    mock_n8n.return_value = True

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {"telegram": False, "n8n": True}
    assert mock_tg.call_count == 1
    assert mock_n8n.call_count == 1


@patch("src.notifier.send_telegram_notification")
@patch("src.notifier.send_n8n_notification")
def test_isolation_n8n_connect_timeout_does_not_block_telegram(mock_n8n, mock_tg):
    """n8n times out with ConnectTimeout; Telegram must still succeed."""
    mock_tg.return_value = True
    mock_n8n.side_effect = httpx.ConnectTimeout("n8n connection timed out")

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {"telegram": True, "n8n": False}
    assert mock_tg.call_count == 1
    assert mock_n8n.call_count == 1


@patch("src.notifier.send_telegram_notification")
@patch("src.notifier.send_n8n_notification")
def test_isolation_both_providers_fail(mock_n8n, mock_tg):
    """Both providers fail; notify must return both as False without crashing."""
    mock_tg.side_effect = httpx.ConnectError("DNS resolution failed for Telegram")
    mock_n8n.side_effect = httpx.HTTPStatusError("500 Internal Server Error", request=MagicMock(), response=MagicMock())

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {"telegram": False, "n8n": False}


@patch("src.notifier.send_telegram_notification")
@patch("src.notifier.send_n8n_notification")
def test_isolation_telegram_arbitrary_unhandled_exception(mock_n8n, mock_tg):
    """Telegram raises unexpected unhandled exception (e.g. KeyError or MemoryError)."""
    mock_tg.side_effect = KeyError("Unexpected dictionary key error")
    mock_n8n.return_value = True

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    outcomes = notify(status=False, repo_path="/app", config=config)
    assert outcomes == {"telegram": False, "n8n": True}


# ============================================================================
# 4. CONFIGURATION ROBUSTNESS & EDGE CASES
# ============================================================================

def test_config_missing_file_falls_back_to_defaults():
    """Missing config file should load default AppConfig without raising."""
    cfg = load_config("nonexistent_path_xyz_123.yaml")
    assert cfg.deploy.repo_path == "e:/Code/gitops_deployer"
    assert "telegram" in cfg.notifications.active_targets
    assert "n8n" in cfg.notifications.active_targets


def test_config_corrupted_yaml_syntax():
    """Corrupted YAML file should log error and return default config."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write("invalid: [yaml: syntax: {unclosed\n\t\tbad_tabs: 123")
        temp_path = f.name

    try:
        cfg = load_config(temp_path)
        assert cfg.deploy.repo_path == "e:/Code/gitops_deployer"
        assert cfg.notifications.active_targets == ["telegram", "n8n"]
    finally:
        os.remove(temp_path)


def test_config_empty_file():
    """Empty YAML file should load default config."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write("")
        temp_path = f.name

    try:
        cfg = load_config(temp_path)
        assert cfg.deploy.repo_path == "e:/Code/gitops_deployer"
    finally:
        os.remove(temp_path)


def test_config_non_dict_yaml_content():
    """YAML file containing a scalar or list should fall back to default config."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write("- item1\n- item2\n")
        temp_path = f.name

    try:
        cfg = load_config(temp_path)
        assert cfg.deploy.repo_path == "e:/Code/gitops_deployer"
    finally:
        os.remove(temp_path)


def test_config_unknown_active_targets_in_notify():
    """Unknown targets like ['slack', 'discord', ''] should not crash notify()."""
    config = {
        "notifications": {
            "active_targets": ["slack", "discord", ""],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {}


def test_config_case_insensitive_active_targets():
    """Active targets specified in uppercase should be recognized."""
    with patch("src.notifier.send_telegram_notification", return_value=True) as mock_tg:
        with patch("src.notifier.send_n8n_notification", return_value=True) as mock_n8n:
            config = {
                "notifications": {
                    "active_targets": ["TELEGRAM", "N8N"],
                    "telegram": {"bot_token": "tok", "chat_id": "cid"},
                    "n8n": {"webhook_url": "https://n8n.com/hook"},
                }
            }
            outcomes = notify(status=True, repo_path="/app", config=config)
            assert outcomes == {"telegram": True, "n8n": True}


def test_config_whitespace_in_active_targets():
    """Active targets with leading/trailing whitespace should ideally be recognized or not crash."""
    config = {
        "notifications": {
            "active_targets": [" telegram ", " n8n "],
            "telegram": {"bot_token": "tok", "chat_id": "cid"},
            "n8n": {"webhook_url": "https://n8n.com/hook"},
        }
    }
    # This checks whether whitespace causes failure to dispatch or crashes
    outcomes = notify(status=True, repo_path="/app", config=config)
    # If not stripped, outcomes is empty {}
    assert isinstance(outcomes, dict)


def test_config_notifications_is_none():
    """When config['notifications'] is None, notify() must not raise AttributeError."""
    config = {
        "notifications": None
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {}


def test_config_active_targets_is_none():
    """When notifications['active_targets'] is None, notify() must not raise TypeError."""
    config = {
        "notifications": {
            "active_targets": None
        }
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {}


def test_config_active_targets_is_int():
    """When notifications['active_targets'] is an integer, notify() must not raise TypeError."""
    config = {
        "notifications": {
            "active_targets": 123
        }
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {}


def test_config_whitespace_in_active_targets_should_dispatch():
    """Active targets with leading/trailing whitespace should be recognized after stripping."""
    with patch("src.notifier.send_telegram_notification", return_value=True) as mock_tg:
        with patch("src.notifier.send_n8n_notification", return_value=True) as mock_n8n:
            config = {
                "notifications": {
                    "active_targets": [" telegram ", " n8n "],
                    "telegram": {"bot_token": "tok", "chat_id": "cid"},
                    "n8n": {"webhook_url": "https://n8n.com/hook"},
                }
            }
            outcomes = notify(status=True, repo_path="/app", config=config)
            assert outcomes == {"telegram": True, "n8n": True}


def test_config_telegram_is_none():
    """When notifications['telegram'] is None, notify() must not crash."""
    config = {
        "notifications": {
            "active_targets": ["telegram"],
            "telegram": None
        }
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {"telegram": False}


def test_config_n8n_is_none():
    """When notifications['n8n'] is None, notify() must not crash."""
    config = {
        "notifications": {
            "active_targets": ["n8n"],
            "n8n": None
        }
    }
    outcomes = notify(status=True, repo_path="/app", config=config)
    assert outcomes == {"n8n": False}


# ============================================================================
# 5. FASTAPI WEBHOOK FAULT RESILIENCE
# ============================================================================

@patch("src.main.deploy", return_value=True)
@patch("src.notifier.send_telegram_notification", side_effect=httpx.ConnectTimeout("Telegram dead"))
@patch("src.notifier.send_n8n_notification", side_effect=httpx.ConnectError("n8n DNS dead"))
def test_webhook_succeeds_even_when_all_notification_targets_are_dead(mock_n8n, mock_tg, mock_deploy):
    """The webhook response must remain 200 OK even if all notification targets timeout or fail."""
    secret = "adversarial_secret"
    payload = b'{"ref": "refs/heads/main"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    app.state.config = {
        "webhook": {"secret": secret},
        "deploy": {"repo_path": "/opt/repo"},
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_token", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    client = TestClient(app)
    response = client.post(
        "/webhook",
        content=payload,
        headers={"X-Hub-Signature-256": sig},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["deployed"] is True
    assert mock_deploy.called
    assert mock_tg.called
    assert mock_n8n.called


@patch("src.main.deploy", return_value=True)
def test_webhook_with_null_notifications_config(mock_deploy):
    """If app.state.config has notifications=None, webhook endpoint should not crash with 500."""
    secret = "adversarial_secret"
    payload = b'{"ref": "refs/heads/main"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    app.state.config = {
        "webhook": {"secret": secret},
        "deploy": {"repo_path": "/opt/repo"},
        "notifications": None,
    }

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook",
        content=payload,
        headers={"X-Hub-Signature-256": sig},
    )

    # If notify() crashes with AttributeError, this returns 500
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ============================================================================
# 6. TELEGRAM HTML SPECIAL CHARACTER PARSING RESILIENCE
# ============================================================================

def test_telegram_html_special_characters_escaped():
    """Verify <, >, &, quotes in repo_path and details are escaped for Telegram HTML mode."""
    with patch("src.notifier.send_telegram_notification") as mock_tg:
        config = {
            "notifications": {
                "active_targets": ["telegram"],
                "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            }
        }
        repo_path = "/repo/<evil>&branch'\""
        details = "Error: condition <tag> failed & x > y with 'quotes' and \"double\""

        notify(status=False, repo_path=repo_path, config=config, details=details)

        assert mock_tg.called
        msg = mock_tg.call_args[1]["message"]
        # In Telegram HTML, raw '<' and '&' must be escaped as '&lt;' and '&amp;'
        assert "<evil>" not in msg
        assert "&lt;evil&gt;&amp;branch" in msg
        assert "&lt;tag&gt;" in msg
        assert "x &gt; y" in msg
        assert "&amp;" in msg


def test_telegram_html_parse_error_api_response_isolation():
    """If Telegram rejects HTML message with 400 Bad Request (entity parse error), isolation holds."""
    with patch("src.notifier.httpx.post") as mock_post:
        with patch("src.notifier.send_n8n_notification", return_value=True) as mock_n8n:
            mock_post.return_value = MagicMock(
                status_code=400,
                text='{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities: Unsupported start tag"}'
            )
            config = {
                "notifications": {
                    "active_targets": ["telegram", "n8n"],
                    "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
                    "n8n": {"webhook_url": "https://n8n.example.com/hook"},
                }
            }
            outcomes = notify(status=True, repo_path="/app", config=config, details="invalid html")
            assert outcomes == {"telegram": False, "n8n": True}

