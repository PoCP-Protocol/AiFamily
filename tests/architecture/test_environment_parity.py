from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_environment_parity_policy_is_explicit() -> None:
    policy = (REPO_ROOT / "docs/10_engineering/ENVIRONMENT_PARITY.md").read_text(
        encoding="utf-8"
    )
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
    wiring = (REPO_ROOT / "backend/apps/family_api/dev_wiring.py").read_text(
        encoding="utf-8"
    )
    assert "SYNTHETIC" in wiring
    assert "refuses to run outside dev/test" in wiring
    assert "Not authentication" in wiring
    assert "Not persistence" in wiring
