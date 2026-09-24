# Akış Agent Gateway

Akış exposes a remote MCP endpoint for external coding agents.

## Endpoint

`https://tpberg3tp--akis-workflow-web.modal.run/agent/mcp`

Transport: Streamable HTTP.

Authentication: Bearer token from `AKIS_AGENT_TOKEN`. The token must exist in the Modal secret used by the Akış web function. The value itself must never be committed.

## MCP tools

- `akis_claim_task(agent)`: claims the oldest available approved/planned workflow for an agent.
- `akis_get_context(agent, limit=20)`: returns shared project memory and work currently assigned to that agent.
- `akis_submit_result(run_id, agent, summary, status="completed")`: stores the result in shared memory, updates the run, and appends an audit receipt.

## Codex

Store the token in your environment:

```powershell
$env:AKIS_AGENT_TOKEN = "<secret>"
```

Then add this to `~/.codex/config.toml`:

```toml
[mcp_servers.akis]
url = "https://tpberg3tp--akis-workflow-web.modal.run/agent/mcp"
bearer_token_env_var = "AKIS_AGENT_TOKEN"
required = true
```

A useful project instruction is:

```text
When Akış MCP is available, call akis_get_context before starting relevant project work.
Claim a task with akis_claim_task only when you intend to perform it.
When finished, call akis_submit_result with a concise factual summary and status.
```

## Claude Code

```powershell
claude mcp add --transport http --scope user akis https://tpberg3tp--akis-workflow-web.modal.run/agent/mcp --header "Authorization: Bearer $env:AKIS_AGENT_TOKEN"
```

Then verify with:

```powershell
claude mcp list
```

## Security behavior

- Missing server token configuration: HTTP 503.
- Missing or invalid Bearer token: HTTP 401.
- MCP only exposes task/context/result coordination. Destructive application actions still pass through Akış policy and approval paths.
- Result summaries are capped at 5000 characters before persistence.

## Current limitation

The endpoint is code-complete on the feature branch but is not reachable until this branch is deployed to Modal with `AKIS_AGENT_TOKEN` configured in the deployment secret.
