"""История болезней: личные записи с датами, комментарием и фото документов."""

from pathlib import Path

import pytest

from app.config import get_settings
from tests.conftest import fid, invite_of, register

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def make(client, h, **body):
    body = {"date_from": "2026-10-01", **body}
    r = client.post("/api/illnesses", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, h, rid, data=JPEG, name="d.jpg"):
    return client.post(f"/api/illnesses/{rid}/documents", headers=h, files={"file": (name, data, "image/jpeg")})


@pytest.fixture(autouse=True)
def own_media(tmp_path, monkeypatch):
    """Своя папка для файлов: тесты проверяют, что на диске ничего не осталось."""
    monkeypatch.setattr(get_settings(), "media_dir", tmp_path)


@pytest.fixture
def me(client):
    h, _ = register(client)
    return h


@pytest.fixture
def me_user(client):
    return register(client)


def test_single_day_and_range(client, me):
    one = make(client, me, title="ОРВИ", comment="температура 38")
    assert (one["date_from"], one["date_to"], one["comment"]) == ("2026-10-01", "2026-10-01", "температура 38")
    rng = make(client, me, date_from="2026-10-05", date_to="2026-10-09")
    assert rng["date_to"] == "2026-10-09"
    ids = [r["id"] for r in client.get("/api/illnesses", headers=me).json()]
    assert ids == [rng["id"], one["id"]]  # новые сверху


@pytest.mark.parametrize("body", [
    {"date_from": "2026-10-05", "date_to": "2026-10-01"},
    {"date_from": "1800-01-01"},
    {"date_from": "2000-01-01", "date_to": "2026-10-01"},
])
def test_bad_period(client, me, body):
    assert client.post("/api/illnesses", headers=me, json=body).status_code == 422


def test_update_dates_and_text(client, me):
    day = make(client, me)
    r = client.patch(f"/api/illnesses/{day['id']}", headers=me, json={"date_from": "2026-10-03"}).json()
    assert (r["date_from"], r["date_to"]) == ("2026-10-03", "2026-10-03")  # один день остаётся одним днём
    r = client.patch(f"/api/illnesses/{day['id']}", headers=me, json={"date_to": "2026-10-07", "comment": " грипп "}).json()
    assert (r["date_to"], r["comment"]) == ("2026-10-07", "грипп")
    assert client.patch(f"/api/illnesses/{day['id']}", headers=me, json={"date_to": "2026-10-01"}).status_code == 422


def test_records_are_private(client, me_user):
    me, user = me_user
    rec = make(client, me, comment="секрет")
    # член той же семьи и посторонний не видят и не меняют запись
    code = invite_of(client, me, fid(user))
    h_mom, _ = register(client, "mom@example.com", "Мама", invite=code)
    h_other, _ = register(client, "other@example.com", "Чужой")
    for h in (h_mom, h_other):
        assert client.get("/api/illnesses", headers=h).json() == []
        assert client.patch(f"/api/illnesses/{rec['id']}", headers=h, json={"comment": "x"}).status_code == 404
        assert client.delete(f"/api/illnesses/{rec['id']}", headers=h).status_code == 404
        assert upload(client, h, rec["id"]).status_code == 404


def test_anonymous_gets_401(client):
    assert client.get("/api/illnesses").status_code == 401
    assert client.post("/api/illnesses", json={"date_from": "2026-10-01"}).status_code == 401
    assert client.get("/api/illnesses/1/documents/1").status_code == 401


def test_photo_upload_serve_delete(client, me):
    rec = make(client, me)
    doc = upload(client, me, rec["id"]).json()["documents"][0]
    r = client.get(doc["url"], headers=me)
    assert r.status_code == 200 and r.content == JPEG
    assert client.get(doc["url"]).status_code == 401  # без входа файл не отдаётся
    left = client.delete(doc["url"], headers=me).json()
    assert left["documents"] == [] and client.get(doc["url"], headers=me).status_code == 404
    assert not list((get_settings().media_dir / "illness").glob("*"))  # файл стёрт с диска


def test_photo_is_private_and_not_in_public_media(client, me):
    rec = make(client, me)
    doc = upload(client, me, rec["id"]).json()["documents"][0]
    h_other, _ = register(client, "other@example.com", "Чужой")
    assert client.get(doc["url"], headers=h_other).status_code == 404
    name = next((get_settings().media_dir / "illness").glob("*")).name
    assert client.get(f"/api/media/{name}").status_code == 404  # публичная раздача медиа его не видит


@pytest.mark.parametrize("data, code", [(PNG, 201), (b"%PDF-1.4 text", 415), (b"GIF89a....", 415), (b"RIFFxxxxWAVE", 415)])
def test_photo_formats(client, me, data, code):
    rec = make(client, me)
    assert upload(client, me, rec["id"], data).status_code == code


def test_photo_size_and_count_limits(client, me, monkeypatch):
    rec = make(client, me)
    monkeypatch.setattr(get_settings(), "max_photo_mb", 0)
    assert upload(client, me, rec["id"]).status_code == 413
    monkeypatch.undo()
    for _ in range(10):
        assert upload(client, me, rec["id"]).status_code == 201
    assert upload(client, me, rec["id"]).status_code == 409


def test_delete_record_removes_files(client, me):
    rec = make(client, me)
    upload(client, me, rec["id"])
    assert client.delete(f"/api/illnesses/{rec['id']}", headers=me).status_code == 204
    assert client.get("/api/illnesses", headers=me).json() == []
    assert not list((get_settings().media_dir / "illness").glob("*"))


def test_delete_account_removes_records_and_files(client):
    h, _ = register(client, "solo@example.com", "Соло")
    rec = make(client, h)
    upload(client, h, rec["id"])
    r = client.request("DELETE", "/api/auth/me", headers=h, json={"password": "kapsula-secret-123"})
    assert r.status_code == 204, r.text
    assert not list((get_settings().media_dir / "illness").glob("*"))


def test_new_records_and_photos_are_plus_only_when_billing_on(client, me):
    from tests.integration.test_cabinet_ops import enable_billing

    rec = make(client, me, title="ОРВИ")
    enable_billing(client, me)
    r = client.post("/api/illnesses", headers=me, json={"date_from": "2026-10-02"})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "illness"
    r = upload(client, me, rec["id"])
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "illness"
    # уже созданное остаётся: смотреть, править и удалять можно и без Плюса
    assert [x["id"] for x in client.get("/api/illnesses", headers=me).json()] == [rec["id"]]
    assert client.patch(f"/api/illnesses/{rec['id']}", headers=me, json={"comment": "лучше"}).status_code == 200
    assert client.delete(f"/api/illnesses/{rec['id']}", headers=me).status_code == 204
