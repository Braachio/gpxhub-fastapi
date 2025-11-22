FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for ML libraries (XGBoost, LightGBM need libgomp)
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy ML models - try multiple paths depending on build context
# Option 1: If building from root (ghostx/), models are at ../ml_models
# Option 2: If models are already in ghostx_fastapi/ml_models, they're copied above
# Option 3: Use environment variable IRACING_ML_MODEL_DIR at runtime
# For Cloud Run, ensure ml_models directory is included in the build context

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
