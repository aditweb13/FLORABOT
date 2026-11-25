from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./florabot.db"
    upload_dir: str = "./data/uploads"
    report_dir: str = "./data/reports"
    plantnet_api_key: str = ""
    plant_id_api_key: str = ""
    plant_id_api_url: str = "https://plant.id/api/v3/health_assessment"
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    gemini_api_key: str = ""
    camera_stream_url: str = "http://10.105.234.29:81/stream"
    camera_snapshot_url: str = "http://10.105.234.29/capture"
    device_offline_timeout_seconds: int = 120
    monitoring_interval_seconds: int = 60
    min_confidence_threshold: float = 0.35
    high_confidence_threshold: float = 0.70
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    # Security, JWT & IoT API Authentication
    jwt_secret_key: str = "florabot-production-jwt-secret-key-replace-with-env-2026"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours
    device_api_key: str = "florabot-iot-device-secret-key-2026"
    enable_auth: bool = False  # Set to True to enforce JWT authentication across all write endpoints
    rate_limit_per_minute: int = 60
    rate_limit_auth_per_minute: int = 10
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
