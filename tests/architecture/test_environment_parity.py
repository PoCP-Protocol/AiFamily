from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_environment_parity_policy_is_explicit() -> None:
    policy = (REPO_ROOT / "docs/10_engineering/ENVIRONMENT_PARITY.md").read_text(encoding="utf-8")
    required_phrases = (
        "开发、测试、生产三个环境必须是**功能完整、彼此行为等价**的环境",
        "开发/测试环境 ≠ 生产功能的简化版",
        "禁止以下实现方式",
        "if environment == test",
        "同一组权限、家庭隔离、Consent、审计和幂等用例",
        "数据是模拟的",
        "功能被删减",
    )
    for phrase in required_phrases:
        assert phrase in policy


def test_development_wiring_declares_its_synthetic_boundary() -> None:
    wiring = (REPO_ROOT / "backend/apps/family_api/dev_wiring.py").read_text(encoding="utf-8")
    assert "SYNTHETIC" in wiring
    assert "refuses to run outside dev/test" in wiring
    assert "Not authentication" in wiring
    assert "Not persistence" in wiring


def test_ci_does_not_inject_runtime_database_url_into_full_test_suite() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["architecture"]
    job_environment = job["env"]
    assert "AIFAMILY_TEST_DATABASE_URL" in job_environment
    assert "DATABASE_URL" not in job_environment

    steps = {step["name"]: step for step in job["steps"]}
    dev_database_name = "aifamily_dev_claude"
    assert (
        dev_database_name
        in steps["Create dev-wiring database (separate from aifamily_test)"]["run"]
    )
    assert steps["Apply Alembic migrations to dev-wiring database (head)"]["env"][
        "DATABASE_URL"
    ].endswith(f"/{dev_database_name}")
    assert "DATABASE_URL" not in steps["Full test suite"].get("env", {})
