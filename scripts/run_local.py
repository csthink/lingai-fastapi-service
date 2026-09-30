#!/usr/bin/env python3
"""Run the isolated local service from this checkout using its virtualenv."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.config import get_settings
import uvicorn


def main():
    settings = get_settings()
    if (settings.host, settings.port) != ("127.0.0.1", 18000):
        raise SystemExit("Local FastAPI must bind 127.0.0.1:18000")
    if (settings.redis_host, settings.redis_port, settings.redis_db, settings.redis_prefix) != ("127.0.0.1", 16379, 1, "lingai-lg020"):
        raise SystemExit("Local Redis must use the isolated 127.0.0.1:16379 database 1")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
