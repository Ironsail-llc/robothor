"""Notes & Tasks routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from robothor.crm.dal import (
    create_note,
    create_task,
    delete_note,
    delete_task,
    get_note,
    get_task,
    list_agent_tasks,
    list_notes,
    list_tasks,
    resolve_task,
    update_task,
)
from robothor.events.bus import publish

from models import CreateNoteRequest, CreateTaskRequest, UpdateTaskRequest

router = APIRouter(prefix="/api", tags=["notes", "tasks"])


# ─── Notes ───────────────────────────────────────────────────────────────


@router.get("/notes")
async def api_list_notes(
    personId: str | None = Query(None),
    companyId: str | None = Query(None),
    limit: int = Query(50),
):
    return {"notes": list_notes(personId, companyId, limit)}


@router.post("/notes")
async def api_create_note(body: CreateNoteRequest):
    if not body.title:
        return JSONResponse({"error": "title required"}, status_code=400)
    note_id = create_note(body.title, body.body, body.personId, body.companyId)
    if note_id:
        return {"id": note_id, "title": body.title}
    return JSONResponse({"error": "failed to create note"}, status_code=500)


@router.get("/notes/{note_id}")
async def api_get_note(note_id: str):
    result = get_note(note_id)
    if not result:
        return JSONResponse({"error": "note not found"}, status_code=404)
    return result


@router.delete("/notes/{note_id}")
async def api_delete_note(note_id: str):
    if delete_note(note_id):
        return {"success": True, "id": note_id}
    return JSONResponse({"error": "note not found"}, status_code=404)


# ─── Tasks ───────────────────────────────────────────────────────────────


@router.get("/tasks")
async def api_list_tasks(
    status: str | None = Query(None),
    personId: str | None = Query(None),
    assignedToAgent: str | None = Query(None),
    createdByAgent: str | None = Query(None),
    tags: str | None = Query(None),
    priority: str | None = Query(None),
    excludeResolved: bool = Query(False),
    limit: int = Query(50),
):
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    return {
        "tasks": list_tasks(
            status=status,
            person_id=personId,
            limit=limit,
            assigned_to_agent=assignedToAgent,
            created_by_agent=createdByAgent,
            tags=tag_list,
            priority=priority,
            exclude_resolved=excludeResolved,
        )
    }


@router.post("/tasks")
async def api_create_task(
    body: CreateTaskRequest,
    x_agent_id: str | None = Header(None, alias="X-Agent-Id"),
):
    if not body.title:
        return JSONResponse({"error": "title required"}, status_code=400)
    # Auto-populate created_by_agent from X-Agent-Id header
    agent_id = x_agent_id
    task_id = create_task(
        title=body.title,
        body=body.body,
        status=body.status,
        due_at=body.dueAt,
        person_id=body.personId,
        company_id=body.companyId,
        created_by_agent=agent_id,
        assigned_to_agent=body.assignedToAgent,
        priority=body.priority,
        tags=body.tags,
        parent_task_id=body.parentTaskId,
    )
    if task_id:
        publish("agent", "task.created", {
            "task_id": task_id, "title": body.title,
            "assigned_to_agent": body.assignedToAgent,
            "created_by_agent": agent_id,
            "priority": body.priority,
            "tags": body.tags or [],
        }, source="bridge")
        return {"id": task_id, "title": body.title}
    return JSONResponse({"error": "failed to create task"}, status_code=500)


@router.get("/tasks/agent/{agent_id}")
async def api_list_agent_tasks(
    agent_id: str,
    status: str | None = Query(None),
    includeUnassigned: bool = Query(False),
    limit: int = Query(50),
):
    return {
        "tasks": list_agent_tasks(
            agent_id=agent_id,
            include_unassigned=includeUnassigned,
            status=status,
            limit=limit,
        )
    }


@router.get("/tasks/{task_id}")
async def api_get_task(task_id: str):
    result = get_task(task_id)
    if not result:
        return JSONResponse({"error": "task not found"}, status_code=404)
    return result


@router.patch("/tasks/{task_id}")
async def api_update_task(
    task_id: str,
    body: UpdateTaskRequest,
    x_agent_id: str | None = Header(None, alias="X-Agent-Id"),
):
    kwargs = {}
    field_map = {
        "title": "title", "body": "body", "status": "status",
        "dueAt": "due_at", "personId": "person_id", "companyId": "company_id",
        "assignedToAgent": "assigned_to_agent", "priority": "priority",
        "tags": "tags", "parentTaskId": "parent_task_id",
        "resolution": "resolution",
    }
    for api_key, dal_key in field_map.items():
        val = getattr(body, api_key, None)
        if val is not None:
            kwargs[dal_key] = val
    # Auto-set resolved_at when status changes to DONE
    if body.status and body.status.upper() == "DONE":
        from datetime import datetime, timezone
        kwargs["resolved_at"] = datetime.now(timezone.utc).isoformat()
    ok = update_task(task_id, **kwargs)
    if ok:
        publish("agent", "task.updated", {
            "task_id": task_id, "fields": list(kwargs.keys()),
            "agent_id": x_agent_id,
        }, source="bridge")
        return {"success": True, "id": task_id}
    return JSONResponse({"error": "task not found"}, status_code=404)


@router.post("/tasks/{task_id}/resolve")
async def api_resolve_task(
    task_id: str,
    body: dict,
    x_agent_id: str | None = Header(None, alias="X-Agent-Id"),
):
    resolution = body.get("resolution", "")
    if not resolution:
        return JSONResponse({"error": "resolution required"}, status_code=400)
    ok = resolve_task(task_id, resolution, agent_id=x_agent_id)
    if ok:
        publish("agent", "task.resolved", {
            "task_id": task_id, "resolution": resolution,
            "agent_id": x_agent_id,
        }, source="bridge")
        return {"success": True, "id": task_id}
    return JSONResponse({"error": "task not found"}, status_code=404)


@router.delete("/tasks/{task_id}")
async def api_delete_task(task_id: str):
    if delete_task(task_id):
        return {"success": True, "id": task_id}
    return JSONResponse({"error": "task not found"}, status_code=404)
