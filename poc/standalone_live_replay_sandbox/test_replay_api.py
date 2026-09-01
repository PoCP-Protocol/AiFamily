from pathlib import Path

from fastapi.testclient import TestClient

from poc.standalone_live_replay_sandbox.replay_api import LINEAGE_REFS, create_app


def headers(
    *, family: str = "family.synthetic.alpha", role: str = "ADULT_VIEWER"
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": "tenant.synthetic.alpha",
        "X-Family-Id": family,
        "X-Actor-Id": "actor.synthetic.adult",
        "X-Actor-Role": role,
    }


def build_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    database = tmp_path / "replay.sqlite3"
    media = tmp_path / "replay.mp4"
    media.write_bytes(b"synthetic-video")
    return TestClient(create_app(database, media)), database, media


def test_replay_plays_then_delete_invalidates_old_url_across_restart(tmp_path: Path) -> None:
    client, database, media = build_client(tmp_path)
    detail = client.get("/sandbox/replays/media.synthetic.1", headers=headers())
    assert detail.status_code == 200
    old_url = detail.json()["playback_url"]
    assert client.get(old_url).status_code == 200

    deleted = client.post(
        "/sandbox/replays/media.synthetic.1/delete",
        headers=headers(),
        json={
            "deletion_ref": "deletion.1",
            "idempotency_key": "delete.1",
            "reason": "adult purpose withdrawal",
        },
    )
    assert deleted.status_code == 200
    assert deleted.json()["affected_refs"] == list(LINEAGE_REFS)
    assert client.get(old_url).status_code == 410

    restarted = TestClient(create_app(database, media))
    assert restarted.get(old_url).status_code == 410
    state = restarted.get("/sandbox/replays/media.synthetic.1", headers=headers())
    assert state.json() == {
        "session_ref": "media.synthetic.1",
        "state": "DELETED",
        "playback_url": None,
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
    }


def test_replay_scope_role_and_auth_fail_closed(tmp_path: Path) -> None:
    client, _, _ = build_client(tmp_path)
    url = "/sandbox/replays/media.synthetic.1"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(family="family.synthetic.other")).status_code == 403
    assert client.get(url, headers=headers(role="CHILD")).status_code == 403


def test_delete_is_idempotent_and_conflicting_key_is_rejected(tmp_path: Path) -> None:
    client, _, _ = build_client(tmp_path)
    command = {
        "deletion_ref": "deletion.2",
        "idempotency_key": "delete.2",
        "reason": "retention expiry",
    }
    url = "/sandbox/replays/media.synthetic.1/delete"
    first = client.post(url, headers=headers(), json=command)
    second = client.post(url, headers=headers(), json=command)
    assert first.json() == second.json()
