from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    PENDING      = "pending"
    RUNNING      = "running"
    COMPLETED    = "completed"
    FAILED       = "failed"
    TIMED_OUT    = "timed_out"
    FALLBACK_USED = "fallback_used"


class BaseAgent:
    """
    Guardrail wrapper for all agents.

    Subclasses implement:
      _execute(*args, **kwargs) -> result
      _fallback(*args, **kwargs) -> result   (must never raise)

    Call run_with_guardrails() — it always returns, never raises.
    Check health_report() to see whether execution succeeded or fell back.
    """

    name: str = "base"
    timeout_seconds: float = 10.0
    max_retries: int = 1            # attempts = max_retries + 1

    def __init__(self) -> None:
        self._status = AgentStatus.PENDING
        self._error: Optional[Exception] = None
        self._attempt = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def is_healthy(self) -> bool:
        return self._status in (
            AgentStatus.COMPLETED,
            AgentStatus.RUNNING,
            AgentStatus.FALLBACK_USED,
        )

    async def run_with_guardrails(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute with timeout + retry + fallback protection.
        Guaranteed to return a value — never raises (except CancelledError).
        """
        self._status = AgentStatus.RUNNING

        for attempt in range(self.max_retries + 1):
            self._attempt = attempt + 1
            try:
                result = await asyncio.wait_for(
                    self._execute(*args, **kwargs),
                    timeout=self.timeout_seconds,
                )
                self._status = AgentStatus.COMPLETED
                logger.info("[%s] Completed on attempt %d", self.name, self._attempt)
                return result

            except asyncio.CancelledError:
                # Must propagate — do not swallow
                self._status = AgentStatus.FAILED
                raise

            except asyncio.TimeoutError:
                logger.warning(
                    "[%s] Timed out after %.1fs (attempt %d/%d)",
                    self.name, self.timeout_seconds, self._attempt, self.max_retries + 1,
                )
                if attempt == self.max_retries:
                    self._status = AgentStatus.TIMED_OUT

            except Exception as exc:
                self._error = exc
                logger.error(
                    "[%s] Error on attempt %d: %s",
                    self.name, self._attempt, exc, exc_info=True,
                )
                if attempt == self.max_retries:
                    self._status = AgentStatus.FAILED

        # All attempts exhausted — run fallback
        logger.warning("[%s] Falling back after %d attempt(s)", self.name, self._attempt)
        self._status = AgentStatus.FALLBACK_USED
        return self._fallback(*args, **kwargs)

    def health_report(self) -> dict:
        return {
            "agent":    self.name,
            "status":   self._status.value,
            "attempts": self._attempt,
            "error":    str(self._error) if self._error else None,
        }

    # ------------------------------------------------------------------
    # Subclass contracts
    # ------------------------------------------------------------------

    async def _execute(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self.name}._execute() not implemented")

    def _fallback(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"{self.name}._fallback() not implemented — define a safe default return"
        )
