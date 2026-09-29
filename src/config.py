import os
import json
import logging
from typing import Optional, List, Any, Dict
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class N8nConfig(BaseModel):
    webhook_url: str = ""


class NotificationsConfig(BaseModel):
    active_targets: List[str] = Field(default_factory=lambda: ["telegram", "n8n"])
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    n8n: N8nConfig = Field(default_factory=N8nConfig)


class DeployConfig(BaseModel):
    repo_path: str = "e:/Code/gitops_deployer"


class WebhookConfig(BaseModel):
    secret: str = "your_webhook_secret_here"


class AppConfig(BaseModel):
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)


class ConfigDict(dict):
    """Dictionary that also supports attribute access while maintaining full dict compatibility."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'ConfigDict' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _wrap_dict(d: Any) -> Any:
    if isinstance(d, dict):
        return ConfigDict({k: _wrap_dict(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_wrap_dict(i) for i in d]
    return d


def load_config(config_path: Optional[str] = "config.yaml") -> ConfigDict:
    """
    Loads application configuration from a YAML file with environment variable overrides.
    Returns a ConfigDict (compatible with standard dict).
    """
    file_path = config_path or os.getenv("CONFIG_PATH", "config.yaml")
    data: Dict[str, Any] = {}

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception as e:
            logger.error(f"Error loading configuration file {file_path}: {e}")

    try:
        app_cfg = AppConfig(**data)
    except Exception as e:
        logger.warning(f"Error validating config with AppConfig, using defaults: {e}")
        app_cfg = AppConfig()

    # Environment variable overrides
    env_secret = os.getenv("WEBHOOK_SECRET") or os.getenv("GITOPS_SECRET")
    if env_secret:
        app_cfg.webhook.secret = env_secret

    env_repo = os.getenv("REPO_PATH") or os.getenv("GITOPS_REPO_PATH")
    if env_repo:
        app_cfg.deploy.repo_path = env_repo

    env_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if env_bot_token:
        app_cfg.notifications.telegram.bot_token = env_bot_token

    env_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if env_chat_id:
        app_cfg.notifications.telegram.chat_id = env_chat_id

    env_n8n_url = os.getenv("N8N_WEBHOOK_URL")
    if env_n8n_url:
        app_cfg.notifications.n8n.webhook_url = env_n8n_url

    env_active = os.getenv("ACTIVE_TARGETS")
    if env_active:
        cleaned = env_active.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    app_cfg.notifications.active_targets = [str(t) for t in parsed]
            except Exception:
                app_cfg.notifications.active_targets = [
                    t.strip() for t in cleaned.strip("[]").split(",") if t.strip()
                ]
        else:
            app_cfg.notifications.active_targets = [
                t.strip() for t in cleaned.split(",") if t.strip()
            ]

    result_dict = app_cfg.model_dump()
    return _wrap_dict(result_dict)
