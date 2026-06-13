from __future__ import annotations

from pathlib import Path


async def test_get_settings_returns_current(client):
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "data_root" in body
    assert body["pace_unit"] == "chars_per_hour"


async def test_patch_settings_updates_value(client):
    r = await client.patch("/api/settings", json={"pace_unit": "pages_per_hour"})
    assert r.status_code == 200
    assert r.json()["pace_unit"] == "pages_per_hour"


async def test_post_setup_initializes_data_root(client, tmp_path: Path):
    new_root = tmp_path / "fresh_root"
    r = await client.post("/api/setup", json={"data_root": str(new_root)})
    assert r.status_code == 200
    assert r.json()["data_root"] == str(new_root)
    assert (new_root / "books").is_dir()
    assert (new_root / "exports").is_dir()


async def test_post_setup_rejects_blank_data_root(client):
    r = await client.post("/api/setup", json={"data_root": "  "})
    assert r.status_code == 400


async def test_patch_settings_rejects_unknown_key(client):
    r = await client.patch("/api/settings", json={"nope": "bar"})
    assert r.status_code == 400


async def test_patch_settings_accepts_all_pace_units(client):
    for unit in (
        "chars_per_hour",
        "pages_per_hour",
        "words_per_hour",
        "sec_per_100_pages",
    ):
        r = await client.patch("/api/settings", json={"pace_unit": unit})
        assert r.status_code == 200, r.text
        assert r.json()["pace_unit"] == unit


async def test_patch_settings_rejects_invalid_pace_unit(client):
    r = await client.patch("/api/settings", json={"pace_unit": "invalid"})
    assert r.status_code == 400


async def test_patch_settings_rejects_non_positive_interval(client):
    r = await client.patch("/api/settings", json={"snapshot_interval_seconds": 0})
    assert r.status_code == 400


async def test_patch_settings_rejects_non_integer_interval(client):
    r = await client.patch("/api/settings", json={"reaper_interval_seconds": "abc"})
    assert r.status_code == 400
