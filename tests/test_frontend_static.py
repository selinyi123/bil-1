"""前端 dist 托管冒烟（无 dist 时 skip，避免强依赖 npm build）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.app import DIST_DIR, app

DIST_INDEX = DIST_DIR / "index.html"
ASSETS_DIR = DIST_DIR / "assets"

pytestmark = pytest.mark.skipif(
    not DIST_INDEX.is_file() or not ASSETS_DIR.is_dir(),
    reason="web/static/dist 未构建，跳过前端静态托管测试",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_spa_index_serves_dist_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "/assets/" in response.text
    assert "no-cache" in response.headers.get("cache-control", "").lower()


def test_legacy_app_js_and_styles_gone(client: TestClient) -> None:
    for path in ("/app.js", "/styles.css"):
        response = client.get(path)
        assert response.status_code == 410
        payload = response.json()
        assert payload.get("error", {}).get("code") == "NOT_FOUND"


def test_favicon_ok(client: TestClient) -> None:
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert "image/svg" in response.headers.get("content-type", "")


def test_hashed_assets_cached(client: TestClient) -> None:
    index = client.get("/")
    assert index.status_code == 200
    marker = '/assets/'
    start = index.text.find(marker)
    assert start >= 0
    end = start
    while end < len(index.text) and index.text[end] not in "\"'":
        end += 1
    asset_path = index.text[start:end]
    response = client.get(asset_path)
    assert response.status_code == 200
    cache = response.headers.get("cache-control", "")
    assert "max-age=31536000" in cache
    assert "immutable" in cache
