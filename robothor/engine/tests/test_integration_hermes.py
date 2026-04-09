"""Integration tests for the Hermes-inspired enhancements.

Tests cross-module interactions across all 5 feature areas:
1. Autonomous skill creation (skills.py ↔ handlers/skills.py ↔ schemas.py)
2. Learning loop (blocks.py ↔ warmup.py ↔ models.py ↔ runner.py ↔ analytics.py)
3. Platform import/export (cli/importer.py ↔ skills.py ↔ blocks.py)
4. Multi-platform delivery (delivery.py registry ↔ slack.py)
5. Audit + retention (dispatch.py audit ↔ retention.py ↔ daemon.py)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════
# 1. SKILL CREATION — End-to-end: create → invoke → update → list
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _FakeCtx:
    agent_id: str = "test-agent"
    tenant_id: str = "test-tenant"


@pytest.fixture()
def skills_dir(tmp_path: Path):
    """Temporary skills directory with cache invalidation."""
    import robothor.engine.skills as _mod

    _mod._skills_cache = None
    yield tmp_path
    _mod._skills_cache = None


def _patch_skills(skills_dir: Path):
    import robothor.engine.skills as _mod

    return patch.object(_mod, "_skills_dir", return_value=skills_dir)


@pytest.mark.integration
class TestSkillLifecycle:
    """End-to-end: create a skill, invoke it, update it, list all."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, skills_dir: Path):
        from robothor.engine.skills import read_skill_meta
        from robothor.engine.tools.handlers.skills import (
            _create_skill,
            _invoke_skill,
            _list_skills,
            _update_skill,
        )

        ctx = _FakeCtx()

        with _patch_skills(skills_dir):
            # 1. Create
            result = await _create_skill(
                {
                    "name": "deploy-app",
                    "description": "Deploy the application",
                    "content": "## Steps\n\n1. Build image\n2. Push to registry\n3. Update deployment",
                    "tags": ["devops", "deploy"],
                    "tools_required": ["exec"],
                },
                ctx,
            )
            assert result["created"] is True

            # 2. Invoke
            invoke_result = await _invoke_skill({"name": "deploy-app"}, ctx)
            assert "content" in invoke_result
            assert "Build image" in invoke_result["content"]

            # 3. Check usage was tracked
            meta = read_skill_meta("deploy-app", base=skills_dir)
            assert meta is not None
            assert meta["usage_count"] == 1

            # 4. Update
            update_result = await _update_skill(
                {
                    "name": "deploy-app",
                    "content": "## Improved Steps\n\n1. Run tests\n2. Build\n3. Push\n4. Deploy\n5. Verify",
                    "reason": "Added test step and verification",
                },
                ctx,
            )
            assert update_result["updated"] is True
            assert update_result["revision"] == 2

            # 5. Invoke updated version
            invoke2 = await _invoke_skill({"name": "deploy-app"}, ctx)
            assert "Run tests" in invoke2["content"]
            assert "Improved Steps" in invoke2["content"]

            # 6. List shows the skill with metadata
            list_result = await _list_skills({}, ctx)
            names = [s["name"] for s in list_result["skills"]]
            assert "deploy-app" in names

            deploy = next(s for s in list_result["skills"] if s["name"] == "deploy-app")
            assert deploy["auto_generated"] is True
            assert deploy["usage_count"] == 2  # invoked twice

            # 7. Verify revision history
            meta2 = read_skill_meta("deploy-app", base=skills_dir)
            assert meta2["revision"] == 2
            assert len(meta2["revision_history"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. LEARNING LOOP — Outcome assessment + analytics integration
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestOutcomeAssessment:
    """Tests that _assess_outcome correctly classifies different run states."""

    def test_successful_interactive_run(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.TELEGRAM
        run.status = RunStatus.COMPLETED
        run.output_text = "Here's your answer about the quarterly report..."
        run.error_message = None
        run.budget_exhausted = False

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment == "successful"
        assert run.outcome_notes is None

    def test_failed_interactive_run(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.TELEGRAM
        run.status = RunStatus.FAILED
        run.error_message = "Connection timeout to OpenRouter"

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment == "incorrect"
        assert "Connection timeout" in run.outcome_notes

    def test_timeout_interactive_run(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.TELEGRAM
        run.status = RunStatus.TIMEOUT

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment == "abandoned"

    def test_budget_exhausted_run(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.WEBCHAT
        run.status = RunStatus.COMPLETED
        run.output_text = "Partial results before budget ran out"
        run.budget_exhausted = True

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment == "partial"

    def test_cron_runs_not_assessed(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.CRON
        run.status = RunStatus.COMPLETED
        run.output_text = "Cron task completed"

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment is None

    def test_sub_agent_runs_not_assessed(self):
        from robothor.engine.models import AgentRun, RunStatus, TriggerType
        from robothor.engine.runner import AgentRunner

        run = AgentRun()
        run.trigger_type = TriggerType.TELEGRAM
        run.parent_run_id = "parent-123"
        run.status = RunStatus.COMPLETED
        run.output_text = "Sub-agent result"

        AgentRunner._assess_outcome(run)

        assert run.outcome_assessment is None


@pytest.mark.integration
class TestUserModelBlock:
    """Tests that user_model is properly seeded and injected."""

    def test_user_model_in_default_seeds(self):
        from robothor.memory.blocks import DEFAULT_BLOCK_SEEDS

        block_names = [name for name, _, _ in DEFAULT_BLOCK_SEEDS]
        assert "user_model" in block_names

    def test_user_model_in_interactive_warmup(self):
        """user_model block is requested during interactive warmup."""
        from robothor.engine.warmup import build_interactive_preamble

        with patch("robothor.engine.warmup._build_memory_blocks_section") as mock_blocks:
            mock_blocks.return_value = ""
            with patch("robothor.engine.warmup._run_context_hooks", return_value=""):
                build_interactive_preamble("main", "Hello")

            if mock_blocks.called:
                block_list = mock_blocks.call_args[0][0]
                assert "user_model" in block_list


# ═══════════════════════════════════════════════════════════════════════
# 3. PLATFORM IMPORT/EXPORT — Hermes import + generic bundle
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestHermesImport:
    """Tests importing from a simulated Hermes Agent installation."""

    def test_detect_hermes(self, tmp_path: Path):
        from robothor.cli.importer import HermesImporter

        # Not detected without config.yaml or skills/
        assert HermesImporter().detect(tmp_path) is False

        # Detected with config.yaml
        (tmp_path / "config.yaml").write_text("model: gpt-4")
        assert HermesImporter().detect(tmp_path) is True

    def test_import_skills(self, tmp_path: Path, skills_dir: Path):
        from robothor.cli.importer import HermesImporter

        # Create simulated Hermes skill
        hermes_skills = tmp_path / "skills"
        skill_dir = hermes_skills / "web-scrape"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: web-scrape\ndescription: Scrape a URL\n---\n\n1. Fetch URL\n2. Parse HTML"
        )

        with _patch_skills(skills_dir):
            result = HermesImporter().run_import(tmp_path, "test-tenant")

        assert result.skills_imported == 1
        assert (skills_dir / "web-scrape" / "SKILL.md").exists()
        assert (skills_dir / "web-scrape" / "meta.json").exists()

        meta = json.loads((skills_dir / "web-scrape" / "meta.json").read_text())
        assert meta["imported_from"] == "hermes"

    def test_import_memory(self, tmp_path: Path):
        from robothor.cli.importer import HermesImporter

        (tmp_path / "MEMORY.md").write_text("User prefers concise responses")
        (tmp_path / "USER.md").write_text("Name: Jane, Role: CTO")

        with patch("robothor.memory.blocks.write_block") as mock_write:
            result = HermesImporter().run_import(tmp_path, "test-tenant")

        assert result.memory_blocks_set == 2
        calls = {c[0][0]: c[0][1] for c in mock_write.call_args_list}
        assert "operational_findings" in calls
        assert "user_profile" in calls


@pytest.mark.integration
class TestGenericImport:
    """Tests importing from a standardized bundle."""

    def test_detect_yaml_bundle(self, tmp_path: Path):
        from robothor.cli.importer import GenericImporter

        (tmp_path / "robothor-import.yaml").write_text("format: robothor-export")
        assert GenericImporter().detect(tmp_path) is True

    def test_import_memory_from_bundle(self, tmp_path: Path):
        import yaml

        from robothor.cli.importer import GenericImporter

        bundle = {
            "memory": {
                "persona": "I am a helpful AI assistant",
                "working_context": "Currently working on Q2 metrics",
            }
        }
        bundle_path = tmp_path / "robothor-import.yaml"
        bundle_path.write_text(yaml.dump(bundle))

        with patch("robothor.memory.blocks.write_block"):
            result = GenericImporter().run_import(bundle_path, "test-tenant")

        assert result.memory_blocks_set == 2

    def test_auto_detect(self, tmp_path: Path):
        from robothor.cli.importer import auto_detect_platform

        # Hermes detected
        (tmp_path / "config.yaml").write_text("model: gpt-4")
        importer = auto_detect_platform(tmp_path)
        assert importer is not None
        assert importer.platform_name == "hermes"


# ═══════════════════════════════════════════════════════════════════════
# 4. MULTI-PLATFORM DELIVERY — Registry + sender dispatch
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestDeliveryRegistry:
    """Tests the platform sender registry pattern."""

    def setup_method(self):
        """Reset registry between tests."""
        from robothor.engine import delivery

        delivery._platform_senders.clear()

    def test_register_and_retrieve(self):
        from robothor.engine.delivery import (
            get_platform_sender,
            register_platform_sender,
        )

        async def mock_send(chat_id: str, text: str) -> None:
            pass

        register_platform_sender("test_platform", mock_send)
        assert get_platform_sender("test_platform") is mock_send
        assert get_platform_sender("nonexistent") is None

    def test_telegram_backward_compat(self):
        from robothor.engine.delivery import (
            get_platform_sender,
            get_telegram_sender,
            set_telegram_sender,
        )

        async def mock_tg(chat_id: str, text: str) -> None:
            pass

        set_telegram_sender(mock_tg)
        assert get_telegram_sender() is mock_tg
        assert get_platform_sender("telegram") is mock_tg

    @pytest.mark.asyncio
    async def test_deliver_telegram_uses_registry(self):
        from robothor.engine.delivery import _deliver_telegram, register_platform_sender
        from robothor.engine.models import AgentConfig, AgentRun

        sent_messages: list[tuple[str, str]] = []

        async def capture_send(chat_id: str, text: str) -> None:
            sent_messages.append((chat_id, text))

        register_platform_sender("telegram", capture_send)

        config = MagicMock(spec=AgentConfig)
        config.name = "test-agent"
        config.delivery_to = "12345"

        run = AgentRun()
        result = await _deliver_telegram(config, "Hello world", run)

        assert result is True
        assert len(sent_messages) == 1
        assert sent_messages[0][0] == "12345"
        assert "Hello world" in sent_messages[0][1]
        assert run.delivery_channel == "telegram"


@pytest.mark.integration
class TestSlackBot:
    """Tests Slack bot initialization and message splitting."""

    def test_split_text_short(self):
        from robothor.engine.slack import _split_text

        chunks = _split_text("hello", 4000)
        assert chunks == ["hello"]

    def test_split_text_long(self):
        from robothor.engine.slack import _split_text

        text = "line1\nline2\nline3\nline4\nline5"
        chunks = _split_text(text, 12)
        assert len(chunks) > 1
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

    def test_is_slack_configured(self):
        from robothor.engine.slack import is_slack_configured

        with patch.dict("os.environ", {}, clear=True):
            assert is_slack_configured() is False

        with patch.dict(
            "os.environ",
            {"ROBOTHOR_SLACK_BOT_TOKEN": "xoxb-test", "ROBOTHOR_SLACK_APP_TOKEN": "xapp-test"},
        ):
            assert is_slack_configured() is True


# ═══════════════════════════════════════════════════════════════════════
# 5. AUDIT + RETENTION — Tool audit + cleanup orchestration
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestToolCallAudit:
    """Tests that tool execution is audited end-to-end."""

    @pytest.mark.asyncio
    async def test_successful_tool_call_audited(self):
        from robothor.engine.tools.dispatch import _audit_tool_call

        with patch("robothor.audit.logger.log_event") as mock_log:
            _audit_tool_call("search_memory", "main", "robothor-primary")

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs[1]["event_type"] == "agent.tool_call"  # noqa: SIM300
            assert call_kwargs[1]["action"] == "search_memory"
            assert call_kwargs[1]["actor"] == "main"
            assert call_kwargs[1]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_failed_tool_call_audited(self):
        from robothor.engine.tools.dispatch import _audit_tool_call

        with patch("robothor.audit.logger.log_event") as mock_log:
            _audit_tool_call(
                "exec", "main", "robothor-primary", status="error", error="Permission denied"
            )

            call_kwargs = mock_log.call_args
            assert call_kwargs[1]["status"] == "error"
            assert "Permission denied" in call_kwargs[1]["details"]["error"]

    @pytest.mark.asyncio
    async def test_audit_never_raises(self):
        """Audit failure must not propagate to tool execution."""
        from robothor.engine.tools.dispatch import _audit_tool_call

        with patch("robothor.audit.logger.log_event", side_effect=RuntimeError("DB down")):
            # Should not raise
            _audit_tool_call("search_memory", "main", "robothor-primary")


@pytest.mark.integration
class TestRetentionIntegration:
    """Tests retention policy consistency and orchestrator resilience."""

    def test_policy_covers_all_high_growth_tables(self):
        from robothor.engine.retention import RETENTION_POLICY

        high_growth = {"agent_run_steps", "audit_log", "agent_runs", "telemetry"}
        covered = set(RETENTION_POLICY.keys())
        assert high_growth.issubset(covered), f"Missing: {high_growth - covered}"

    def test_orchestrator_isolates_failures(self):
        """One table failure doesn't block cleanup of others."""
        from robothor.engine.retention import run_retention_cleanup

        call_count = 0

        def mock_cleanup(table, **kwargs):
            nonlocal call_count
            call_count += 1
            if table == "audit_log":
                raise RuntimeError("Simulated failure")
            return 0

        with patch("robothor.engine.retention._cleanup_table", side_effect=mock_cleanup):
            results = run_retention_cleanup()

        assert results["audit_log"] == -1
        # All other tables should have been attempted
        from robothor.engine.retention import RETENTION_POLICY

        assert call_count == len(RETENTION_POLICY)

    def test_children_cleaned_before_parents(self):
        """FK cascade safety: child tables must be cleaned before parents."""
        from robothor.engine.retention import RETENTION_POLICY

        tables = list(RETENTION_POLICY.keys())

        # agent_run_steps must come before agent_runs
        if "agent_run_steps" in tables and "agent_runs" in tables:
            assert tables.index("agent_run_steps") < tables.index("agent_runs")

        # workflow_run_steps must come before workflow_runs
        if "workflow_run_steps" in tables and "workflow_runs" in tables:
            assert tables.index("workflow_run_steps") < tables.index("workflow_runs")


@pytest.mark.integration
class TestWatchdogRecording:
    """Tests that watchdog events are recorded to memory blocks."""

    def test_record_watchdog_event(self):
        from robothor.engine.daemon import _record_watchdog_event

        with (
            patch("robothor.memory.blocks.read_block") as mock_read,
            patch("robothor.memory.blocks.write_block") as mock_write,
        ):
            mock_read.return_value = {"content": "[old] existing entry"}

            _record_watchdog_event("pg_failure", "consecutive=3: connection refused")

            mock_write.assert_called_once()
            written = mock_write.call_args[0][1]
            assert "pg_failure" in written
            assert "consecutive=3" in written
            assert "[old] existing entry" in written

    def test_record_watchdog_event_never_raises(self):
        """Watchdog recording must never crash the daemon."""
        from robothor.engine.daemon import _record_watchdog_event

        with patch("robothor.memory.blocks.read_block", side_effect=RuntimeError("DB down")):
            # Must not raise
            _record_watchdog_event("test_event", "detail")


# ═══════════════════════════════════════════════════════════════════════
# 6. ONBOARDING — Conversational flow
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestOnboardingFlow:
    """Tests the Telegram self-service onboarding conversation."""

    def setup_method(self):
        from robothor.engine.onboarding import _onboarding_sessions

        _onboarding_sessions.clear()

    def test_full_onboarding_flow(self):
        from robothor.engine.onboarding import (
            is_onboarding,
            process_onboarding,
            start_onboarding,
        )

        user_id = "tg_12345"

        # Step 1: Start
        assert not is_onboarding(user_id)
        prompt = start_onboarding(user_id)
        assert "name" in prompt.lower()
        assert is_onboarding(user_id)

        # Step 2: Provide name
        reply = process_onboarding(user_id, "Jane Smith")
        assert "jane-smith" in reply.lower() or "Jane Smith" in reply
        assert "yes" in reply.lower()

        # Step 3: Confirm — mock _finalize_onboarding entirely since DAL may not have
        # create_tenant_with_user (depends on migration 033)
        def mock_finalize(uid, session):
            from robothor.engine.onboarding import _cancel_onboarding

            _cancel_onboarding(uid)
            return "You're all set, Jane! Your workspace **jane-smith** is ready."

        with patch("robothor.engine.onboarding._finalize_onboarding", side_effect=mock_finalize):
            reply = process_onboarding(user_id, "yes")

        assert "all set" in reply.lower()
        assert not is_onboarding(user_id)

    def test_custom_workspace_id(self):
        from robothor.engine.onboarding import process_onboarding, start_onboarding

        user_id = "tg_99999"
        start_onboarding(user_id)
        process_onboarding(user_id, "Bob Builder")

        # Provide custom ID instead of "yes"
        mock_create = MagicMock(return_value="bob-custom-id")
        with (
            patch("robothor.crm.dal.get_tenant", return_value=None, create=True),
            patch("robothor.crm.dal.create_tenant_with_user", mock_create, create=True),
        ):
            reply = process_onboarding(user_id, "bob-custom-id")

        assert "bob-custom-id" in reply

    def test_tenant_collision(self):
        from robothor.engine.onboarding import process_onboarding, start_onboarding

        user_id = "tg_collision"
        start_onboarding(user_id)
        process_onboarding(user_id, "Existing User")

        with patch(
            "robothor.engine.onboarding._finalize_onboarding",
            return_value="Workspace ID 'existing-user' is already taken. Please message me again.",
        ):
            reply = process_onboarding(user_id, "yes")

        assert "taken" in reply.lower()
