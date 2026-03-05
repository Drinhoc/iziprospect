from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    openai_api_key: str
    google_sheets_id: str
    google_service_account_json: str
    evolution_webhook_secret: Optional[str]
    evolution_api_url: Optional[str]
    evolution_api_key: Optional[str]
    default_timezone: str = "UTC"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            google_sheets_id=os.getenv("GOOGLE_SHEETS_ID", ""),
            google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            evolution_webhook_secret=os.getenv("EVOLUTION_WEBHOOK_SECRET"),
            evolution_api_url=os.getenv("EVOLUTION_API_URL"),
            evolution_api_key=os.getenv("EVOLUTION_API_KEY"),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
        )

    def service_account_info(self) -> dict:
        if not self.google_service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is required")

        raw = self.google_service_account_json.strip()
        if raw.startswith("{"):
            return json.loads(raw)

        with open(raw, "r", encoding="utf-8") as fp:
            return json.load(fp)


settings = Settings.from_env()
