import pytest
from sqlalchemy.orm import Session

from app.crypto.keys import generate_key
from app.db import make_engine
from app.migrate import upgrade


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
    with Session(engine) as session:
        yield session
