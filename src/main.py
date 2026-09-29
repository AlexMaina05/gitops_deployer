import logging
from fastapi import FastAPI, Request, HTTPException
from src.config import load_config
from src.security import verify_github_signature
from src.executor import deploy
from src.notifier import notify

logger = logging.getLogger(__name__)

app = FastAPI(
    title="GitOps Auto-Deployer",
    description="Automated deployment service triggered via Git webhooks with cryptographic HMAC verification and notification dispatch.",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint for liveness and readiness probes."""
    return {"status": "ok"}


@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    Receives incoming Git webhook requests, verifies HMAC-SHA256 signature,
    triggers deployment pipeline, and dispatches notification outcomes.
    """
    raw_config = getattr(request.app.state, "config", None)
    config = raw_config if raw_config is not None else load_config()
    if not isinstance(config, dict):
        config = {}

    webhook_cfg = (config.get("webhook") or {}) if isinstance(config, dict) else {}
    secret_token = (webhook_cfg.get("secret") or "") if isinstance(webhook_cfg, dict) else ""
    if not isinstance(secret_token, str) or not secret_token.strip():
        logger.warning("Webhook secret is empty or missing in configuration.")
        raise HTTPException(status_code=401, detail="Invalid signature")

    deploy_cfg = (config.get("deploy") or {}) if isinstance(config, dict) else {}
    repo_path = deploy_cfg.get("repo_path", ".") if isinstance(deploy_cfg, dict) else "."

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        logger.warning("Webhook request missing X-Hub-Signature-256 header.")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.body()

    if not verify_github_signature(
        payload_body=payload,
        secret_token=secret_token,
        signature_header=signature,
    ):
        logger.warning("HMAC signature verification failed for webhook request.")
        raise HTTPException(status_code=401, detail="Invalid signature")

    logger.info(f"HMAC verified successfully. Initiating deployment for repo: {repo_path}")
    deploy_success = deploy(repo_path)

    logger.info(f"Deployment finished with status: {deploy_success}. Dispatching notifications...")
    try:
        notify(status=deploy_success, repo_path=repo_path, config=config)
    except Exception as e:
        logger.error(f"Error during webhook notification dispatch: {e}")

    return {
        "status": "success" if deploy_success else "failed",
        "deployed": deploy_success,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
