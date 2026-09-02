import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

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


def build_client(
    tmp_path: Path,
    commerce_base_url: str | None = None,
) -> tuple[TestClient, Path, Path]:
    database = tmp_path / "replay.sqlite3"
    media = tmp_path / "replay.mp4"
    media.write_bytes(b"synthetic-video")
    return TestClient(create_app(database, media, commerce_base_url)), database, media


@contextmanager
def fake_commerce_server(
    entitlements: dict[str, str],
) -> Iterator[tuple[str, list[dict[str, str]]]]:
    requests: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            prefix = "/sandbox/live-commerce/purchases/"
            suffix = "/balances"
            if not self.path.startswith(prefix) or not self.path.endswith(suffix):
                self.send_error(404)
                return
            purchase_ref = unquote(self.path[len(prefix) : -len(suffix)])
            observed = {
                "purchase_ref": purchase_ref,
                "tenant_id": self.headers.get("X-Tenant-Id", ""),
                "family_id": self.headers.get("X-Family-Id", ""),
                "actor_id": self.headers.get("X-Actor-Id", ""),
                "role": self.headers.get("X-Actor-Role", ""),
                "source": self.headers.get("X-Sandbox-Source", ""),
                "fixture_only": self.headers.get("X-Fixture-Only", ""),
            }
            requests.append(observed)
            entitlement = entitlements.get(purchase_ref)
            if (
                entitlement is None
                or observed["tenant_id"] != "tenant.synthetic.alpha"
                or observed["family_id"] != "family.synthetic.alpha"
                or observed["actor_id"] != "actor.synthetic.adult"
                or observed["role"] != "ADULT_VIEWER"
                or observed["source"] != "SANDBOX_SYNTHETIC"
                or observed["fixture_only"] != "true"
            ):
                self.send_error(404)
                return
            payload = json.dumps(
                {
                    "purchase_ref": purchase_ref,
                    "cash": 1200,
                    "settlement": 960,
                    "entitlement": entitlement,
                    "external_effect": False,
                    "source": "SANDBOX_SYNTHETIC",
                    "fixture_only": True,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


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


def test_active_entitlement_binds_capability_and_survives_restart(tmp_path: Path) -> None:
    purchase_ref = "purchase:media/alpha 1"
    entitlements = {purchase_ref: "ACTIVE"}
    with fake_commerce_server(entitlements) as (commerce_url, observed):
        client, database, media = build_client(tmp_path, commerce_url)
        request_headers = {**headers(), "X-Media-Entitlement-Ref": purchase_ref}

        detail = client.get("/sandbox/replays/media.synthetic.1", headers=request_headers)

        assert detail.status_code == 200
        playback_url = detail.json()["playback_url"]
        assert client.get(playback_url).status_code == 200
        restarted = TestClient(create_app(database, media, commerce_url))
        assert restarted.get(playback_url).status_code == 200
        assert observed[-1] == {
            "purchase_ref": purchase_ref,
            "tenant_id": "tenant.synthetic.alpha",
            "family_id": "family.synthetic.alpha",
            "actor_id": "actor.synthetic.adult",
            "role": "ADULT_VIEWER",
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": "true",
        }


def test_revoked_entitlement_invalidates_old_capability(tmp_path: Path) -> None:
    purchase_ref = "purchase:media:revoked"
    entitlements = {purchase_ref: "ACTIVE"}
    with fake_commerce_server(entitlements) as (commerce_url, _):
        client, _, _ = build_client(tmp_path, commerce_url)
        request_headers = {**headers(), "X-Media-Entitlement-Ref": purchase_ref}
        detail = client.get("/sandbox/replays/media.synthetic.1", headers=request_headers)
        old_url = detail.json()["playback_url"]

        entitlements[purchase_ref] = "REVOKED"

        assert client.get(old_url).status_code == 403
        assert (
            client.get("/sandbox/replays/media.synthetic.1", headers=request_headers).status_code
            == 403
        )


def test_entitlement_missing_cross_scope_and_provider_failure_fail_closed(
    tmp_path: Path,
) -> None:
    purchase_ref = "purchase:media:provider"
    entitlements = {purchase_ref: "ACTIVE"}
    with fake_commerce_server(entitlements) as (commerce_url, _):
        client, database, media = build_client(tmp_path, commerce_url)
        replay_url = "/sandbox/replays/media.synthetic.1"
        assert client.get(replay_url, headers=headers()).status_code == 403
        assert (
            client.get(
                replay_url,
                headers={
                    **headers(family="family.synthetic.other"),
                    "X-Media-Entitlement-Ref": purchase_ref,
                },
            ).status_code
            == 403
        )
        detail = client.get(
            replay_url,
            headers={**headers(), "X-Media-Entitlement-Ref": purchase_ref},
        )
        old_url = detail.json()["playback_url"]

    unavailable = TestClient(create_app(database, media, commerce_url))
    assert (
        unavailable.get(
            replay_url,
            headers={**headers(), "X-Media-Entitlement-Ref": purchase_ref},
        ).status_code
        == 503
    )
    assert unavailable.get(old_url).status_code == 503


def test_deleted_capability_returns_410_before_entitlement_check(tmp_path: Path) -> None:
    purchase_ref = "purchase:media:deleted"
    entitlements = {purchase_ref: "ACTIVE"}
    with fake_commerce_server(entitlements) as (commerce_url, _):
        client, database, media = build_client(tmp_path, commerce_url)
        request_headers = {**headers(), "X-Media-Entitlement-Ref": purchase_ref}
        detail = client.get("/sandbox/replays/media.synthetic.1", headers=request_headers)
        old_url = detail.json()["playback_url"]
        deleted = client.post(
            "/sandbox/replays/media.synthetic.1/delete",
            headers=headers(),
            json={
                "deletion_ref": "deletion.entitled",
                "idempotency_key": "delete.entitled",
                "reason": "adult purpose withdrawal",
            },
        )
        assert deleted.status_code == 200

    restarted = TestClient(create_app(database, media, commerce_url))
    assert restarted.get(old_url).status_code == 410


def test_initialise_upgrades_existing_replay_database(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    media = tmp_path / "replay.mp4"
    media.write_bytes(b"synthetic-video")
    with __import__("sqlite3").connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE replay_assets (
                session_ref TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                media_path TEXT NOT NULL,
                capability TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL
            );
            """
        )

    TestClient(create_app(database, media))

    with __import__("sqlite3").connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(replay_assets)")}
    assert {"entitlement_purchase_ref", "actor_id"} <= columns
