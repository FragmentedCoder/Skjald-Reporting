import json
import os
import shutil
import subprocess
from datetime import UTC, datetime

import pytest
import sqlcipher3
from sqlalchemy import select, text

from app import backups, jobs
from app.audit import AuditEntry
from app.backups import BackupError, Target
from app.crypto.key_files import load_or_create_backup_key, load_or_create_database_key
from app.crypto.keys import from_kit_text, to_kit_text
from app.roles import Role, grant_role
from tests.conftest import PASSWORD

BACKUPS = "/api/admin/backups"
needs_restic = pytest.mark.skipif(shutil.which("restic") is None, reason="restic isn't installed")


# What a target means


def test_each_kind_of_target_is_a_restic_repository() -> None:
    assert backups.repository(Target()) == "/backups/restic"
    smb = Target(kind="smb", smb_host="nas.local", smb_share="backup", smb_path="/skjald/",
                 smb_username="skjald")
    assert backups.repository(smb) == "rclone:skjaldsmb:backup/skjald"
    s3 = Target(kind="s3", s3_endpoint="https://s3.example.com/", s3_bucket="vault",
                s3_access_key_id="AKIA")
    assert backups.repository(s3) == "s3:https://s3.example.com/vault/skjald"


def test_secrets_go_to_restic_as_environment_never_as_arguments() -> None:
    s3 = Target(kind="s3", s3_endpoint="https://s3.example.com", s3_bucket="vault",
                s3_access_key_id="AKIA", s3_region="eu-north-1")
    env = backups.environment(s3, {"s3_secret_access_key": "s3cret"}, "KEYTEXT")
    assert env["AWS_SECRET_ACCESS_KEY"] == "s3cret" and env["RESTIC_PASSWORD"] == "KEYTEXT"
    assert env["AWS_DEFAULT_REGION"] == "eu-north-1"


def test_the_repository_password_is_the_recovery_kits_backup_key() -> None:
    key = bytes(range(32))
    kit = to_kit_text(key)
    assert " " in kit
    assert backups.password(key) == kit.replace(" ", "")
    assert from_kit_text(backups.password(key)) == key


def test_restic_complaints_are_said_plainly() -> None:
    assert "another key" in backups._explain(12, "Fatal: wrong password or no key found")
    assert backups._explain(1, "dial tcp: lookup nas: no such host") == (
        "The backup target can't be reached.")
    assert "refused" in backups._explain(1, "Access Denied (403)")
    assert backups._explain(1, "Fatal: something odd\n") == "Fatal: something odd"


def test_a_target_says_what_it_still_needs() -> None:
    assert Target().missing() is None
    assert "server" in (Target(kind="smb").missing() or "")
    assert "bucket" in (Target(kind="s3", s3_endpoint="https://s3.example.com").missing() or "")
    with pytest.raises(ValueError):
        Target(kind="smb", smb_share="a share; rm -rf /")


# When


def test_the_nightly_backup_is_due_from_its_hour(frozen_clock, session) -> None:
    morning = datetime(2026, 10, 24, 1, 30, tzinfo=UTC)
    assert backups._nightly(session, morning) == []
    late = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)
    assert backups._nightly(session, late) == [("backup", "backup/2026-10-24", {})]
    backups.save_target(session, Target(kind="off"))
    assert backups._nightly(session, late) == []


def test_the_restore_test_waits_for_a_backup(frozen_clock, session) -> None:
    assert backups._weekly_restore_test(session, frozen_clock.now) == []
    job = jobs.enqueue(session, "backup")
    jobs.finish(session, job, {})
    assert backups._weekly_restore_test(session, frozen_clock.now) == [
        ("restore_test", "restore_test/2026-W43", {})]


def test_the_next_backup_time() -> None:
    now = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)
    target = Target(hour=2)
    assert backups.next_backup(target, False, now) == datetime(2026, 10, 24, 2, tzinfo=UTC)
    assert backups.next_backup(target, True, now) == datetime(2026, 10, 25, 2, tzinfo=UTC)
    afternoon = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
    assert backups.next_backup(target, False, afternoon) == afternoon  # missed: due now
    assert backups.next_backup(Target(kind="off"), False, now) is None


# Backing up and restoring, with restic itself


@pytest.fixture
def local_repository(tmp_path, monkeypatch, data_dir, engine):
    from app.settings import settings

    monkeypatch.setattr(settings, "data_dir", str(data_dir))
    repo = tmp_path / "repo"
    monkeypatch.setattr(backups, "LOCAL_REPOSITORY", str(repo))
    return repo


def run(session, kind):
    job = jobs.enqueue(session, kind)
    session.commit()
    jobs.run_one(session)
    return job


