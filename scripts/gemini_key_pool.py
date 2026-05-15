#!/usr/bin/env python3

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = ROOT / "config/gemini_api_keys.local.json"
SHARED_CONFIG = ROOT / "config/gemini_api_keys.json"


PRO_MODEL_RE = re.compile(r"(^|[-_.])pro($|[-_.])", re.IGNORECASE)


@dataclass(frozen=True)
class GeminiKey:
    name: str
    value: str
    scope: str = "default"

    @property
    def label(self):
        return self.name or "unnamed-key"


class GeminiKeyPool:
    """Select Gemini API keys by model family without logging key material."""

    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else self._default_config_path()
        self.keys = self._load_keys()

    @staticmethod
    def is_pro_model(model):
        return bool(PRO_MODEL_RE.search(model or ""))

    def keys_for_model(self, model):
        if not self.keys:
            return []

        if self.is_pro_model(model):
            pro_keys = [key for key in self.keys if key.scope == "pro"]
            default_keys = [key for key in self.keys if key.scope in ("default", "all")]
            return pro_keys + default_keys

        return [key for key in self.keys if key.scope in ("default", "all")]

    def attempt_count_for_model(self, model, requested_attempts):
        eligible_count = len(self.keys_for_model(model))
        if eligible_count == 0:
            return requested_attempts
        return max(requested_attempts, eligible_count)

    def env_for_attempt(self, model, attempt_index, base_env=None):
        env = dict(base_env or os.environ)
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

        eligible_keys = self.keys_for_model(model)
        if not eligible_keys:
            return env, "environment"

        key = eligible_keys[attempt_index % len(eligible_keys)]
        env["GEMINI_API_KEY"] = key.value
        env.pop("GOOGLE_API_KEY", None)
        env.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        env.pop("GOOGLE_GENAI_USE_GCA", None)
        return env, key.label

    def _default_config_path(self):
        override = (os.environ.get("DAILY_CURATION_GEMINI_KEYS_FILE") or "").strip()
        if override:
            return Path(override).expanduser()
        if LOCAL_CONFIG.exists():
            return LOCAL_CONFIG
        if SHARED_CONFIG.exists():
            return SHARED_CONFIG
        return LOCAL_CONFIG

    def _load_keys(self):
        config_keys = self._load_config_keys()
        if config_keys:
            return config_keys
        return self._load_env_keys()

    def _load_config_keys(self):
        if not self.config_path.exists():
            return []

        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        entries = payload.get("keys", [])
        if not isinstance(entries, list):
            raise ValueError(f"Gemini key config 'keys' must be a list: {self.config_path}")

        keys = []
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"Gemini key entry #{index} must be an object: {self.config_path}")

            value = (entry.get("api_key") or "").strip()
            if not value:
                continue

            scope = (entry.get("scope") or "default").strip().lower()
            if scope not in ("default", "pro", "all"):
                raise ValueError(f"Unsupported Gemini key scope {scope!r} in {self.config_path}")

            name = (entry.get("name") or f"{scope}-{index}").strip()
            keys.append(GeminiKey(name=name, value=value, scope=scope))

        return keys

    def _load_env_keys(self):
        keys = []
        default_values = self._split_env("GEMINI_DEFAULT_API_KEYS") or self._split_env("GEMINI_API_KEY_POOL")
        pro_values = self._split_env("GEMINI_PRO_API_KEYS")

        for index, value in enumerate(default_values, start=1):
            keys.append(GeminiKey(name=f"env-default-{index}", value=value, scope="default"))
        for index, value in enumerate(pro_values, start=1):
            keys.append(GeminiKey(name=f"env-pro-{index}", value=value, scope="pro"))

        single_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if single_key and not keys:
            keys.append(GeminiKey(name="env-gemini-api-key", value=single_key, scope="default"))

        return keys

    @staticmethod
    def _split_env(name):
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return []
        return [value.strip() for value in raw.split(",") if value.strip()]
