from __future__ import annotations

import os

import uvicorn


def main() -> int:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("tax_exam_app.web:app", host=host, port=port, app_dir="src", reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
