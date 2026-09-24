"""Modal runtime for the Akış MVP."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

import modal
from composio import Composio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import PlainTextResponse


image = modal.Image.debian_slim().uv_pip_install("fastapi[standard]", "composio", "mcp")
app = modal.App(name="akis-workflow")

agent_mcp = MCPServer(
    "Akis Agent Gateway",
    instructions=(
        "Use Akis to claim a pending task, read shared project context, "
        "and submit your result back to the shared control plane."
    ),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with agent_mcp.session_manager.run():
        yield


api = FastAPI(title="Akış Workflow API", version="0.4.0", lifespan=lifespan)

CONTROL_PLANE_STATE = modal.Dict.from_name("akis-control-plane-v1", create_if_missing=True)


async def load_state_list(key: str) -> list[dict[str, Any]]:
    value = await CONTROL_PLANE_STATE.get.aio(key, [])
    return value if isinstance(value, list) else []


async def prepend_state(key: str, item: dict[str, Any], limit: int = 100) -> None:
    items = await load_state_list(key)
    await CONTROL_PLANE_STATE.put.aio(key, [item, *items][:limit])


def risk_for_tool(slug: str) -> str:
    name = slug.upper()
    if any(term in name for term in ("DELETE", "REMOVE", "REVOKE", "DROP")):
        return "blocked"
    if any(term in name for term in ("SEND", "CREATE", "UPDATE", "PUSH", "DEPLOY")):
        return "approval_required"
    return "allow"


def normalize_result(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return {"type": type(value).__name__, "text": str(value)[:2000]}


async def execute_tool(tool_slug: str, arguments: dict[str, Any], user_id: str) -> Any:
    def _execute() -> Any:
        composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
        return composio.tools.execute(
            tool_slug,
            arguments=arguments,
            user_id=user_id,
            dangerously_skip_version_check=True,
        )

    return normalize_result(await asyncio.to_thread(_execute))


class BearerAuthMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            expected = os.environ.get("AKIS_AGENT_TOKEN", "").strip()
            if not expected:
                response = PlainTextResponse("Akis MCP authentication is not configured", status_code=503)
                await response(scope, receive, send)
                return
            if headers.get("authorization") != f"Bearer {expected}":
                response = PlainTextResponse("Unauthorized", status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def save_runs(runs: list[dict[str, Any]]) -> None:
    await CONTROL_PLANE_STATE.put.aio("runs", runs)


@agent_mcp.tool()
async def akis_claim_task(agent: str) -> dict[str, Any]:
    """Claim the oldest available Akis task for this agent."""
    agent_name = agent.strip().lower()
    if not agent_name:
        return {"ok": False, "error": "agent is required"}

    runs = await load_state_list("runs")
    candidates = [
        run
        for run in reversed(runs)
        if run.get("kind") != "tool_execution"
        and run.get("status") in {"planned", "approved"}
        and not run.get("assigned_agent")
    ]
    if not candidates:
        return {"ok": True, "status": "idle", "task": None}

    target = candidates[0]
    target["assigned_agent"] = agent_name
    target["status"] = "assigned"
    target["assigned_at"] = datetime.now(timezone.utc).isoformat()
    target.setdefault("receipts", []).append(
        receipt(str(target["id"]), "agent_claimed", agent_name)
    )
    await save_runs(runs)
    return {
        "ok": True,
        "status": "assigned",
        "task": {
            "run_id": target["id"],
            "goal": target.get("goal"),
            "assigned_agent": agent_name,
        },
    }


@agent_mcp.tool()
async def akis_get_context(agent: str, limit: int = 20) -> dict[str, Any]:
    """Return shared project memory and work assigned to this agent."""
    safe_limit = max(1, min(int(limit), 50))
    agent_name = agent.strip().lower()
    runs = await load_state_list("runs")
    memory = await load_state_list("memory")
    assigned = [
        run
        for run in runs
        if run.get("assigned_agent") == agent_name
        and run.get("status") in {"assigned", "in_progress"}
    ]
    return {
        "ok": True,
        "agent": agent_name,
        "memory": memory[:safe_limit],
        "assigned_runs": assigned[:safe_limit],
    }


@agent_mcp.tool()
async def akis_submit_result(
    run_id: str,
    agent: str,
    summary: str,
    status: str = "completed",
) -> dict[str, Any]:
    """Submit an agent result into Akis memory and close the assigned task."""
    normalized_status = status.strip().lower()
    if normalized_status not in {"completed", "failed"}:
        return {"ok": False, "error": "status must be completed or failed"}

    agent_name = agent.strip().lower()
    runs = await load_state_list("runs")
    target = next((run for run in runs if str(run.get("id")) == run_id), None)
    if target is None:
        return {"ok": False, "error": "run not found"}
    if target.get("assigned_agent") != agent_name:
        return {"ok": False, "error": "run is assigned to another agent"}

    safe_summary = summary.strip()[:5000]
    target["status"] = normalized_status
    target["completed_at"] = datetime.now(timezone.utc).isoformat()
    target["result_summary"] = safe_summary
    target.setdefault("receipts", []).append(
        receipt(run_id, f"agent_{normalized_status}", agent_name)
    )
    await save_runs(runs)

    memory_item = {
        "id": str(uuid4()),
        "kind": "agent_result",
        "agent": agent_name,
        "run_id": run_id,
        "content": safe_summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await prepend_state("memory", memory_item)
    return {"ok": True, "run_id": run_id, "status": normalized_status}


def receipt(run_id: str, event: str, detail: str) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{run_id}:{timestamp}:{event}:{detail}".encode()).hexdigest()[:16]
    return {"id": digest, "timestamp": timestamp, "event": event, "detail": detail}
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
    return {"status": "ok", "service": "akis-workflow", "version": "0.4.0", "capabilities": "control-plane-v1,mcp-agent-gateway"}


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

    run_id = str(uuid4())
    policies = [{"tool": tool["slug"], "decision": risk_for_tool(tool["slug"])} for tool in matched_tools]
    receipts = [receipt(run_id, "goal_received", goal), receipt(run_id, "plan_created", f"{len(matched_tools)} tool(s) matched")]
    memory = {"id": str(uuid4()), "kind": "goal", "content": goal, "created_at": datetime.now(timezone.utc).isoformat()}
    requires_approval = any(policy["decision"] == "approval_required" for policy in policies)
    run_status = "awaiting_approval" if requires_approval else "planned"
    run_record = {
        "id": run_id,
        "goal": goal,
        "status": run_status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policies": policies,
        "receipts": receipts,
    }
    await prepend_state("memory", memory)
    await prepend_state("runs", run_record)

    return {
        "ok": True,
        "run_id": run_id,
        "status": run_status,
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
        "control_plane": {
            "agent_gateway": ["chatgpt", "codex", "claude", "cursor"],
            "policies": policies,
            "receipts": receipts,
            "memory": memory,
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


@api.post("/tools/execute")
async def tool_gateway(payload: dict[str, Any]) -> dict[str, Any]:
    tool_slug = str(payload.get("tool", "")).strip().upper()
    arguments = payload.get("arguments", {})
    user_id = str(payload.get("user_id", "tpberg3tp")).strip() or "tpberg3tp"
    if not tool_slug:
        return {"ok": False, "error": "tool is required"}
    if not isinstance(arguments, dict):
        return {"ok": False, "error": "arguments must be an object"}

    run_id = str(uuid4())
    decision = risk_for_tool(tool_slug)
    receipts = [receipt(run_id, "tool_requested", tool_slug)]

    if decision == "blocked":
        run_record = {
            "id": run_id,
            "kind": "tool_execution",
            "tool": tool_slug,
            "status": "blocked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": decision,
            "receipts": [*receipts, receipt(run_id, "policy_blocked", tool_slug)],
        }
        await prepend_state("runs", run_record)
        return {"ok": False, "run_id": run_id, "status": "blocked", "policy": decision}

    if decision == "approval_required":
        run_record = {
            "id": run_id,
            "kind": "tool_execution",
            "tool": tool_slug,
            "arguments": arguments,
            "user_id": user_id,
            "status": "awaiting_approval",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": decision,
            "receipts": [*receipts, receipt(run_id, "approval_required", tool_slug)],
        }
        await prepend_state("runs", run_record)
        return {
            "ok": True,
            "run_id": run_id,
            "status": "awaiting_approval",
            "policy": decision,
        }

    try:
        result = await execute_tool(tool_slug, arguments, user_id)
    except Exception as error:
        run_record = {
            "id": run_id,
            "kind": "tool_execution",
            "tool": tool_slug,
            "status": "failed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "policy": decision,
            "receipts": [*receipts, receipt(run_id, "execution_failed", type(error).__name__)],
        }
        await prepend_state("runs", run_record)
        return {"ok": False, "run_id": run_id, "status": "failed", "error": str(error)}

    run_record = {
        "id": run_id,
        "kind": "tool_execution",
        "tool": tool_slug,
        "status": "executed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": decision,
        "receipts": [*receipts, receipt(run_id, "executed", tool_slug)],
    }
    await prepend_state("runs", run_record)
    return {"ok": True, "run_id": run_id, "status": "executed", "result": result}


@api.post("/approvals/{run_id}")
async def decide_approval(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in {"approve", "reject"}:
        return {"ok": False, "error": "decision must be approve or reject"}

    runs = await load_state_list("runs")
    target = next((run for run in runs if run.get("id") == run_id), None)
    if target is None:
        return {"ok": False, "error": "run not found"}
    if target.get("status") != "awaiting_approval":
        return {"ok": False, "error": "run is not awaiting approval", "status": target.get("status")}

    target["approval"] = {
        "decision": decision,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    target.setdefault("receipts", []).append(
        receipt(run_id, f"approval_{decision}", f"Run {decision}d by user")
    )

    if decision == "reject":
        target["status"] = "rejected"
        await CONTROL_PLANE_STATE.put.aio("runs", runs)
        return {"ok": True, "run": target}

    if target.get("kind") == "tool_execution":
        try:
            result = await execute_tool(
                str(target["tool"]),
                target.get("arguments", {}),
                str(target.get("user_id", "tpberg3tp")),
            )
        except Exception as error:
            target["status"] = "failed"
            target.setdefault("receipts", []).append(
                receipt(run_id, "execution_failed", type(error).__name__)
            )
            await CONTROL_PLANE_STATE.put.aio("runs", runs)
            return {"ok": False, "run": target, "error": str(error)}

        target["status"] = "executed"
        target.setdefault("receipts", []).append(
            receipt(run_id, "executed_after_approval", str(target["tool"]))
        )
        await CONTROL_PLANE_STATE.put.aio("runs", runs)
        return {"ok": True, "run": target, "result": result}

    target["status"] = "approved"
    await CONTROL_PLANE_STATE.put.aio("runs", runs)
    return {"ok": True, "run": target}


@api.get("/control-plane")
async def control_plane() -> dict[str, Any]:
    runs = await load_state_list("runs")
    memory = await load_state_list("memory")
    return {
        "ok": True,
        "storage": "modal.Dict:akis-control-plane-v1",
        "agents": ["chatgpt", "codex", "claude", "cursor"],
        "runs": runs[:20],
        "memory": memory[:20],
        "policy": {"read": "allow", "write": "approval_required", "destructive": "blocked"},
    }


mcp_security = TransportSecuritySettings(
    allowed_hosts=[
        "tpberg3tp--akis-workflow-web.modal.run",
        "tpberg3tp--akis-workflow-web.modal.run:*",
        "127.0.0.1:*",
        "localhost:*",
    ],
    allowed_origins=[
        "https://atpsec.github.io",
        "http://127.0.0.1:*",
        "http://localhost:*",
    ],
)
mcp_http_app = agent_mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=mcp_security,
)
api.mount("/agent", BearerAuthMiddleware(mcp_http_app))


@app.function(image=image, secrets=[modal.Secret.from_name("composio-akis")])
@modal.asgi_app()
def web() -> FastAPI:
    return api
