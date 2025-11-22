# import os
# import openai
# from dotenv import load_dotenv

# load_dotenv()
# openai.api_key = os.getenv("OPENAI_API_KEY")

# def generate_gpt_feedback(prompt: str, model: str = "gpt-3.5-turbo") -> str:
#     try:
#         response = openai.ChatCompletion.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": "당신은 전문 레이싱 드라이빙 코치이며, 항상 한국어로 피드백을 작성합니다."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7
#         )
#         return response['choices'][0]['message']['content'].strip()
#     except Exception as e:
#         print(f"❌ GPT 피드백 생성 실패: {e}")
#         raise
