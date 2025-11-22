# import requests
# from .base import AIFeedbackProvider

# class OllamaFeedbackProvider(AIFeedbackProvider):
#     def generate(self, prompt: str) -> tuple[str, str]:
#         response = requests.post(
#             "http://localhost:11434/v1/chat/completions",
#             headers={"Content-Type": "application/json"},
#             json={
#                 "model": "llama3",
#                 "messages": [
#                     {"role": "system", "content": "당신은 전문 드라이빙 코치이며 항상 한국어로 작성합니다."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 "temperature": 0.7
#             },
#             timeout=5
#         )
#         response.raise_for_status()
#         result = response.json()
#         feedback = result["choices"][0]["message"]["content"].strip()
#         return feedback, "ollama"
