from abc import ABC, abstractmethod
from typing import Optional, Callable


class BrowserSession(ABC):
    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @abstractmethod
    def inject_prompt(self, prompt: str) -> bool:
        pass

    @abstractmethod
    def click_send(self) -> bool:
        pass

    @abstractmethod
    def wait_response(self, timeout_seconds: int) -> str:
        pass

    @abstractmethod
    def copy_response(self) -> bool:
        pass

    @abstractmethod
    def get_clipboard_text(self) -> Optional[str]:
        pass

    @abstractmethod
    def reload(self) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    def run(
        self,
        prompt: str,
        expected_blocks: int,
        timeout_seconds: int,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        if not self.inject_prompt(prompt):
            raise RuntimeError("Prompt injection failed")
        if not self.click_send():
            raise RuntimeError("Send button click failed")
        return self.wait_response(timeout_seconds)