from __future__ import annotations

import ast
import base64
import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _as_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    openai_api_key: str
    google_sheets_id: str
    google_service_account_json: str
    google_service_account_json_base64: str
    evolution_webhook_secret: Optional[str]
    evolution_api_url: Optional[str]
    evolution_api_key: Optional[str]
    crm_target_group_id: Optional[str]
    disable_evolution_confirmation: bool
    default_timezone: str = "UTC"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            google_sheets_id=os.getenv("GOOGLE_SHEETS_ID", ""),
            google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            google_service_account_json_base64=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", ""),
            evolution_webhook_secret=os.getenv("EVOLUTION_WEBHOOK_SECRET"),
            evolution_api_url=os.getenv("EVOLUTION_API_URL"),
            evolution_api_key=os.getenv("EVOLUTION_API_KEY"),
            crm_target_group_id=(
                os.getenv("CRM_TARGET_GROUP_ID")
                or os.getenv("GROUP_ID_CRM_CONFIGURADO")
                or os.getenv("GROUP_ID_CRM")
                or os.getenv("CRM_GROUP_ID")
            ),
            disable_evolution_confirmation=_as_bool(os.getenv("DISABLE_EVOLUTION_CONFIRMATION"), default=True),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
        )

    @staticmethod
    def _parse_service_account_payload(raw: str) -> dict:
        value = (raw or "").strip()
        if not value:
            raise ValueError("Empty Google service account payload")

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        unwrapped = value.strip('"').strip("'").replace("\\n", "\n")
        try:
            return json.loads(unwrapped)
        except json.JSONDecodeError:
            pass

        parsed = ast.literal_eval(unwrapped)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must decode to a dict")

    def service_account_info(self) -> dict:
        if self.google_service_account_json_base64:
            decoded = base64.b64decode(self.google_service_account_json_base64).decode("utf-8")
            return self._parse_service_account_payload(decoded)

        if self.google_service_account_json:
            raw = self.google_service_account_json.strip()
            if raw.startswith("{") or raw.startswith("'") or raw.startswith('"'):
                return self._parse_service_account_payload(raw)
            with open(raw, "r", encoding="utf-8") as fp:
                return json.load(fp)

        raise ValueError("Provide GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")


settings = Settings.from_env()
