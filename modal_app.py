"""Modal runtime for the Akış MVP."""

import os
from typing import Any

import modal
from composio import Composio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


image = modal.Image.debian_slim().uv_pip_install("fastapi[standard]", "composio")
app = modal.App(name="akis-workflow")

api = FastAPI(title="Akış Workflow API", version="0.1.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "https://atpsec.github.io",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def describe_tool(tool: Any) -> dict[str, str]:
    """Normalize Composio's provider-specific tool shape for the UI."""
    if isinstance(tool, dict):
        raw = tool
    elif hasattr(tool, "model_dump"):
        raw = tool.model_dump()
    elif hasattr(tool, "dict"):
        raw = tool.dict()
    else:
        raw = {}

    function = raw.get("function") if isinstance(raw, dict) else None
    if not isinstance(function, dict):
        function = {}
    slug = (
        raw.get("slug")
        or raw.get("name")
        or function.get("name")
        or "Composio tool"
    )
    name = function.get("name") or raw.get("name") or slug
    return {"slug": str(slug), "name": str(name)}


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "akis-workflow", "version": "0.2.0"}


@api.post("/run")
async def run_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    goal = str(payload.get("goal", "")).strip()
    if not goal:
        return {"ok": False, "error": "goal is required"}

    composio_status = "not_checked"
    matched_tools: list[dict[str, str]] = []
    goal_lower = goal.lower()
    requested_tools: list[str] | None = None
    if any(term in goal_lower for term in ("gmail", "e-posta", "email")) and "slack" in goal_lower:
        requested_tools = ["GMAIL_FETCH_EMAILS", "SLACK_SEND_MESSAGE"]
    try:
        composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
        if requested_tools:
            tools = composio.tools.get("tpberg3tp", tools=requested_tools, limit=5)
        else:
            tools = composio.tools.get("tpberg3tp", search=goal, limit=5)
        matched_tools = [describe_tool(tool) for tool in tools]
        composio_status = "connected"
    except Exception:
        # Planning remains usable if a user has not connected an app yet.
        composio_status = "needs_connection"

    return {
        "ok": True,
        "status": "planned",
        "goal": goal,
        "task": {
            "name": "Müşteri e-postası özeti",
            "source": "Gmail gelen kutusu",
            "processing": "E-postaları seç, kısa ve anlaşılır özet çıkar",
            "destination": "Bağlı Slack çalışma alanı",
        },
        "integrations": {
            "composio": composio_status,
            "matched_tools": matched_tools,
        },
        "steps": [
            {
                "owner": "chatgpt",
                "action": "Görevi parçalara ayır ve gerekli araçları seç",
            },
            {
                "owner": "composio",
                "action": "Bağlı uygulamalarda güvenli işlem planı oluştur",
            },
            {
                "owner": "modal",
                "action": "İşi izole, ölçeklenebilir çalışma alanında yürüt",
            },
        ],
    }


@app.function(image=image, secrets=[modal.Secret.from_name("composio-akis")])
@modal.asgi_app()
def web() -> FastAPI:
    return api
