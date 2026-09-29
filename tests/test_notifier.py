from unittest.mock import patch, MagicMock
import httpx
import pytest

from src.notifier import (
    send_telegram_notification,
    send_n8n_notification,
    notify,
)


@patch("src.notifier.httpx.post")
def test_send_telegram_notification_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, text="OK")
    result = send_telegram_notification(
        bot_token="test_token_123",
        chat_id="chat_456",
        message="Test message",
    )
    assert result is True
    mock_post.assert_called_once_with(
        "https://api.telegram.org/bottest_token_123/sendMessage",
        json={"chat_id": "chat_456", "text": "Test message", "parse_mode": "HTML"},
        timeout=10.0,
    )


@patch("src.notifier.httpx.post")
def test_send_telegram_notification_missing_credentials(mock_post):
    assert send_telegram_notification(bot_token="", chat_id="123", message="hi") is False
    assert send_telegram_notification(bot_token="tok", chat_id="", message="hi") is False
    mock_post.assert_not_called()


@patch("src.notifier.httpx.post")
def test_send_telegram_notification_http_error(mock_post):
    mock_post.side_effect = httpx.ConnectError("Connection refused")
    result = send_telegram_notification(
        bot_token="test_token_123",
        chat_id="chat_456",
        message="Test message",
    )
    assert result is False


@patch("src.notifier.httpx.post")
def test_send_telegram_notification_non_200(mock_post):
    mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
    result = send_telegram_notification(
        bot_token="test_token_123",
        chat_id="chat_456",
        message="Test message",
    )
    assert result is False


@patch("src.notifier.httpx.post")
def test_send_n8n_notification_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, text="OK")
    payload = {"event": "deployment", "status": "success", "repo_path": "/opt/repo"}
    result = send_n8n_notification(
        webhook_url="https://n8n.example.com/webhook/test",
        payload=payload,
    )
    assert result is True
    mock_post.assert_called_once_with(
        "https://n8n.example.com/webhook/test",
        json=payload,
        timeout=10.0,
    )


@patch("src.notifier.httpx.post")
def test_send_n8n_notification_missing_url(mock_post):
    assert send_n8n_notification(webhook_url="", payload={"event": "deployment"}) is False
    mock_post.assert_not_called()


@patch("src.notifier.httpx.post")
def test_send_n8n_notification_http_error(mock_post):
    mock_post.side_effect = httpx.RequestError("Network unreachable")
    result = send_n8n_notification(
        webhook_url="https://n8n.example.com/webhook/test",
        payload={"event": "deployment"},
    )
    assert result is False


@patch("src.notifier.httpx.post")
def test_send_n8n_notification_non_200(mock_post):
    mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
    result = send_n8n_notification(
        webhook_url="https://n8n.example.com/webhook/test",
        payload={"event": "deployment"},
    )
    assert result is False


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
def test_notify_dispatch_both_active(mock_tg, mock_n8n):
    mock_tg.return_value = True
    mock_n8n.return_value = True

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    results = notify(status=True, repo_path="/app/deploy", config=config, details="All containers restarted")

    assert results == {"telegram": True, "n8n": True}
    assert mock_tg.call_count == 1
    assert mock_n8n.call_count == 1

    tg_args, tg_kwargs = mock_tg.call_args
    assert tg_kwargs["bot_token"] == "tg_tok"
    assert tg_kwargs["chat_id"] == "tg_chat"
    assert "/app/deploy" in tg_kwargs["message"]
    assert "SUCCESS" in tg_kwargs["message"]
    assert "All containers restarted" in tg_kwargs["message"]

    n8n_args, n8n_kwargs = mock_n8n.call_args
    assert n8n_kwargs["webhook_url"] == "https://n8n.example.com/hook"
    assert n8n_kwargs["payload"]["status"] == "success"
    assert n8n_kwargs["payload"]["repo_path"] == "/app/deploy"
    assert n8n_kwargs["payload"]["details"] == "All containers restarted"


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
def test_notify_dispatch_only_telegram(mock_tg, mock_n8n):
    mock_tg.return_value = True

    config = {
        "notifications": {
            "active_targets": ["telegram"],
            "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    results = notify(status=True, repo_path="/app/deploy", config=config)

    assert results == {"telegram": True}
    assert mock_tg.call_count == 1
    mock_n8n.assert_not_called()


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
def test_notify_dispatch_only_n8n(mock_tg, mock_n8n):
    mock_n8n.return_value = True

    config = {
        "notifications": {
            "active_targets": ["n8n"],
            "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    results = notify(status=False, repo_path="/app/deploy", config=config)

    assert results == {"n8n": True}
    mock_tg.assert_not_called()
    assert mock_n8n.call_count == 1
    assert mock_n8n.call_args[1]["payload"]["status"] == "failure"


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
def test_notify_dispatch_neither_active(mock_tg, mock_n8n):
    config = {
        "notifications": {
            "active_targets": [],
            "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    results = notify(status=True, repo_path="/app/deploy", config=config)

    assert results == {}
    mock_tg.assert_not_called()
    mock_n8n.assert_not_called()


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
def test_notify_isolation_telegram_failure_does_not_block_n8n(mock_tg, mock_n8n):
    mock_tg.side_effect = RuntimeError("Fatal Telegram failure")
    mock_n8n.return_value = True

    config = {
        "notifications": {
            "active_targets": ["telegram", "n8n"],
            "telegram": {"bot_token": "tg_tok", "chat_id": "tg_chat"},
            "n8n": {"webhook_url": "https://n8n.example.com/hook"},
        }
    }

    results = notify(status=True, repo_path="/app/deploy", config=config)

    assert results == {"telegram": False, "n8n": True}
    assert mock_tg.call_count == 1
    assert mock_n8n.call_count == 1


@patch("src.notifier.send_n8n_notification")
@patch("src.notifier.send_telegram_notification")
@patch("src.notifier.load_config")
def test_notify_with_default_config_loader(mock_load_cfg, mock_tg, mock_n8n):
    mock_load_cfg.return_value = {
        "notifications": {
            "active_targets": ["telegram"],
            "telegram": {"bot_token": "def_tok", "chat_id": "def_chat"},
            "n8n": {"webhook_url": ""},
        }
    }
    mock_tg.return_value = True

    results = notify(status=True, repo_path="/test/repo", config=None)
    assert results == {"telegram": True}
    mock_load_cfg.assert_called_once()
    mock_tg.assert_called_once()
    mock_n8n.assert_not_called()

