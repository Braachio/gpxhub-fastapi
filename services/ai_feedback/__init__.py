# from .ollama_provider import OllamaFeedbackProvider
from .fallback import FallbackFeedbackProvider
from .gpt_provider import GPTFeedbackProvider  # GPT 붙일 때 활성화

from .base import AIFeedbackProvider


def generate_ai_feedback(prompt: str) -> tuple[str, str]:
    """
    AI 피드백 생성 진입점
    우선순위: Ollama → Fallback
    """
    providers: list[AIFeedbackProvider] = [
        GPTFeedbackProvider(),  # GPT 사용 시
        # OllamaFeedbackProvider(),
    ]

    for provider in providers:
        try:
            return provider.generate(prompt)
        except Exception as e:
            print(f"❌ {provider.__class__.__name__} 실패: {e}")
            continue

    return FallbackFeedbackProvider().generate(prompt)

