from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_replay_sandbox.knowledge_api import ReplayProjection, create_app


class ReplayCatalogFixture:
    def __init__(self) -> None:
        self.replays = {
            "replay.synthetic.1": ReplayProjection(
                replay_ref="replay.synthetic.1",
                tenant_id="tenant.synthetic.alpha",
                family_id="family.synthetic.alpha",
                review_state="APPROVED",
            ),
            "replay.synthetic.unreviewed": ReplayProjection(
                replay_ref="replay.synthetic.unreviewed",
                tenant_id="tenant.synthetic.alpha",
                family_id="family.synthetic.alpha",
                review_state="DRAFT",
            ),
        }

    def get(self, replay_ref: str) -> ReplayProjection | None:
        return self.replays.get(replay_ref)


class DeletionProjectionFixture:
    def __init__(self) -> None:
        self.deleted: set[str] = set()

    def is_deleted(self, replay_ref: str, tenant_id: str, family_id: str) -> bool:
        assert tenant_id.startswith("tenant.synthetic")
        assert family_id.startswith("family.synthetic")
        return replay_ref in self.deleted


def headers(
    role: str,
    *,
    tenant: str = "tenant.synthetic.alpha",
    family: str = "family.synthetic.alpha",
    actor: str | None = None,
) -> dict[str, str]:
    identities = {
        "AI_OPERATOR": "actor.synthetic.ai",
        "HUMAN_REVIEWER": "actor.synthetic.reviewer",
        "ADULT_VIEWER": "actor.synthetic.adult",
        "CHILD": "actor.synthetic.child",
        "CREATOR": "actor.synthetic.creator",
    }
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": tenant,
        "X-Family-Id": family,
        "X-Actor-Id": actor or identities[role],
        "X-Actor-Role": role,
    }


def draft_payload(suffix: str = "1") -> dict[str, object]:
    return {
        "knowledge_ref": f"knowledge.synthetic.{suffix}",
        "idempotency_key": f"draft-key.{suffix}",
        "card_title": "先听懂，再回应",
        "card_body": "把孩子的话复述一遍，再表达自己的看法。",
        "chapters": [
            {"title": "识别情绪", "body": "先描述观察到的情绪。"},
            {"title": "确认需求", "body": "用开放问题确认真实需求。"},
        ],
    }


def make_client(tmp_path: Path):
    catalog = ReplayCatalogFixture()
    deletion = DeletionProjectionFixture()
    database = tmp_path / "knowledge.sqlite3"
    client = TestClient(create_app(database, replay_catalog=catalog, deletion_projection=deletion))
    return client, catalog, deletion, database


def create_draft(client: TestClient, suffix: str = "1", replay_ref: str = "replay.synthetic.1"):
    return client.post(
        f"/sandbox/replay-knowledge/replays/{replay_ref}/drafts",
        headers=headers("AI_OPERATOR"),
        json=draft_payload(suffix),
    )


def review(
    client: TestClient,
    *,
    knowledge_ref: str = "knowledge.synthetic.1",
    action: str = "APPROVE",
    decision_key: str = "review-key.1",
    extra: dict[str, object] | None = None,
):
    payload: dict[str, object] = {
        "decision_key": decision_key,
        "action": action,
        "reason": "人工确认内容准确且适合家庭阅读",
    }
    payload.update(extra or {})
    return client.post(
        f"/sandbox/replay-knowledge/items/{knowledge_ref}/review",
        headers=headers("HUMAN_REVIEWER"),
        json=payload,
    )


def test_ai_draft_requires_human_approval_before_adult_can_read(tmp_path: Path) -> None:
    client, _, _, _ = make_client(tmp_path)
    created = create_draft(client)
    assert created.status_code == 202
    assert created.json()["state"] == "DRAFT"
    assert created.json()["fact_write"] is False

    hidden = client.get(
        "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge",
        headers=headers("ADULT_VIEWER"),
    )
    assert hidden.status_code == 200
    assert hidden.json() == []

    approved = review(client)
    assert approved.status_code == 200
    assert approved.json()["state"] == "APPROVED"
    visible = client.get(
        "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge",
        headers=headers("ADULT_VIEWER"),
    )
    assert visible.status_code == 200
    assert visible.json()[0]["chapters"][0]["title"] == "识别情绪"
    assert visible.json()[0]["external_effect"] is False


