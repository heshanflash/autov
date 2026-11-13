"""AutoV Trader - configuration loader (.env + runtime settings)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
SETTINGS_FILE = STATE_DIR / "settings.json"

_lock = threading.RLock()


def _load_dotenv(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


_dotenv = _load_dotenv(ROOT / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key) or _dotenv.get(key, default)


def env_float(key: str, default: float) -> float:
    try:
        return float(env(key, str(default)))
    except (TypeError, ValueError):
        return default


def env_int(key: str, default: int) -> int:
    try:
        return int(float(env(key, str(default))))
    except (TypeError, ValueError):
        return default


DEFAULTS = {
    "account_size": env_float("ACCOUNT_SIZE", 1000.0),
    "risk_per_trade_pct": env_float("RISK_PER_TRADE_PCT", 0.5),
    "daily_max_loss_pct": env_float("DAILY_MAX_LOSS_PCT", 1.0),
    "monthly_max_loss_pct": env_float("MONTHLY_MAX_LOSS_PCT", 1.0),
    "max_open_positions": env_int("MAX_OPEN_POSITIONS", 5),
    "max_per_symbol_pct": env_float("MAX_PER_SYMBOL_PCT", 25.0),
    "trading_mode": env("TRADING_MODE", "paper").strip().lower(),
    "data_mode": env("DATA_MODE", "auto").strip().lower(),
    "scan_limit": env_int("SCAN_LIMIT", 40),
    "timeframe": env("TIMEFRAME", "1h"),
    "atr_sl_mult": 1.8,          # stop-loss = entry - ATR * mult
    "rr_targets": [1.5, 3.0, 5.0],  # TP1/TP2/TP3 in R multiples
    "tp_fractions": [0.4, 0.3, 0.3],  # portion closed at each TP
    "min_quote_volume": 5_000_000,   # skip illiquid coins
    "fee_pct": 0.1,              # taker fee % per side
}


def load_settings() -> dict:
    with _lock:
        s = dict(DEFAULTS)
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                for k, v in saved.items():
                    if k in s:
                        s[k] = v
            except (json.JSONDecodeError, OSError):
                pass
        return s


def save_settings(patch: dict) -> dict:
    with _lock:
        s = load_settings()
        for k, v in patch.items():
            if k in DEFAULTS:
                s[k] = v
        STATE_DIR.mkdir(exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
        return s


API_KEY = env("BINANCE_API_KEY", "")
API_SECRET = env("BINANCE_API_SECRET", "")
