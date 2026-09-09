param(
    [string]$FamilyId = "00000000-0000-4000-8000-000000000001",
    [string]$SubjectPersonId = "00000000-0000-4000-8000-000000000002"
)

$ErrorActionPreference = "Stop"

Write-Host "=== F baseline identity ==="
git rev-parse HEAD
git status --short --branch

Write-Host "=== F-01 default create_app / health / readiness / first business paths ==="
$env:AIFAMILY_ENV = "production"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

uv run python -c @"
from fastapi.testclient import TestClient
from backend.apps.family_api.main import create_app

family_id = "$FamilyId"
subject_id = "$SubjectPersonId"
app = create_app()
client = TestClient(app, raise_server_exceptions=False)

print("openapi_paths=", len(app.openapi()["paths"]))
health = client.get("/health")
ready = client.get("/ready")
print("health=", health.status_code, health.text)
print("ready=", ready.status_code, ready.text)

first_business = client.get(f"/families/{family_id}/ui/02/assessment")
print("ui02=", first_business.status_code, first_business.text)
if first_business.status_code >= 500:
    raise SystemExit("FIRST_REAL_FAILURE: default create_app UI-02 HTTP path is unavailable")

signal = client.post(
    f"/families/{family_id}/needs/signals",
    json={"subject_person_id": subject_id, "raw_text": "孩子最近很难开始作业"},
    headers={"Idempotency-Key": "qa-f-baseline-real-http"},
)
print("need_signal=", signal.status_code, signal.text)
if signal.status_code >= 500:
    raise SystemExit("FIRST_REAL_FAILURE: default create_app FamilyNeed HTTP path is unavailable")
"@