def test_human_can_edit_or_reject_but_ai_creator_and_child_cannot_review(tmp_path: Path) -> None:
    client, _, _, _ = make_client(tmp_path)
    assert create_draft(client, "edit").status_code == 202
    for role in ("AI_OPERATOR", "CREATOR", "CHILD", "ADULT_VIEWER"):
        denied = client.post(
            "/sandbox/replay-knowledge/items/knowledge.synthetic.edit/review",
            headers=headers(role),
            json={
                "decision_key": f"denied.{role}",
                "action": "APPROVE",
                "reason": "不得自动批准",
            },
        )
        assert denied.status_code == 403

    edited = review(
        client,
        knowledge_ref="knowledge.synthetic.edit",
        action="EDIT",
        decision_key="review.edit",
        extra={
            "edited_card_title": "人工修订：先共情，再讨论",
            "edited_chapters": [{"title": "共情", "body": "先确认孩子的感受。"}],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["state"] == "APPROVED"
    assert edited.json()["card_title"].startswith("人工修订")

    assert create_draft(client, "reject").status_code == 202
    rejected = review(
        client,
        knowledge_ref="knowledge.synthetic.reject",
        action="REJECT",
        decision_key="review.reject",
    )
    assert rejected.json()["state"] == "REJECTED"
    visible = client.get(
        "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge",
        headers=headers("ADULT_VIEWER"),
    ).json()
    assert {item["knowledge_ref"] for item in visible} == {"knowledge.synthetic.edit"}


def test_adult_bookmark_is_actor_scoped_and_idempotent(tmp_path: Path) -> None:
    client, _, _, _ = make_client(tmp_path)
    assert create_draft(client).status_code == 202
    assert review(client).status_code == 200
    url = "/sandbox/replay-knowledge/items/knowledge.synthetic.1/bookmarks"
    payload = {"bookmark_ref": "bookmark.synthetic.1", "idempotency_key": "bookmark-key.1"}
    first = client.post(url, headers=headers("ADULT_VIEWER"), json=payload)
    assert first.status_code == 201
    assert first.json()["actor_id"] == "actor.synthetic.adult"
    assert first.json()["external_effect"] is False
    assert client.post(url, headers=headers("ADULT_VIEWER"), json=payload).json() == first.json()

    another_adult = headers("ADULT_VIEWER", actor="actor.synthetic.other")
    assert client.get("/sandbox/replay-knowledge/bookmarks", headers=another_adult).json() == []
    own = client.get("/sandbox/replay-knowledge/bookmarks", headers=headers("ADULT_VIEWER")).json()
    assert [item["bookmark_ref"] for item in own] == ["bookmark.synthetic.1"]

    conflict = {**payload, "bookmark_ref": "bookmark.synthetic.changed"}
    assert client.post(url, headers=headers("ADULT_VIEWER"), json=conflict).status_code == 409


def test_draft_and_review_idempotency_conflicts_fail_closed(tmp_path: Path) -> None:
    client, _, _, _ = make_client(tmp_path)
    first = create_draft(client)
    assert first.status_code == 202
    assert create_draft(client).json() == first.json()
    changed = draft_payload()
    changed["card_body"] = "相同键，不同内容"
    assert (
        client.post(
            "/sandbox/replay-knowledge/replays/replay.synthetic.1/drafts",
            headers=headers("AI_OPERATOR"),
            json=changed,
        ).status_code
        == 409
    )

    first_review = review(client)
    assert first_review.status_code == 200
    assert review(client).json() == first_review.json()
    conflicting_review = review(client, action="REJECT")
    assert conflicting_review.status_code == 409


def test_cross_scope_missing_unreviewed_and_unapproved_fail_closed(tmp_path: Path) -> None:
    client, _, _, _ = make_client(tmp_path)
    other_family = headers("AI_OPERATOR", family="family.synthetic.other")
    assert (
        client.post(
            "/sandbox/replay-knowledge/replays/replay.synthetic.1/drafts",
            headers=other_family,
            json=draft_payload(),
        ).status_code
        == 403
    )
    assert create_draft(client, "missing", "replay.synthetic.missing").status_code == 404
    assert create_draft(client, "unreviewed", "replay.synthetic.unreviewed").status_code == 404

    assert create_draft(client).status_code == 202
    unapproved_bookmark = client.post(
        "/sandbox/replay-knowledge/items/knowledge.synthetic.1/bookmarks",
        headers=headers("ADULT_VIEWER"),
        json={"bookmark_ref": "bookmark.draft", "idempotency_key": "bookmark.draft"},
    )
    assert unapproved_bookmark.status_code == 404


def test_sqlite_restart_restores_review_and_bookmark(tmp_path: Path) -> None:
    client, catalog, deletion, database = make_client(tmp_path)
    assert create_draft(client).status_code == 202
    assert review(client).status_code == 200
    payload = {"bookmark_ref": "bookmark.restart", "idempotency_key": "bookmark.restart"}
    assert (
        client.post(
            "/sandbox/replay-knowledge/items/knowledge.synthetic.1/bookmarks",
            headers=headers("ADULT_VIEWER"),
            json=payload,
        ).status_code
        == 201
    )

    restarted = TestClient(
        create_app(database, replay_catalog=catalog, deletion_projection=deletion)
    )
    knowledge = restarted.get(
        "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge",
        headers=headers("ADULT_VIEWER"),
    ).json()
    bookmarks = restarted.get(
        "/sandbox/replay-knowledge/bookmarks", headers=headers("ADULT_VIEWER")
    ).json()
    assert knowledge[0]["state"] == "APPROVED"
    assert bookmarks[0]["bookmark_ref"] == "bookmark.restart"


def test_canonical_deletion_hides_everything_and_tombstone_prevents_resurrection(
    tmp_path: Path,
) -> None:
    client, catalog, deletion, database = make_client(tmp_path)
    assert create_draft(client).status_code == 202
    assert review(client).status_code == 200
    bookmark_url = "/sandbox/replay-knowledge/items/knowledge.synthetic.1/bookmarks"
    assert (
        client.post(
            bookmark_url,
            headers=headers("ADULT_VIEWER"),
            json={"bookmark_ref": "bookmark.deleted", "idempotency_key": "bookmark.deleted"},
        ).status_code
        == 201
    )

    deletion.deleted.add("replay.synthetic.1")
    knowledge_url = "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge"
    assert client.get(knowledge_url, headers=headers("ADULT_VIEWER")).status_code == 410
    assert (
        client.get("/sandbox/replay-knowledge/bookmarks", headers=headers("ADULT_VIEWER")).json()
        == []
    )
    assert (
        client.post(
            bookmark_url,
            headers=headers("ADULT_VIEWER"),
            json={"bookmark_ref": "bookmark.new", "idempotency_key": "bookmark.new"},
        ).status_code
        == 410
    )
    assert (
        review(
            client,
            knowledge_ref="knowledge.synthetic.1",
            decision_key="review.after-delete",
        ).status_code
        == 410
    )

    deletion.deleted.clear()
    restarted = TestClient(
        create_app(database, replay_catalog=catalog, deletion_projection=deletion)
    )
    assert restarted.get(knowledge_url, headers=headers("ADULT_VIEWER")).status_code == 410
    assert (
        restarted.get("/sandbox/replay-knowledge/bookmarks", headers=headers("ADULT_VIEWER")).json()
        == []
    )


def test_synthetic_auth_and_projection_failure_are_closed(tmp_path: Path) -> None:
    client, _, deletion, _ = make_client(tmp_path)
    url = "/sandbox/replay-knowledge/replays/replay.synthetic.1/knowledge"
    assert client.get(url).status_code == 401
    unsafe = headers("ADULT_VIEWER")
    unsafe["X-Actor-Id"] = "real.actor"
    assert client.get(url, headers=unsafe).status_code == 403

    class BrokenCatalog:
        def get(self, replay_ref: str) -> ReplayProjection | None:
            raise RuntimeError("projection down")

    broken = TestClient(
        create_app(
            tmp_path / "broken.sqlite3",
            replay_catalog=BrokenCatalog(),
            deletion_projection=deletion,
        )
    )
    assert broken.get(url, headers=headers("ADULT_VIEWER")).status_code == 503


def test_bookmark_listing_does_not_mask_projection_failure_as_empty(tmp_path: Path) -> None:
    client, _, deletion, database = make_client(tmp_path)
    assert create_draft(client).status_code == 202
    assert review(client).status_code == 200
    assert (
        client.post(
            "/sandbox/replay-knowledge/items/knowledge.synthetic.1/bookmarks",
            headers=headers("ADULT_VIEWER"),
            json={
                "bookmark_ref": "bookmark.projection-failure",
                "idempotency_key": "bookmark.projection-failure",
            },
        ).status_code
        == 201
    )

    class BrokenCatalog:
        def get(self, replay_ref: str) -> ReplayProjection | None:
            raise RuntimeError("projection down")

    broken = TestClient(
        create_app(
            database,
            replay_catalog=BrokenCatalog(),
            deletion_projection=deletion,
        )
    )
    assert (
        broken.get(
            "/sandbox/replay-knowledge/bookmarks",
            headers=headers("ADULT_VIEWER"),
        ).status_code
        == 503
    )


@pytest.mark.parametrize("field", ["card_title", "card_body"])
def test_blank_generated_content_is_rejected(tmp_path: Path, field: str) -> None:
    client, _, _, _ = make_client(tmp_path)
    payload = draft_payload()
    payload[field] = "   "
    result = client.post(
        "/sandbox/replay-knowledge/replays/replay.synthetic.1/drafts",
        headers=headers("AI_OPERATOR"),
        json=payload,
    )
    assert result.status_code == 422
