from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
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

# ML predictor import for startup preloading
from services.ml_predictor import get_predictor

app = FastAPI()
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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


@app.on_event("startup")
async def startup_event():
    """
    Preload ML models at startup to fail fast if models are not available.
    This prevents 503 errors on first request.
    """
    logger.info("🚀 Starting application startup...")
    
    # Preload models for both modes
    for mode in ["pre", "post"]:
        try:
            logger.info(f"📦 Preloading {mode} mode predictor...")
            predictor = get_predictor(mode=mode)
            logger.info(
                f"✅ {mode.upper()} mode predictor loaded successfully. "
                f"Model version: {predictor.model_version}, "
                f"Features: {len(predictor.feature_names)}"
            )
        except FileNotFoundError as e:
            logger.error(f"❌ Failed to load {mode} mode predictor: {e}")
            logger.error(
                "💡 Tip: Set IRACING_ML_MODEL_DIR or IRACING_ENSEMBLE_CONFIG_* "
                "environment variables, or ensure model files are in the expected location."
            )
            # Don't fail startup - allow the app to start but requests will return 503
            # This is better than crashing the entire service
        except Exception as e:
            logger.error(f"❌ Unexpected error loading {mode} mode predictor: {e}", exc_info=True)
    
    logger.info("✅ Application startup complete")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
