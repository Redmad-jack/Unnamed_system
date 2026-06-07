from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "src" / "conscious_entity" / "interfaces" / "static"
SOURCE_DIR = ROOT / "web" / "arts"
DIST_DIR = ROOT / "tmp" / "netlify-arts-dist"
ARTS_DIR = DIST_DIR / "arts"


def main() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    (ARTS_DIR / "vendor").mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_DIR / "index.html", ARTS_DIR / "index.html")
    shutil.copy2(SOURCE_DIR / "arts.css", ARTS_DIR / "arts.css")
    shutil.copy2(SOURCE_DIR / "app.js", ARTS_DIR / "app.js")
    shutil.copy2(STATIC_DIR / "art.css", ARTS_DIR / "art.css")
    for filename in [
        "react.production.min.js",
        "react-dom.production.min.js",
        "three.module.js",
    ]:
        shutil.copy2(STATIC_DIR / "vendor" / filename, ARTS_DIR / "vendor" / filename)

    art_js = (STATIC_DIR / "art.js").read_text(encoding="utf-8")
    (ARTS_DIR / "art-surface.js").write_text(transform_art_js(art_js), encoding="utf-8")
    (ARTS_DIR / "config.js").write_text(build_config_js(), encoding="utf-8")


def transform_art_js(source: str) -> str:
    source = source.replace(
        'const THREE_MODULE_PATH = "/static/vendor/three.module.js";',
        'const THREE_MODULE_PATH = "/arts/vendor/three.module.js";',
    )
    source = source.replace(
        """  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }""",
        """  async function fetchJSON(url) {
    if (window.StrangerArts && typeof window.StrangerArts.fetchSurfaceJSON === "function") {
      return window.StrangerArts.fetchSurfaceJSON(url);
    }
    const response = await fetch(url);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }""",
    )
    return source


def build_config_js() -> str:
    config = {
        "renderBaseUrl": os.getenv("STRANGER_RENDER_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
    }
    return "window.STRANGER_ARTS_CONFIG = " + json.dumps(config, ensure_ascii=False) + ";\n"


if __name__ == "__main__":
    main()
