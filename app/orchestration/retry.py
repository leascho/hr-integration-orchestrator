"""Retry policy with capped exponential backoff."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetryPolicy:
    """max_retries is the number of retries after the initial attempt.

    Default: 3 retries -> at most 4 attempts, with delays of 0.5s, 1s, 2s (capped at 4s).
    """

    max_retries: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    sleep: Callable[[float], None] = field(default=time.sleep, compare=False)

    @property
    def max_attempts(self) -> int:
        return self.max_retries + 1

    def delay_for_retry(self, retry_number: int) -> float:
        """Delay before retry number `retry_number` (1-based)."""
        return min(self.base_delay_seconds * (2 ** (retry_number - 1)), self.max_delay_seconds)
