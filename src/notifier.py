import html
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from src.config import load_config

logger = logging.getLogger(__name__)


def send_telegram_notification(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Sends a notification message to a Telegram chat via the Telegram Bot API.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram notification skipped: bot_token or chat_id is missing.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully.")
            return True
        else:
            logger.error(
                f"Telegram API responded with status {response.status_code}: {response.text}"
            )
            return False
    except httpx.HTTPError as e:
        logger.error(f"HTTP error sending Telegram notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram notification: {e}")
        return False


def send_n8n_notification(webhook_url: str, payload: dict) -> bool:
    """
    Sends a notification payload to an n8n webhook URL.
    """
    if not webhook_url:
        logger.warning("n8n notification skipped: webhook_url is missing.")
        return False

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        if 200 <= response.status_code < 300:
            logger.info("n8n notification sent successfully.")
            return True
        else:
            logger.error(
                f"n8n webhook responded with status {response.status_code}: {response.text}"
            )
            return False
    except httpx.HTTPError as e:
        logger.error(f"HTTP error sending n8n notification: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending n8n notification: {e}")
        return False


def notify(
    status: bool,
    repo_path: str,
    config: Optional[Dict[str, Any]] = None,
    details: str = "",
) -> Dict[str, bool]:
    """
    Dispatches deployment notifications to configured active targets (Telegram, n8n).
    Guarantees provider isolation so failure in one target never blocks others.
    """
    if config is None:
        config = load_config()
    elif hasattr(config, "model_dump"):
        config = config.model_dump()

    notifications_cfg = config.get("notifications") if isinstance(config, dict) else {}
    if not isinstance(notifications_cfg, dict):
        notifications_cfg = {}

    active_targets = notifications_cfg.get("active_targets") or []
    if not isinstance(active_targets, (list, tuple, set)):
        active_targets = []

    active_lower = [str(t).strip().lower() for t in active_targets if t is not None]

    # Format human-readable message for Telegram
    outcome_title = "SUCCESS" if status else "FAILED"
    icon = "🚀" if status else "❌"
    safe_outcome = html.escape(outcome_title)
    safe_repo_path = html.escape(str(repo_path))
    telegram_message = (
        f"{icon} <b>GitOps Deployment {safe_outcome}</b>\n"
        f"<b>Repository:</b> <code>{safe_repo_path}</code>"
    )
    if details:
        safe_details = html.escape(str(details))
        telegram_message += f"\n<b>Details:</b> {safe_details}"

    # Format structured payload for n8n
    timestamp = datetime.now(timezone.utc).isoformat()
    n8n_payload = {
        "event": "deployment",
        "status": "success" if status else "failure",
        "repo_path": repo_path,
        "message": f"Deployment {'succeeded' if status else 'failed'}" + (f": {details}" if details else ""),
        "details": details,
        "timestamp": timestamp,
    }

    outcomes: Dict[str, bool] = {}

    if "telegram" in active_lower:
        try:
            tg_cfg = notifications_cfg.get("telegram")
            if not isinstance(tg_cfg, dict):
                tg_cfg = {}
            bot_token = tg_cfg.get("bot_token", "") if isinstance(tg_cfg, dict) else ""
            chat_id = tg_cfg.get("chat_id", "") if isinstance(tg_cfg, dict) else ""
            outcomes["telegram"] = send_telegram_notification(
                bot_token=bot_token,
                chat_id=chat_id,
                message=telegram_message,
            )
        except Exception as e:
            logger.error(f"Isolated error handling Telegram notification: {e}")
            outcomes["telegram"] = False

    if "n8n" in active_lower:
        try:
            n8n_cfg = notifications_cfg.get("n8n")
            if not isinstance(n8n_cfg, dict):
                n8n_cfg = {}
            webhook_url = n8n_cfg.get("webhook_url", "") if isinstance(n8n_cfg, dict) else ""
            outcomes["n8n"] = send_n8n_notification(
                webhook_url=webhook_url,
                payload=n8n_payload,
            )
        except Exception as e:
            logger.error(f"Isolated error handling n8n notification: {e}")
            outcomes["n8n"] = False

    return outcomes