@needs_restic
def test_a_backup_restores_and_checks_out(local_repository, session, make_user, data_dir,
                                          master_key_path) -> None:
    grant_role(session, make_user(), Role.TECHNICIAN, actor=None, ip=None)
    session.commit()

    backup = run(session, "backup")
    assert backup.state == "done", backup.error
    assert backup.outcome()["repository_made"] and backup.outcome()["files"] >= 3
    tested = run(session, "restore_test")
    assert tested.state == "done", tested.error
    assert tested.outcome()["audit_entries"] >= 1
    actions = list(session.scalars(select(AuditEntry.action).where(
        AuditEntry.action.like("backup.%"))))
    assert actions == ["backup.completed", "backup.restore_tested"]

    # The recovery kit's backup key, as written there, opens the repository.
    kit = to_kit_text(load_or_create_backup_key(data_dir, master_key_path))
    listed = subprocess.run(
        ["restic", "snapshots", "--json"], capture_output=True, text=True, check=True,
        env={"RESTIC_REPOSITORY": str(local_repository), "PATH": os.environ["PATH"],
             "RESTIC_PASSWORD": kit.replace(" ", "")})
    assert len(json.loads(listed.stdout)) == 1


@needs_restic
def test_a_repository_made_with_another_key_is_refused_plainly(local_repository,
                                                              session) -> None:
    subprocess.run(["restic", "init"], capture_output=True, check=True, env={
        "RESTIC_REPOSITORY": str(local_repository), "RESTIC_PASSWORD": "someone else's",
        "PATH": os.environ["PATH"]})
    backup = run(session, "backup")
    assert backup.state == "queued" and "another key" in backup.error
    failed = session.scalar(select(AuditEntry).where(AuditEntry.action == "backup.failed"))
    assert "another key" in failed.details


def test_a_tampered_copy_fails_the_restore_check(local_repository, session, data_dir,
                                                 master_key_path, tmp_path) -> None:
    from app import audit

    audit.append(session, "test.entry", details={"n": 1})
    session.commit()
    folder = tmp_path / "copy"
    schema = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    backups._stage(folder, {"schema": schema, "audit_entries": 1})
    assert backups.check_restored(folder)["audit_entries"] == 1

    key = load_or_create_database_key(data_dir, master_key_path)
    copy = sqlcipher3.connect(str(folder / "skjald.db"))
    copy.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    # Someone with the file and the key can drop the triggers that keep the log
    # append-only; the hash chain still shows the change.
    for (name,) in copy.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit_log'"
    ).fetchall():
        copy.execute(f"DROP TRIGGER {name}")
    copy.execute("UPDATE audit_log SET details = '{\"n\":2}'")
    copy.commit()
    copy.close()
    with pytest.raises(BackupError, match="audit log breaks"):
        backups.check_restored(folder)


# The admin panel


@pytest.fixture
def as_admin(admin):
    return admin[1]


def test_the_status_tells_where_when_and_how_it_went(client, as_admin) -> None:
    status = client.get(BACKUPS, headers=as_admin).json()
    assert status["target"]["kind"] == "local" and status["repository"] == "/backups/restic"
    assert status["last_backup"] is None and status["runs"] == []
    assert status["next_backup_at"] is not None


def test_changing_where_backups_go_needs_a_fresh_confirmation(client, as_admin,
                                                              session) -> None:
    s3 = {"kind": "s3", "s3_endpoint": "https://s3.example.com", "s3_bucket": "vault",
          "s3_access_key_id": "AKIA", "s3_secret_access_key": "s3cret", "hour": 3}
    refused = client.put(BACKUPS, headers=as_admin, json=s3)
    assert refused.headers["X-Skjald-Reason"] == "step_up_required"
    assert "where backups go" in refused.json()["detail"]
    client.post("/api/auth/confirm-password", headers=as_admin, json={"password": PASSWORD})
    saved = client.put(BACKUPS, headers=as_admin, json=s3)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["s3_secret_set"] and "s3cret" not in saved.text
    assert body["repository"] == "s3:https://s3.example.com/vault/skjald"
    # The hour alone changes without asking again, and the secret is kept.
    later = client.put(BACKUPS, headers=as_admin, json={**s3, "s3_secret_access_key": None,
                                                         "hour": 4})
    assert later.status_code == 200 and later.json()["s3_secret_set"]
    logged = session.scalars(select(AuditEntry.details).where(
        AuditEntry.action == "backup.settings_changed")).all()
    assert logged == ['{"hour":3,"keep_days":90,"kind":"s3"}',
                      '{"hour":4,"keep_days":90,"kind":"s3"}']
    assert all("s3cret" not in d for d in logged)


