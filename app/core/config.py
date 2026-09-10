from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_SECRET_KEY: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # Database (SQLite by default — swap for postgresql+asyncpg://... in production)
    DATABASE_URL: str = "sqlite+aiosqlite:///./franchise.db"
    
    # here Geocoding api key
    HERE_API_KEY: str = ""
    
    # JWT
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # OTP
    OTP_EXPIRE_MINUTES: int = 5
    OTP__MINUTES:  int  =  1440

    # Super Admin
    SUPER_ADMIN_EMAIL: str = "admin@example.com"
    SUPER_ADMIN_PASSWORD: str = "Admin@1234"
    SUPER_ADMIN_NAME: str = "Super Admin"

    # App
    APP_NAME: str = "Franchise Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:8000,https://roadoz-frontend-prod.vercel.app"

    LOCATION_RADIUS_METERS: int = 100

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
