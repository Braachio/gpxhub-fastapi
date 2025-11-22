import os
import requests

USE_GPT = False  # 🔒 GPT 사용 여부를 제어하는 플래그

def generate_ai_feedback(prompt: str) -> tuple[str, str]:
    """
    GPT API를 통해 AI 피드백 생성 (현재는 사용 중지됨).
    실패 시 또는 사용 중지 시 기본 메시지 반환.
    """
    if not USE_GPT:
        return (
            "⚠️ 현재 AI 피드백 기능은 일시적으로 비활성화되어 있습니다.\n기본 분석 결과만 제공됩니다.",
            "disabled"
        )

    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "당신은 전문 드라이빙 코치이며 항상 한국어로 작성합니다."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            },
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        feedback = result["choices"][0]["message"]["content"].strip()
        return feedback, "gpt"

    except Exception as e:
        print(f"❌ GPT 피드백 생성 실패: {e}")
        return (
            "⚠️ 현재 AI 피드백 서버에 연결할 수 없습니다.\n기본 분석 결과만 제공됩니다.",
            "error"
        )
