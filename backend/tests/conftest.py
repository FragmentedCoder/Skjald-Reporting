from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import clock
from app.crypto.keys import generate_key
from app.db import get_db, make_engine
from app.main import app
from app.migrate import upgrade
from app.policy import SecurityPolicy
from app.users import create_user

PASSWORD = "lang nok adgangskode til fjorden"


@pytest.fixture
def master_key_path(tmp_path):
    path = tmp_path / "master.key"
    path.write_bytes(generate_key())
    return path


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def engine(data_dir, master_key_path):
    engine = make_engine(data_dir, master_key_path)
    upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(engine):
    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    # https: the session cookie is Secure, so it is only sent back over HTTPS.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


class FrozenClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def frozen_clock(monkeypatch):
    frozen = FrozenClock()
    monkeypatch.setattr(clock, "utcnow", lambda: frozen.now)
    return frozen


@pytest.fixture
def make_user(session):
    def make(username="astrid", password=PASSWORD, **fields):
        user = create_user(
            session, username, fields.pop("display_name", "Astrid Fjeld"), password,
            policy=SecurityPolicy(), **fields,
        )
        session.commit()
        return user

    return make
