from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def main():
    from src.core.config import settings
    from src.core.log import configure_logging

    configure_logging(
        level=settings.log_level,
        json_format=settings.log_json,
        service=settings.log_service,
    )

    workers = int(os.getenv("WEB_CONCURRENCY", "4"))
    port = int(os.getenv("PORT", "8000"))
    reload_val = os.getenv("DEBUG", "false").lower() == "true"

    try:
        import gunicorn.app.wsgiapp  # noqa: F401
    except ImportError:
        import uvicorn

        uvicorn.run(
            "src.api.server:app",
            host="0.0.0.0",
            port=port,
            reload=reload_val,
            log_config=None,
        )
        return

    from gunicorn.app.wsgiapp import WSGIApplication

    class StandaloneApplication(WSGIApplication):
        def __init__(self, app_uri: str, options: dict):
            self._app_uri = app_uri
            self._options = options
            super().__init__()

        def load_config(self):
            for key, value in self._options.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self._app_uri

    options = {
        "bind": f"0.0.0.0:{port}",
        "workers": workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "timeout": 120,
        "keepalive": 5,
        "reload": reload_val,
    }
    StandaloneApplication("src.api.server:app", options).run()


if __name__ == "__main__":
    main()
