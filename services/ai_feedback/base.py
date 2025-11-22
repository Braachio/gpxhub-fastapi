from abc import ABC, abstractmethod

class AIFeedbackProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> tuple[str, str]:
        pass
