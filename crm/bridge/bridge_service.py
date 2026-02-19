"""
Robothor Bridge Service — Connects OpenClaw, Twenty CRM, Chatwoot, and Memory System.
FastAPI app on port 9100.
"""
import json
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

import config
import contact_resolver
import chatwoot_client
import twenty_client

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Robothor Bridge", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Check connectivity to all dependent services."""
    services = {}
    try:
        r = await http_client.get(f"{config.TWENTY_URL}/healthz")
        services["twenty"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
    except Exception as e:
        services["twenty"] = f"error:{e}"

    try:
        r = await http_client.get(f"{config.CHATWOOT_URL}/api")
        services["chatwoot"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
    except Exception as e:
        services["chatwoot"] = f"error:{e}"

    try:
        r = await http_client.get(f"{config.MEMORY_URL}/health")
        services["memory"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
    except Exception as e:
        services["memory"] = f"error:{e}"

    if config.IMPETUS_ONE_TOKEN:
        try:
            r = await http_client.get(f"{config.IMPETUS_ONE_URL}/healthz", timeout=5.0)
            services["impetus_one"] = "ok" if r.status_code == 200 else f"error:{r.status_code}"
        except Exception as e:
            services["impetus_one"] = f"error:{e}"

    all_ok = all(v == "ok" for v in services.values())
    return {"status": "ok" if all_ok else "degraded", "services": services}


@app.post("/resolve-contact")
async def resolve_contact(request: Request):
    """Resolve a channel identifier to cross-system contact IDs."""
    body = await request.json()
    channel = body.get("channel", "")
    identifier = body.get("identifier", "")
    name = body.get("name")

    if not channel or not identifier:
        return JSONResponse({"error": "channel and identifier required"}, status_code=400)

    result = await contact_resolver.resolve(channel, identifier, name, http_client)
    # Convert datetime fields to strings for JSON
    for k, v in result.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
    return result


@app.get("/timeline/{identifier}")
async def timeline(identifier: str):
    """Get unified timeline for a contact across all systems."""
    result = await contact_resolver.get_timeline(identifier, http_client)
    return result


@app.post("/webhooks/chatwoot")
async def webhook_chatwoot(request: Request):
    """Receive Chatwoot webhook events and ingest to memory system."""
    body = await request.json()
    event = body.get("event", "")

    if event == "message_created":
        content = body.get("content", {})
        message_text = content.get("content", "") if isinstance(content, dict) else str(content)
        sender = body.get("sender", {})
        conversation = body.get("conversation", {})

        # Ingest to memory system
        try:
            await http_client.post(f"{config.MEMORY_URL}/ingest", json={
                "channel": "chatwoot",
                "content": message_text,
                "metadata": {
                    "sender_name": sender.get("name", ""),
                    "sender_email": sender.get("email", ""),
                    "conversation_id": conversation.get("id"),
                    "event": event,
                },
            })
        except Exception:
            pass  # Don't fail webhook on memory ingestion error

    return {"status": "ok"}


@app.post("/webhooks/twenty")
async def webhook_twenty(request: Request):
    """Receive Twenty CRM webhook events."""
    body = await request.json()
    # Log for now; expand as needed
    return {"status": "ok", "event": body.get("event", "unknown")}


@app.post("/webhooks/openclaw")
async def webhook_openclaw(request: Request):
    """Receive OpenClaw message events, push to Chatwoot and resolve contacts."""
    body = await request.json()
    channel = body.get("channel", "unknown")
    identifier = body.get("identifier", "")
    name = body.get("name", "")
    content = body.get("content", "")
    direction = body.get("direction", "incoming")

    # Resolve contact across systems
    resolved = await contact_resolver.resolve(channel, identifier, name, http_client)

    # Push to Chatwoot if we have a contact
    chatwoot_contact_id = resolved.get("chatwoot_contact_id")
    if chatwoot_contact_id and content:
        # Find or create conversation
        convos = await chatwoot_client.get_conversations(chatwoot_contact_id, http_client)
        if convos:
            convo_id = convos[0].get("id")
        else:
            convo = await chatwoot_client.create_conversation(chatwoot_contact_id, client=http_client)
            convo_id = convo.get("id") if convo else None

        if convo_id:
            msg_type = "incoming" if direction == "incoming" else "outgoing"
            await chatwoot_client.send_message(convo_id, content, msg_type, client=http_client)

    return {"status": "ok", "resolved": {
        "twenty_person_id": resolved.get("twenty_person_id"),
        "chatwoot_contact_id": resolved.get("chatwoot_contact_id"),
    }}


@app.post("/log-interaction")
async def log_interaction(request: Request):
    """Log an interaction from the agent to CRM layer.
    Called by the log_interaction MCP tool."""
    body = await request.json()
    contact_name = body.get("contact_name", "")
    channel = body.get("channel", "api")
    direction = body.get("direction", "outgoing")
    content_summary = body.get("content_summary", "")
    channel_identifier = body.get("channel_identifier", contact_name)

    # Resolve contact
    resolved = await contact_resolver.resolve(channel, channel_identifier, contact_name, http_client)

    # Create Chatwoot conversation record
    chatwoot_contact_id = resolved.get("chatwoot_contact_id")
    if chatwoot_contact_id and content_summary:
        convos = await chatwoot_client.get_conversations(chatwoot_contact_id, http_client)
        if convos:
            convo_id = convos[0].get("id")
        else:
            convo = await chatwoot_client.create_conversation(chatwoot_contact_id, client=http_client)
            convo_id = convo.get("id") if convo else None

        if convo_id:
            msg_type = "incoming" if direction == "incoming" else "outgoing"
            await chatwoot_client.send_message(convo_id, content_summary, msg_type, client=http_client)

    return {"status": "ok", "contact": contact_name, "resolved": bool(resolved.get("twenty_person_id"))}


# ─── CRM Proxy Endpoints (for OpenClaw plugin) ───────────────────────────


@app.get("/api/conversations")
async def api_list_conversations(
    status: str = Query("open"),
    page: int = Query(1),
):
    """List Chatwoot conversations by status."""
    result = await chatwoot_client.list_conversations(status, page, client=http_client)
    return result


@app.get("/api/conversations/{conversation_id}")
async def api_get_conversation(conversation_id: int):
    """Get a single Chatwoot conversation."""
    result = await chatwoot_client.get_conversation(conversation_id, client=http_client)
    if not result:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return result


@app.get("/api/conversations/{conversation_id}/messages")
async def api_list_messages(conversation_id: int):
    """List messages in a Chatwoot conversation."""
    result = await chatwoot_client.list_messages(conversation_id, client=http_client)
    return {"payload": result}


@app.post("/api/conversations/{conversation_id}/messages")
async def api_create_message(conversation_id: int, request: Request):
    """Create a message in a Chatwoot conversation."""
    body = await request.json()
    content = body.get("content", "")
    message_type = body.get("message_type", "outgoing")
    private = body.get("private", False)

    if not content:
        return JSONResponse({"error": "content required"}, status_code=400)

    result = await chatwoot_client.send_message(
        conversation_id, content, message_type, client=http_client
    )
    return result or {"status": "ok"}


@app.post("/api/conversations/{conversation_id}/toggle_status")
async def api_toggle_conversation_status(conversation_id: int, request: Request):
    """Toggle conversation status (open, resolved, pending, snoozed)."""
    body = await request.json()
    status = body.get("status", "resolved")
    if status not in ("open", "resolved", "pending", "snoozed"):
        return JSONResponse({"error": "status must be open, resolved, pending, or snoozed"}, status_code=400)
    result = await chatwoot_client.toggle_conversation_status(
        conversation_id, status, client=http_client
    )
    if not result:
        return JSONResponse({"error": "failed to toggle status"}, status_code=500)
    return result


@app.get("/api/people")
async def api_list_people(
    search: Optional[str] = Query(None),
    limit: int = Query(20),
):
    """List or search people in Twenty CRM."""
    result = await twenty_client.list_people(search, limit, client=http_client)
    return {"people": result}


@app.post("/api/people")
async def api_create_person(request: Request):
    """Create a person in Twenty CRM."""
    body = await request.json()
    first_name = body.get("firstName", "")
    last_name = body.get("lastName", "")

    if not first_name:
        return JSONResponse({"error": "firstName required"}, status_code=400)

    email = body.get("email")
    phone = body.get("phone")

    person_id = await twenty_client.create_person(
        first_name, last_name, email, phone, client=http_client
    )
    if person_id:
        return {"id": person_id, "firstName": first_name, "lastName": last_name}
    return JSONResponse({"error": "failed to create person"}, status_code=500)


@app.post("/api/notes")
async def api_create_note(request: Request):
    """Create a note in Twenty CRM."""
    body = await request.json()
    title = body.get("title", "")
    note_body = body.get("body", "")

    if not title:
        return JSONResponse({"error": "title required"}, status_code=400)

    note_id = await twenty_client.create_note(title, note_body, client=http_client)
    if note_id:
        return {"id": note_id, "title": title}
    return JSONResponse({"error": "failed to create note"}, status_code=500)


# ─── Vault Endpoints ────────────────────────────────────────────────────

_vault_client = None

def _get_vault():
    """Lazy-init vault client."""
    global _vault_client
    if _vault_client is None:
        import sys
        sys.path.insert(0, os.path.expanduser("~/clawd/scripts"))
        from vault_client import VaultClient
        _vault_client = VaultClient()
        _vault_client.login()
    return _vault_client


@app.get("/api/vault/list")
async def api_vault_list():
    """List all vault items (names and usernames, no passwords)."""
    try:
        vc = _get_vault()
        items = vc.list_items()
        return {"items": items}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/vault/get")
async def api_vault_get(name: str = Query(..., description="Item name (partial match)")):
    """Get a vault item by name, fully decrypted."""
    try:
        vc = _get_vault()
        item = vc.get_item(name)
        if item:
            return item
        return JSONResponse({"error": f"No item matching '{name}'"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/vault/search")
async def api_vault_search(q: str = Query(..., description="Search query")):
    """Search vault items by name."""
    try:
        vc = _get_vault()
        items = vc.search(q)
        return {"items": items}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/vault/create")
async def api_vault_create(request: Request):
    """Create a new login item in the vault."""
    body = await request.json()
    name = body.get("name")
    username = body.get("username")
    password = body.get("password")
    if not name or not username or not password:
        return JSONResponse({"error": "name, username, and password required"}, status_code=400)
    try:
        vc = _get_vault()
        item = vc.create_login(
            name=name, username=username, password=password,
            uri=body.get("uri"), notes=body.get("notes"),
        )
        return item
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/vault/create_card")
async def api_vault_create_card(request: Request):
    """Create a new card item in the vault."""
    body = await request.json()
    name = body.get("name")
    cardholder = body.get("cardholderName")
    number = body.get("number")
    exp_month = body.get("expMonth")
    exp_year = body.get("expYear")
    if not name or not number or not exp_month or not exp_year:
        return JSONResponse(
            {"error": "name, number, expMonth, and expYear required"}, status_code=400
        )
    try:
        vc = _get_vault()
        item = vc.create_card(
            name=name, cardholderName=cardholder or "",
            number=number, expMonth=exp_month, expYear=exp_year,
            code=body.get("code"), brand=body.get("brand"),
            notes=body.get("notes"),
        )
        return item
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Impetus One Proxy Endpoints ───────────────────────────────────────

async def _io_get(path: str, params: dict | None = None) -> dict:
    """Proxy GET to Impetus One API."""
    headers = {"Authorization": f"Bearer {config.IMPETUS_ONE_TOKEN}"}
    r = await http_client.get(f"{config.IMPETUS_ONE_URL}{path}", headers=headers, params=params)
    r.raise_for_status()
    return r.json()


async def _io_post(path: str, body: dict) -> dict:
    """Proxy POST to Impetus One API."""
    headers = {
        "Authorization": f"Bearer {config.IMPETUS_ONE_TOKEN}",
        "Content-Type": "application/json",
    }
    r = await http_client.post(f"{config.IMPETUS_ONE_URL}{path}", headers=headers, json=body)
    r.raise_for_status()
    return r.json()


@app.get("/api/impetus/health")
async def api_impetus_health():
    """Check Impetus One service health."""
    try:
        r = await http_client.get(f"{config.IMPETUS_ONE_URL}/healthz", timeout=5.0)
        return {"status": "ok" if r.status_code == 200 else "error", "http_code": r.status_code}
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=503)


@app.get("/api/impetus/patients")
async def api_impetus_patients(
    search: Optional[str] = Query(None),
    firstName: Optional[str] = Query(None),
    lastName: Optional[str] = Query(None),
):
    """List/search patients in Impetus One."""
    try:
        params = {}
        if firstName:
            params["firstName"] = firstName
        if lastName:
            params["lastName"] = lastName
        if search:
            params["lastName"] = search
        data = await _io_get("/api/patients", params or None)
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/patients/{patient_id}")
async def api_impetus_patient(patient_id: str):
    """Get a single patient by ID."""
    try:
        data = await _io_get(f"/api/patients/{patient_id}")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/prescriptions")
async def api_impetus_prescriptions(
    status: Optional[str] = Query(None),
):
    """List prescriptions, optionally filtered by status."""
    try:
        params = {}
        if status:
            params["status"] = status
        data = await _io_get("/api/prescriptions", params or None)
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/prescriptions/{rx_id}")
async def api_impetus_prescription(rx_id: str):
    """Get a single prescription by ID."""
    try:
        data = await _io_get(f"/api/prescriptions/{rx_id}")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/appointments")
async def api_impetus_appointments():
    """List appointments."""
    try:
        data = await _io_get("/api/appointments")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/queue")
async def api_impetus_queue():
    """List provider review queue items."""
    try:
        data = await _io_get("/api/queue_items")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/medications")
async def api_impetus_medications():
    """List medications."""
    try:
        data = await _io_get("/api/medications")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/pharmacies")
async def api_impetus_pharmacies():
    """List pharmacies."""
    try:
        data = await _io_get("/api/pharmacies")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/orders")
async def api_impetus_orders():
    """List e-commerce orders."""
    try:
        data = await _io_get("/api/ecommerce/orders")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/impetus/encounters")
async def api_impetus_encounters():
    """List patient encounters/chart notes."""
    try:
        data = await _io_get("/api/encounters")
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/impetus/graphql")
async def api_impetus_graphql(request: Request):
    """GraphQL passthrough to Impetus One."""
    try:
        body = await request.json()
        data = await _io_post("/api/graphql", body)
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ─── Impetus One MCP Client (for write operations with scribe delegation) ──


class ImpetusMCPClient:
    """JSON-RPC client for Impetus One MCP HTTP endpoint.

    Write operations (prescriptions, transmit) require scribe delegation context
    that only the MCP layer handles. This client maintains a session with the
    Impetus MCP server at /_mcp.
    """

    def __init__(self):
        self.session_id: str | None = None
        self._initialized = False
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send(self, message: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.IMPETUS_ONE_TOKEN}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        r = await http_client.post(
            f"{config.IMPETUS_ONE_URL}/_mcp",
            headers=headers,
            json=message,
            timeout=30.0,
        )

        if session_id := r.headers.get("Mcp-Session-Id"):
            self.session_id = session_id

        # Handle non-JSON responses (e.g. 405, SSE streams)
        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type or "text/json" in content_type:
            return r.json()
        # For SSE or other formats, try to parse as JSON anyway
        text = r.text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {"error": f"Unexpected response ({r.status_code}): {text[:200]}"}

    async def ensure_initialized(self):
        if self._initialized:
            return

        result = await self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "robothor-bridge", "version": "1.0.0"},
            },
        })

        # Send initialized notification (no response expected)
        await self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        self._initialized = True

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call an MCP tool and return the parsed result."""
        await self.ensure_initialized()

        result = await self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {},
            },
        })

        if "error" in result:
            err = result["error"]
            return {"error": err.get("message", str(err)) if isinstance(err, dict) else str(err)}

        # MCP tool results have content array with text items
        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except (json.JSONDecodeError, KeyError):
                return {"text": content[0].get("text", "")}

        return result.get("result", {})

    def reset(self):
        """Reset session state on connection errors."""
        self.session_id = None
        self._initialized = False


_impetus_mcp: ImpetusMCPClient | None = None


def _get_impetus_mcp() -> ImpetusMCPClient:
    global _impetus_mcp
    if _impetus_mcp is None:
        _impetus_mcp = ImpetusMCPClient()
    return _impetus_mcp


@app.get("/api/impetus/providers")
async def api_impetus_providers():
    """List providers RoboThor can act as via scribe delegation."""
    try:
        mcp = _get_impetus_mcp()
        return await mcp.call_tool("list_actable_providers")
    except Exception as e:
        _get_impetus_mcp().reset()
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/impetus/prescriptions/draft")
async def api_impetus_create_draft(request: Request):
    """Create a prescription draft via MCP (supports scribe delegation).

    Body: {patientId, medicationId, directions, quantity, daysSupply,
           refills?, notes?, actingAsProviderId?}
    """
    try:
        body = await request.json()
        mcp = _get_impetus_mcp()
        return await mcp.call_tool("create_prescription_draft", body)
    except Exception as e:
        _get_impetus_mcp().reset()
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/impetus/prescriptions/{rx_id}/transmit")
async def api_impetus_transmit(rx_id: str, request: Request):
    """Transmit a prescription to pharmacy via MCP.

    Two-step flow:
    1. First call (no confirmationId): creates pending confirmation
    2. Second call (with confirmationId): executes after human approval

    Body: {actingAsProviderId?, confirmationId?}
    """
    try:
        body = await request.json()
        body["prescriptionId"] = rx_id
        mcp = _get_impetus_mcp()
        return await mcp.call_tool("transmit_prescription", body)
    except Exception as e:
        _get_impetus_mcp().reset()
        return JSONResponse({"error": str(e)}, status_code=502)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9100)
