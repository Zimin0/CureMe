import os

os.environ["CUREME_REMOTE_LOOKUP"] = "false"
os.environ["CUREME_FRONTEND_DIST"] = "/nonexistent"
import tempfile
os.environ["CUREME_MEDIA_DIR"] = tempfile.mkdtemp()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db, make_engine
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, email="nikita@example.com", name="Никита", invite=None):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "secret123", "invite_code": invite})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]
