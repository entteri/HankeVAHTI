"""Käynnistä HankeVAHTI komennolla `python main.py`."""

import uvicorn

from app.core.config import HOST, LOG_LEVEL, PORT


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level=LOG_LEVEL.lower(), reload=False)
