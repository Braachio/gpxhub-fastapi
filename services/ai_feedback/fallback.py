from .base import AIFeedbackProvider

class FallbackFeedbackProvider(AIFeedbackProvider):
    def generate(self, prompt: str) -> tuple[str, str]:
        return (
            "⚠️ 현재 AI 피드백 서버에 연결할 수 없습니다.\n기본 분석 결과만 제공됩니다.",
            "error"
        )
