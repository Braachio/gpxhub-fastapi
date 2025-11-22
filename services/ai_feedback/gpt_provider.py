# from openai import OpenAI  # 예시용
from .base import AIFeedbackProvider

class GPTFeedbackProvider(AIFeedbackProvider):
    def generate(self, prompt: str) -> tuple[str, str]:
        # 추후 OpenAI API 연결 예정
        raise NotImplementedError("GPT는 아직 구현되지 않았습니다.")
