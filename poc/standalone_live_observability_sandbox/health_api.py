"""Read-only runtime health aggregation for isolated live sandboxes."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import uvicorn
from fastapi import Depends, FastAPI

from poc.standalone_live_moderation_sandbox.question_api import (
    SyntheticActor,
    actor_headers,
    require_role,
    require_scope,
)

COMPONENTS = ("media", "interaction", "replay", "commerce")
OPS_TENANT = "tenant.synthetic.alpha"
OPS_FAMILY = "family.synthetic.alpha"
SAFE_SOURCES = {"synthetic", "SANDBOX_SYNTHETIC"}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    status_code: int | None
    payload: Mapping[str, object] | None
    latency_ms: float
    reachable: bool


HealthProbe = Callable[[str, float], ProbeResult]


def create_app(
    component_targets: Mapping[str, str],
    *,
    probe: HealthProbe | None = None,
    timeout_seconds: float = 0.75,
) -> FastAPI:
    if set(component_targets) != set(COMPONENTS):
        raise ValueError("media, interaction, replay, and commerce targets are required")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    health_targets = {
        component: health_url(component_targets[component]) for component in COMPONENTS
    }
    health_probe = probe or http_probe
    app = FastAPI(title="Xiao Ju Deng runtime observability sandbox")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
            "external_effect": False,
        }

    @app.get("/sandbox/live-ops/runtime-snapshot")
    def runtime_snapshot(
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"LIVE_OPERATOR", "HUMAN_MODERATOR"})
        require_scope(actor, OPS_TENANT, OPS_FAMILY)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(COMPONENTS)) as executor:
            futures = {
                component: executor.submit(
                    safely_probe,
                    health_probe,
                    health_targets[component],
                    timeout_seconds,
                )
                for component in COMPONENTS
            }
            components = [
                component_snapshot(
                    component,
                    health_targets[component],
                    futures[component].result(),
                )
                for component in COMPONENTS
            ]
        overall = "READY" if all(item["state"] == "UP" for item in components) else "DEGRADED"
        return {
            "overall": overall,
            "checked_at": datetime.now(UTC).isoformat(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "components": components,
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
            "external_effect": False,
        }

    return app


def safely_probe(probe: HealthProbe, url: str, timeout_seconds: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        return probe(url, timeout_seconds)
    except Exception:
        return ProbeResult(
            status_code=None,
            payload=None,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            reachable=False,
        )


def http_probe(url: str, timeout_seconds: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            status_code = response.status
            body = response.read(65_537)
        if len(body) > 65_536:
            payload = None
        else:
            decoded = json.loads(body.decode("utf-8"))
            payload = decoded if isinstance(decoded, dict) else None
        return ProbeResult(
            status_code=status_code,
            payload=payload,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            reachable=True,
        )
    except HTTPError as exc:
        return ProbeResult(
            status_code=exc.code,
            payload=None,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            reachable=True,
        )
    except (TimeoutError, URLError, OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return ProbeResult(
            status_code=None,
            payload=None,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            reachable=False,
        )


def component_snapshot(component: str, url: str, result: ProbeResult) -> dict[str, object]:
    if not result.reachable:
        state = "DOWN"
    elif valid_health_evidence(component, result):
        state = "UP"
    else:
        state = "UNSAFE"
    detail = {
        "UP": "verified synthetic health",
        "DOWN": "provider unreachable or timed out",
        "UNSAFE": "health evidence rejected",
    }[state]
    return {
        "component": component,
        "url": public_url(url),
        "state": state,
        "latency_ms": round(max(result.latency_ms, 0), 3),
        "detail": detail,
        "external_effect": False,
    }


def valid_health_evidence(component: str, result: ProbeResult) -> bool:
    if result.status_code != 200 or result.payload is None:
        return False
    if component == "media":
        return (
            set(result.payload) == {"source", "fixture_only"}
            and result.payload.get("source") == "synthetic"
            and result.payload.get("fixture_only") is True
        )
    return (
        result.payload.get("status") == "ok"
        and result.payload.get("source") == "SANDBOX_SYNTHETIC"
        and result.payload.get("fixture_only") is True
    )


def health_url(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("component target must be an HTTP URL")
    path = parsed.path.rstrip("/")
    if not path.endswith("/health"):
        path = f"{path}/health"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def public_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or "invalid"
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urlunsplit(SplitResult(parsed.scheme, netloc, parsed.path, "", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-url", required=True)
    parser.add_argument("--interaction-url", required=True)
    parser.add_argument("--replay-url", required=True)
    parser.add_argument("--commerce-url", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    app = create_app(
        {
            "media": args.media_url,
            "interaction": args.interaction_url,
            "replay": args.replay_url,
            "commerce": args.commerce_url,
        }
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
