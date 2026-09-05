from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "governance/AI_USE_CASE_REGISTRY.yaml"


def _load_registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def test_ai_use_case_registry_is_explicit_and_machine_readable() -> None:
    data = _load_registry()
    assert data["schema_version"] == "1.0"
    assert data["canonical_scope"]
    assert data["use_cases"]
    assert data["agents"]
    assert data["tools"]


def test_registry_declares_the_five_named_agents() -> None:
    data = _load_registry()
    agent_ids = {agent["id"] for agent in data["agents"]}
    assert agent_ids == {
        "parent_advisor",
        "child_coach",
        "teaching_assistant",
        "growth_planner",
        "operations_assistant",
    }
    assert all(agent["may_mutate_business_state"] is False for agent in data["agents"])


def test_registry_links_use_cases_agents_tools_and_versioned_outputs() -> None:
    data = _load_registry()
    enum = data["enums"]
    agent_ids = {agent["id"] for agent in data["agents"]}
    tool_ids = {tool["id"] for tool in data["tools"]}
    use_case_ids = {use_case["id"] for use_case in data["use_cases"]}

    assert len(use_case_ids) >= 14
    for use_case in data["use_cases"]:
        for key in (
            "business_process_ids",
            "agent",
            "capability_route",
            "input_evidence",
            "output_type",
            "output_schema_ref",
            "prompt_ref",
            "knowledge_refs",
            "allowed_tools",
            "risk_level",
            "human_gate",
            "named_action_owner",
            "status",
            "evidence_refs",
        ):
            assert use_case.get(key), f"{use_case['id']} missing {key}"
        assert use_case["agent"] in agent_ids
        assert set(use_case["allowed_tools"]).issubset(tool_ids)
        assert use_case["output_type"] in enum["output_type"]
        assert use_case["risk_level"] in enum["risk_level"]
        assert use_case["human_gate"] in enum["human_gate_mode"]
        assert use_case["status"] in enum["status"]
        assert use_case["risk_level"] != "PROHIBITED"
        assert use_case["human_gate"] != "NOT_REQUIRED" or use_case["risk_level"] == "LOW"


def test_registry_declares_principal_as_the_cross_cutting_ai_control_plane() -> None:
    data = _load_registry()
    principal = data["principal"]
    assert principal["id"] == "famili_principal"
    assert principal["soul_id"] == "FAMILI_PRINCIPAL_SISTERLY_MENTOR"
    assert principal["method_inheritance"] is True
    assert principal["identity_cloning"] is False
    assert principal["may_mutate_business_state"] is False
    assert set(principal["allowed_agents"]) == {
        "parent_advisor",
        "child_coach",
        "teaching_assistant",
        "growth_planner",
        "operations_assistant",
    }
    assert "service_product_architect" in principal["profiles"]
    assert "knowledge_steward" in principal["profiles"]


def test_registry_contains_service_design_and_principal_use_cases() -> None:
    data = _load_registry()
    use_cases = {item["id"]: item for item in data["use_cases"]}
    for use_case_id in (
        "service_product_discovery",
        "service_product_composition",
        "service_product_compile",
        "service_product_simulation",
        "knowledge_stewardship",
        "principal_knowledge_answer",
    ):
        use_case = use_cases[use_case_id]
        assert use_case["principal_profile"]
        assert use_case["status"] == "PLANNED"
        assert use_case["agent"] in {agent["id"] for agent in data["agents"]}


def test_registry_tools_are_read_or_draft_only_and_reference_known_agents() -> None:
    data = _load_registry()
    agent_ids = {agent["id"] for agent in data["agents"]}
    for tool in data["tools"]:
        assert tool["mutates_business_state"] is False
        assert set(tool["allowed_agents"]).issubset(agent_ids)
        assert tool["human_gate"] in data["enums"]["human_gate_mode"]
        assert tool["status"] in data["enums"]["status"]
        assert tool["evidence_refs"]


def test_registry_runtime_invariants_enforce_governed_ai_boundary() -> None:
    data = _load_registry()
    invariants = data["runtime_invariants"]
    assert invariants["single_model_boundary"] == "backend/intelligence/model_gateway"
    assert invariants["ai_runtime_root"] == "backend/intelligence"
    assert invariants["may_mutate_business_state"] is False
    assert invariants["canonical_write_requires_named_action"] is True
    assert invariants["high_impact_requires_human_gate"] is True
    assert invariants["minor_commercial_profiling"] == "PROHIBITED"
    assert invariants["family_total_score_or_ranking"] == "PROHIBITED"
    assert invariants["environment_functional_parity"] is True


def test_registry_has_no_provider_specific_use_case_contract() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    assert "provider_id:" not in text
    assert "model_name:" not in text
    assert "D:\\family-ai" not in text
    assert ("50_" + "开发_dev") not in text


def test_registry_is_honest_about_current_maturity() -> None:
    data = _load_registry()
    experiment_use_cases = {
        item["id"] for item in data["use_cases"] if item["status"] == "EXPERIMENT"
    }
    experiment_agents = {item["id"] for item in data["agents"] if item["status"] == "EXPERIMENT"}
    experiment_tools = {item["id"] for item in data["tools"] if item["status"] == "EXPERIMENT"}

    assert experiment_use_cases == {"assessment_interpretation", "growth_plan_draft"}
    assert experiment_agents == {"parent_advisor", "growth_planner"}
    assert experiment_tools == {"read_context"}
    for section in ("use_cases", "agents", "tools"):
        assert all(item["status"] in {"PLANNED", "EXPERIMENT"} for item in data[section])
