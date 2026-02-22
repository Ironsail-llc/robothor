"""
Tests for task coordination system — agent-to-agent task routing.

Tests cover:
- Bridge API endpoints (POST, PATCH, GET agent/, resolve)
- DAL extensions (create_task, update_task, list_tasks, list_agent_tasks, resolve_task)
- New fields (priority, tags, assigned_to_agent, etc.)
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── Bridge API Tests (mocked DAL) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_basic(test_client):
    """POST /api/tasks creates a task with agent coordination fields."""
    task_id = str(uuid.uuid4())
    with patch("routers.notes_tasks.create_task", return_value=task_id) as mock_create:
        with patch("routers.notes_tasks.publish"):
            r = await test_client.post("/api/tasks", json={
                "title": "Reply to sender",
                "assignedToAgent": "email-responder",
                "priority": "high",
                "tags": ["email", "reply-needed"],
            })
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == task_id
    assert data["title"] == "Reply to sender"
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["assigned_to_agent"] == "email-responder"
    assert call_kwargs.kwargs["priority"] == "high"
    assert call_kwargs.kwargs["tags"] == ["email", "reply-needed"]


@pytest.mark.asyncio
async def test_create_task_auto_created_by_agent(test_client):
    """POST /api/tasks auto-populates created_by_agent from X-Agent-Id header."""
    task_id = str(uuid.uuid4())
    with patch("routers.notes_tasks.create_task", return_value=task_id) as mock_create:
        with patch("routers.notes_tasks.publish"):
            r = await test_client.post(
                "/api/tasks",
                json={"title": "Test task"},
                headers={"X-Agent-Id": "email-classifier"},
            )
    assert r.status_code == 200
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["created_by_agent"] == "email-classifier"


@pytest.mark.asyncio
async def test_create_task_missing_title(test_client):
    """POST /api/tasks with empty title returns 400."""
    r = await test_client.post("/api/tasks", json={"title": ""})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_update_task(test_client):
    """PATCH /api/tasks/{id} updates task fields."""
    with patch("routers.notes_tasks.update_task", return_value=True):
        with patch("routers.notes_tasks.publish"):
            r = await test_client.patch(
                f"/api/tasks/{uuid.uuid4()}",
                json={"status": "IN_PROGRESS", "priority": "urgent"},
            )
    assert r.status_code == 200
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_update_task_auto_resolved_at(test_client):
    """PATCH /api/tasks/{id} with status=DONE auto-sets resolved_at."""
    with patch("routers.notes_tasks.update_task", return_value=True) as mock_update:
        with patch("routers.notes_tasks.publish"):
            r = await test_client.patch(
                f"/api/tasks/{uuid.uuid4()}",
                json={"status": "DONE"},
            )
    assert r.status_code == 200
    call_kwargs = mock_update.call_args
    assert "resolved_at" in call_kwargs.kwargs


@pytest.mark.asyncio
async def test_update_task_not_found(test_client):
    """PATCH /api/tasks/{id} returns 404 when task doesn't exist."""
    with patch("routers.notes_tasks.update_task", return_value=False):
        with patch("routers.notes_tasks.publish"):
            r = await test_client.patch(
                f"/api/tasks/{uuid.uuid4()}",
                json={"status": "IN_PROGRESS"},
            )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_agent_tasks(test_client):
    """GET /api/tasks/agent/{agent_id} returns priority-ordered tasks."""
    mock_tasks = [
        {"id": str(uuid.uuid4()), "title": "Urgent task", "priority": "urgent",
         "status": "TODO", "tags": ["email"]},
        {"id": str(uuid.uuid4()), "title": "Normal task", "priority": "normal",
         "status": "TODO", "tags": []},
    ]
    with patch("routers.notes_tasks.list_agent_tasks", return_value=mock_tasks):
        r = await test_client.get("/api/tasks/agent/email-responder")
    assert r.status_code == 200
    data = r.json()
    assert len(data["tasks"]) == 2


