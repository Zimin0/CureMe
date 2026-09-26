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
