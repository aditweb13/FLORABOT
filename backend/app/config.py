from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/florabot.db"
    upload_dir: str = "./data/uploads"
    report_dir: str = "./data/reports"
    plant_id_api_key: str = ""
    plant_id_api_url: str = "https://plant.id/api/v3/health_assessment"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    camera_stream_url: str = ""
    camera_snapshot_url: str = ""
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
