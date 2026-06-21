"""Environment configuration for the ingester."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; env vars may be set externally
    pass


# Per-province API keys (only needed for key-gated IBI hosts).
API_KEYS: Dict[str, Optional[str]] = {
    "mb": os.getenv("MANITOBA_511_KEY"),
    "sk": os.getenv("SASKATCHEWAN_511_KEY"),
    "nb": os.getenv("NB_511_KEY"),
    "ns": os.getenv("NS_511_KEY"),
    "pe": os.getenv("PE_511_KEY"),
    "nl": os.getenv("NL_511_KEY"),
}


@dataclass
class Settings:
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_service_key: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY")

    def require_supabase(self) -> None:
        if not self.supabase_url or not self.supabase_service_key:
            raise SystemExit(
                "Missing SUPABASE_URL / SUPABASE_SERVICE_KEY. Copy .env.example to "
                ".env and fill them in (service_role key from Supabase dashboard)."
            )


settings = Settings()
