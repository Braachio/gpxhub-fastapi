from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# API 모듈 import
from api.upload import router as upload_router
from api.get_lap import router as get_lap_router
from api import brake_analysis
from api.dashboard import router as dashboard_router
from api.braking_dashboard import router as braking_dashboard_router
from api.iracing_schedule import router as iracing_schedule_router
from api import iracing_sdk
from api.telemetry_upload import router as telemetry_upload_router
from api.ml_predict import router as ml_predict_router
# from api import track_corners
from app.api.endpoints.collector import router as collector_router
from app.api.endpoints.predict import router as predict_router

app = FastAPI()
load_dotenv()


@app.get("/")
async def root():
    return {"message": "🚀 GPX API is running!"}


# ✅ CORS 수정: allow_credentials=True일 때 "*" 금지
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ghostx.site",           # 🔒 운영 도메인
        "http://localhost:3000"          # 💻 개발용 도메인
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 공용 API v1 라우터
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(collector_router, tags=["collector"])
api_router.include_router(predict_router, tags=["predict"])
app.include_router(api_router)

# 기존 라우터 등록 (/api)
app.include_router(upload_router, prefix="/api")
app.include_router(get_lap_router, prefix="/api")
app.include_router(brake_analysis.router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(braking_dashboard_router, prefix="/api")
app.include_router(iracing_schedule_router, prefix="/api")
app.include_router(iracing_sdk.router, prefix="/api")
app.include_router(telemetry_upload_router, prefix="/api")
app.include_router(ml_predict_router)
# app.include_router(track_corners.router)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
