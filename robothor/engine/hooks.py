"""
Event Hooks — Redis Stream consumers that trigger agent runs.

Subscribes to Redis streams (email, calendar, etc.) and invokes
agents when matching events arrive.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from robothor.engine.dedup import try_acquire, release
from robothor.engine.delivery import deliver
from robothor.engine.models import TriggerType

MAX_RETRIES = 3

if TYPE_CHECKING:
    from robothor.engine.config import EngineConfig
    from robothor.engine.runner import AgentRunner

logger = logging.getLogger(__name__)

# Event → agent mapping
EVENT_TRIGGERS: dict[str, list[dict]] = {
    "email": [
        {
            "event_type": "email.new",
            "agent_id": "email-classifier",
            "message": "New email received. Process the triage inbox and classify emails.",
        },
    ],
    "calendar": [
        {
            "event_type": "calendar.updated",
            "agent_id": "calendar-monitor",
            "message": "Calendar updated. Check for conflicts, cancellations, and changes.",
        },
    ],
    "vision": [
        {
            "event_type": "vision.unknown_person",
            "agent_id": "vision-monitor",
            "message": "Unknown person detected. Check vision events and escalate if needed.",
        },
    ],
}


class EventHooks:
    """Redis Stream consumer that triggers agent runs on events."""

    def __init__(self, config: EngineConfig, runner: AgentRunner) -> None:
        self.config = config
        self.runner = runner
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start consuming Redis streams."""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            logger.warning("redis.asyncio not available, event hooks disabled")
            await self._idle()
            return

        from robothor.config import get_config
        cfg = get_config()

        try:
            r = aioredis.Redis(
                host=cfg.redis.host,
                port=cfg.redis.port,
                db=cfg.redis.db,
                password=cfg.redis.password or None,
            )
            await r.ping()
            logger.info("Event hooks connected to Redis")
        except Exception as e:
            logger.warning("Redis not available, event hooks disabled: %s", e)
            await self._idle()
            return

        consumer_group = "engine"
        consumer_name = f"engine-{self.config.tenant_id}"
        streams = list(EVENT_TRIGGERS.keys())

        # Create consumer groups (ignore if they already exist)
        for stream in streams:
            try:
                await r.xgroup_create(stream, consumer_group, id="$", mkstream=True)
            except Exception:
                pass  # Group already exists

        logger.info("Listening on streams: %s", ", ".join(streams))

        # Read loop
        stream_keys = {s: ">" for s in streams}
        while not self._stop_event.is_set():
            try:
                results = await r.xreadgroup(
                    consumer_group,
                    consumer_name,
                    stream_keys,
                    count=5,
                    block=5000,
                )
                if not results:
                    continue

                for stream_name, messages in results:
                    stream_str = stream_name.decode() if isinstance(stream_name, bytes) else stream_name
                    for msg_id, data in messages:
                        await self._handle_event(stream_str, msg_id, data, r, consumer_group)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Event hook error: %s", e, exc_info=True)
                await asyncio.sleep(5)

        await r.aclose()

    async def _handle_event(self, stream: str, msg_id, data: dict, redis_client, group: str) -> None:
        """Process a single event from a stream."""
        # Decode bytes
        decoded = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            decoded[key] = val

        event_type = decoded.get("event_type", "")
        triggers = EVENT_TRIGGERS.get(stream, [])

        for trigger in triggers:
            if event_type and trigger.get("event_type") != event_type:
                continue

            agent_id = trigger["agent_id"]

            # Dedup: skip if agent is already running (shared with scheduler)
            if not try_acquire(agent_id):
                logger.debug("Skipping %s — already running", agent_id)
                continue

            failed = False
            try:
                from robothor.engine.config import load_agent_config
                agent_config = load_agent_config(agent_id, self.config.manifest_dir)

                # Build warm message with preamble
                message = trigger["message"]
                if agent_config:
                    try:
                        from robothor.engine.warmup import build_warmth_preamble
                        preamble = build_warmth_preamble(
                            agent_config, self.config.workspace, self.config.tenant_id
                        )
                        if preamble:
                            message = f"{preamble}\n\n{message}"
                    except Exception as e:
                        logger.debug("Warmup preamble failed for hook %s: %s", agent_id, e)

                run = await self.runner.execute(
                    agent_id=agent_id,
                    message=message,
                    trigger_type=TriggerType.HOOK,
                    trigger_detail=f"{stream}:{event_type}",
                    agent_config=agent_config,
                )

                if agent_config:
                    await deliver(agent_config, run)

                if run.status.value in ("failed", "timeout"):
                    failed = True

                logger.info(
                    "Hook complete: %s via %s:%s status=%s",
                    agent_id, stream, event_type, run.status.value,
                )
            except Exception as e:
                logger.error("Hook execution failed for %s: %s", agent_id, e)
                failed = True
            finally:
                release(agent_id)

        # Dead letter queue on failure
        if failed:
            retry_count = int(decoded.get("_retry_count", "0"))
            if retry_count < MAX_RETRIES:
                # Re-add with incremented retry count
                try:
                    retry_data = dict(decoded)
                    retry_data["_retry_count"] = str(retry_count + 1)
                    await redis_client.xadd(stream, retry_data)
                    logger.info(
                        "Retrying %s:%s (attempt %d/%d)",
                        stream, event_type, retry_count + 1, MAX_RETRIES,
                    )
                except Exception as e:
                    logger.warning("Failed to re-queue for retry: %s", e)
            else:
                # Move to DLQ
                try:
                    dlq_stream = f"{stream}:dlq"
                    await redis_client.xadd(dlq_stream, decoded, maxlen=1000)
                    logger.warning(
                        "Moved to DLQ %s after %d retries: %s",
                        dlq_stream, MAX_RETRIES, event_type,
                    )
                except Exception as e:
                    logger.warning("Failed to add to DLQ: %s", e)

        # Acknowledge the original message
        try:
            await redis_client.xack(stream, group, msg_id)
        except Exception as e:
            logger.warning("Failed to ack message %s: %s", msg_id, e)

    async def _idle(self) -> None:
        """Idle loop when Redis is not available."""
        while not self._stop_event.is_set():
            await asyncio.sleep(60)

    async def stop(self) -> None:
        """Signal the event loop to stop."""
        self._stop_event.set()
