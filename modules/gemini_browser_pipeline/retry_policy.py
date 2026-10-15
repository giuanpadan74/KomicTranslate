import time
from dataclasses import dataclass
from typing import Optional, List, Callable


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 3.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


class RetryPolicy:
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ):
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.base_delay * (self.config.exponential_base ** attempt),
                        self.config.max_delay,
                    )
                    if on_retry:
                        on_retry(attempt + 1, e)
                    time.sleep(delay)
                else:
                    break
        raise last_error

    @staticmethod
    def default() -> "RetryPolicy":
        return RetryPolicy(RetryConfig())


def get_dynamic_timeout(block_count: int, base: int = 60, per_block: int = 20) -> int:
    effective_blocks = min(max(block_count, 1), 60)
    return min(base + (effective_blocks - 1) * per_block, 300)