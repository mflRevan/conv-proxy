"""
Central configuration for clawproxy.
Loads from (in order): ~/.clawproxy/config.json → .env → environment variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

# Load ~/.clawproxy/config.json if it exists
_DATA_DIR = Path.home() / ".clawproxy"
_CONFIG_FILE = _DATA_DIR / "config.json"
_file_config: dict = {}
if _CONFIG_FILE.exists():
    try:
        with open(_CONFIG_FILE) as f:
            _file_config = json.load(f)
    except Exception:
        pass


def _cfg(section: str, key: str, env_key: str, default: str = "") -> str:
    """Resolve a config value: env var → config.json → default."""
    val = os.getenv(env_key, "")
    if val:
        return val
    s = _file_config.get(section, {})
    if isinstance(s, dict) and key in s:
        return str(s[key])
    return default


@dataclass
class AppConfig:
    # Server
    host: str = "0.0.0.0"
    port: int = 37374

    # Gateway
    gateway_url: str = "ws://127.0.0.1:18789"
    gateway_token: str = ""
    gateway_origin: str = "http://127.0.0.1:18789"

    # Proxy agent
    openrouter_api_key: str = ""
    proxy_model: str = "openai/gpt-oss-120b"
    proxy_system_prompt_path: str = str(_PROJECT_ROOT / "config" / "PROXY.md")

    # HF
    hf_token: str = ""

    # Voice
    vad_enabled: bool = True
    wakeword_enabled: bool = True
    wakeword_threshold: float = 0.55
    wakeword_active_window_s: float = 10.0

    # STT
    stt_engine: str = "whisper-small"
    whisper_model: str = "small"

    # History
    main_history_length: int = 20
    main_history_full_count: int = 5

    # TTS
    tts_enabled: bool = True

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            host=_cfg("server", "host", "HOST", "0.0.0.0"),
            port=int(_cfg("server", "port", "PORT", "37374")),
            gateway_url=_cfg("gateway", "url", "GATEWAY_URL", "ws://127.0.0.1:18789"),
            gateway_token=_cfg("gateway", "token", "GATEWAY_TOKEN", ""),
            gateway_origin=_cfg("gateway", "origin", "GATEWAY_ORIGIN", "http://127.0.0.1:18789"),
            openrouter_api_key=_cfg("openrouter", "apiKey", "OPENROUTER_API_KEY", ""),
            proxy_model=_cfg("openrouter", "model", "PROXY_MODEL", "openai/gpt-oss-120b"),
            hf_token=_cfg("hf", "token", "HUGGINGFACE_HUB_TOKEN", "") or os.getenv("HF_TOKEN", ""),
            proxy_system_prompt_path=os.getenv(
                "PROXY_SYSTEM_PROMPT",
                str(_PROJECT_ROOT / "config" / "PROXY.md"),
            ),
            vad_enabled=os.getenv("VAD_ENABLED", "true").lower() == "true",
            wakeword_enabled=_cfg("voice", "wakewordEnabled", "WAKEWORD_ENABLED", "true").lower() == "true",
            wakeword_threshold=float(_cfg("voice", "wakewordThreshold", "WAKEWORD_THRESHOLD", "0.55")),
            wakeword_active_window_s=float(_cfg("voice", "wakewordActiveWindowMs", "WAKEWORD_ACTIVE_WINDOW_S", "10000")) / 1000.0 if float(_cfg("voice", "wakewordActiveWindowMs", "WAKEWORD_ACTIVE_WINDOW_S", "10000")) > 100 else float(_cfg("voice", "wakewordActiveWindowMs", "WAKEWORD_ACTIVE_WINDOW_S", "10.0")),
            stt_engine=os.getenv("STT_ENGINE", "whisper-small"),
            whisper_model=os.getenv("WHISPER_MODEL", "small"),
            main_history_length=int(_cfg("history", "mainLength", "MAIN_HISTORY_LENGTH", "20")),
            main_history_full_count=int(_cfg("history", "fullCount", "MAIN_HISTORY_FULL_COUNT", "5")),
            tts_enabled=os.getenv("TTS_ENABLED", "true").lower() == "true",
        )
