from fastapi import APIRouter
from io import StringIO
import pandas as pd
import requests

from schemas.schemas import AnalyzeRequest

router = APIRouter()

@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        res = requests.get(req.file_url)
        res.raise_for_status()
        df = pd.read_csv(StringIO(res.text))

    except pd.errors.ParserError:
        return {"error": "❌ CSV 파싱 실패 - 파일 형식을 확인하세요."}
    except Exception as e:
        return {"error": f"분석 실패: {str(e)}"}