@pytest.mark.asyncio
async def test_resolve_task(test_client):
    """POST /api/tasks/{id}/resolve marks task as DONE with resolution."""
    with patch("routers.notes_tasks.resolve_task", return_value=True):
        with patch("routers.notes_tasks.publish"):
            r = await test_client.post(
                f"/api/tasks/{uuid.uuid4()}/resolve",
                json={"resolution": "Sent reply to sender about meeting"},
            )
    assert r.status_code == 200
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_resolve_task_missing_resolution(test_client):
    """POST /api/tasks/{id}/resolve without resolution returns 400."""
    r = await test_client.post(
        f"/api/tasks/{uuid.uuid4()}/resolve",
        json={},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_resolve_task_not_found(test_client):
    """POST /api/tasks/{id}/resolve returns 404 when task doesn't exist."""
    with patch("routers.notes_tasks.resolve_task", return_value=False):
        with patch("routers.notes_tasks.publish"):
            r = await test_client.post(
                f"/api/tasks/{uuid.uuid4()}/resolve",
                json={"resolution": "done"},
            )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks_with_filters(test_client):
    """GET /api/tasks with agent/tag/priority filters."""
    with patch("routers.notes_tasks.list_tasks", return_value=[]) as mock_list:
        r = await test_client.get(
            "/api/tasks",
            params={
                "assignedToAgent": "email-responder",
                "tags": "email,reply-needed",
                "priority": "high",
                "excludeResolved": "true",
            },
        )
    assert r.status_code == 200
    call_kwargs = mock_list.call_args
    assert call_kwargs.kwargs["assigned_to_agent"] == "email-responder"
    assert call_kwargs.kwargs["tags"] == ["email", "reply-needed"]
    assert call_kwargs.kwargs["priority"] == "high"
    assert call_kwargs.kwargs["exclude_resolved"] is True


@pytest.mark.asyncio
async def test_create_task_emits_event(test_client):
    """POST /api/tasks emits a task.created event to the agent stream."""
    task_id = str(uuid.uuid4())
    with patch("routers.notes_tasks.create_task", return_value=task_id):
        with patch("routers.notes_tasks.publish") as mock_publish:
            r = await test_client.post("/api/tasks", json={
                "title": "Test event",
                "assignedToAgent": "supervisor",
                "priority": "high",
                "tags": ["escalation"],
            })
    assert r.status_code == 200
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args
    assert call_args[0][0] == "agent"
    assert call_args[0][1] == "task.created"
    assert call_args[0][2]["task_id"] == task_id


# ─── Pydantic Model Tests ───────────────────────────────────────────────


def test_create_task_request_defaults():
    """CreateTaskRequest has sensible defaults."""
    from models import CreateTaskRequest
    req = CreateTaskRequest(title="Test")
    assert req.status == "TODO"
    assert req.priority == "normal"
    assert req.tags is None
    assert req.assignedToAgent is None


def test_update_task_request_all_none():
    """UpdateTaskRequest with no fields is valid (all optional)."""
    from models import UpdateTaskRequest
    req = UpdateTaskRequest()
    assert req.title is None
    assert req.status is None
    assert req.priority is None


# ─── task_to_dict Tests ─────────────────────────────────────────────────


def test_task_to_dict_new_fields():
    """task_to_dict includes all coordination fields."""
    from robothor.crm.models import task_to_dict
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    row = {
        "id": uuid.uuid4(),
        "title": "Test task",
        "body": "body text",
        "status": "IN_PROGRESS",
        "due_at": now,
        "person_id": None,
        "company_id": None,
        "created_by_agent": "email-classifier",
        "assigned_to_agent": "email-responder",
        "priority": "high",
        "tags": ["email", "reply-needed"],
        "parent_task_id": None,
        "resolved_at": None,
        "resolution": None,
        "updated_at": now,
        "created_at": now,
    }
    result = task_to_dict(row)
    assert result["createdByAgent"] == "email-classifier"
    assert result["assignedToAgent"] == "email-responder"
    assert result["priority"] == "high"
    assert result["tags"] == ["email", "reply-needed"]
    assert result["parentTaskId"] is None
    assert result["resolvedAt"] is None
    assert result["resolution"] == ""


def test_task_to_dict_backward_compatible():
    """task_to_dict works when new columns are missing (e.g. old rows)."""
    from robothor.crm.models import task_to_dict
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    row = {
        "id": uuid.uuid4(),
        "title": "Old task",
        "body": None,
        "status": "TODO",
        "due_at": None,
        "person_id": None,
        "company_id": None,
        "updated_at": now,
        "created_at": now,
    }
    result = task_to_dict(row)
    assert result["createdByAgent"] == ""
    assert result["assignedToAgent"] == ""
    assert result["priority"] == "normal"
    assert result["tags"] == []
    assert result["parentTaskId"] is None
    assert result["resolvedAt"] is None
    assert result["resolution"] == ""