def test_a_target_without_what_it_needs_is_refused(client, as_admin) -> None:
    refused = client.put(BACKUPS, headers=as_admin, json={"kind": "smb", "smb_host": "nas"})
    assert refused.status_code == 400 and "share name" in refused.json()["detail"]


def test_running_now_queues_one_job_at_a_time(client, as_admin, session) -> None:
    first = client.post(f"{BACKUPS}/run/backup", headers=as_admin).json()
    again = client.post(f"{BACKUPS}/run/backup", headers=as_admin).json()
    assert first["id"] == again["id"] and first["state"] == "queued"
    assert client.get(f"{BACKUPS}/runs/{first['id']}", headers=as_admin).json()["kind"] == "backup"
    assert client.post(f"{BACKUPS}/run/format_disk", headers=as_admin).status_code == 422


def test_only_administrators_reach_backups(client, make_user, session, full_session) -> None:
    manager = make_user("mona")
    grant_role(session, manager, Role.MANAGER, actor=None, ip=None)
    session.commit()
    assert client.get(BACKUPS, headers=full_session(manager)).status_code == 403


@needs_restic
def test_a_restore_puts_the_backup_back_and_keeps_what_was_there(
    local_repository, session, engine, make_user, data_dir, master_key_path
) -> None:
    from pathlib import Path

    from sqlalchemy.orm import Session

    from app.db import make_engine
    from app.restore import restore
    from app.users import User

    make_user("before")
    assert run(session, "backup").state == "done"
    make_user("after")
    session.commit()
    session.close()
    engine.dispose()  # Skjald is stopped

    key_text = backups.password(load_or_create_backup_key(data_dir, master_key_path))
    found = restore(backups.environment(Target(), {}, key_text), "latest", data_dir)
    assert Path(found["kept"], "skjald.db").exists()
    restored = make_engine(data_dir, master_key_path)
    with Session(restored) as db:
        usernames = set(db.scalars(select(User.username)))
        # The copy was made while its own backup job ran; nothing runs it now.
        own = db.scalar(select(jobs.Job).where(jobs.Job.kind == "backup"))
    restored.dispose()
    assert "before" in usernames and "after" not in usernames
    assert own.state == "failed" and "the restore ended it" in own.error


@needs_restic
def test_a_backup_from_before_a_rotation_restores_with_its_master_key(
    local_repository, session, engine, make_user, data_dir, master_key_path
) -> None:
    from sqlalchemy.orm import Session

    from app.crypto import rotation
    from app.db import make_engine
    from app.restore import restore
    from app.users import User

    make_user("before")
    old = master_key_path.read_bytes()
    backup = run(session, "backup")
    assert backup.state == "done", backup.error
    session.close()
    engine.dispose()
    rotated = rotation.rotate(data_dir, master_key_path)

    # The weekly test can't ask for the old key: it says why it can't check this one.
    with Session(make_engine(data_dir, master_key_path)) as db:
        tested = run(db, "restore_test")
        assert tested.state == "queued"
        assert f"made under master key {rotation.key_id(old)}" in tested.error
        assert rotated.new_id in tested.error

    key_text = backups.password(load_or_create_backup_key(data_dir, master_key_path))
    env = backups.environment(Target(), {}, key_text)
    asked: list[str | None] = []

    def wrong(made_under):
        asked.append(made_under)
        return bytes(32)

    with pytest.raises(BackupError, match="doesn't open this backup either"):
        restore(env, "latest", data_dir, older_key=wrong)
    assert asked == [rotation.key_id(old)]

    found = restore(env, "latest", data_dir, older_key=lambda made_under: old)
    assert found["audit_entries"] >= 1
    restored = make_engine(data_dir, master_key_path)  # the server's current master key
    with Session(restored) as db:
        assert "before" in set(db.scalars(select(User.username)))
        moved = db.scalar(select(AuditEntry).where(
            AuditEntry.action == "keys.restored_under_current_master_key"))
        assert moved is not None and rotated.new_id in moved.details
    restored.dispose()


def test_a_damaged_copy_fails_the_integrity_check(local_repository, session, tmp_path) -> None:
    from app import audit

    for n in range(200):  # enough pages that the last isn't the schema's
        audit.append(session, "test.entry", details={"n": n, "pad": "x" * 200})
    session.commit()
    folder = tmp_path / "copy"
    schema = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    backups._stage(folder, {"schema": schema, "audit_entries": 200})
    database = folder / "skjald.db"
    data = bytearray(database.read_bytes())
    data[-2000:-1000] = bytes(1000)  # a page near the end, zeroed
    database.write_bytes(bytes(data))
    with pytest.raises(BackupError, match="integrity check"):
        backups.check_restored(folder)
