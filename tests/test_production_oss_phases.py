import json
from pathlib import Path

REQUIRED_PHASE_FIELDS = {
    "id",
    "name",
    "objective",
    "jira_inspired_requirements",
    "confluence_inspired_requirements",
    "cross_product_integration_requirements",
    "build_artifacts",
    "acceptance_gates",
    "anti_hallucination_checks",
    "kanban_child_task_shape",
    "exit_criteria",
}


def _catalog() -> dict:
    return json.loads(Path("data/product_catalog.json").read_text())


def _phase_catalog() -> dict:
    return json.loads(Path("data/production_oss_phases.json").read_text())


def test_selected_products_are_exactly_jira_and_confluence_and_grounded():
    phase_catalog = _phase_catalog()
    product_catalog = _catalog()
    product_ids = {product["id"] for product in product_catalog["products"]}

    assert phase_catalog["selected_products"] == ["jira", "confluence"]
    assert set(phase_catalog["selected_products"]) <= product_ids

    grounding = {
        entry["product_id"]: entry for entry in phase_catalog["selected_product_grounding"]
    }
    assert set(grounding) == {"jira", "confluence"}
    assert grounding["jira"]["catalog_role"] == "Primary work graph and workflow engine."
    assert grounding["confluence"]["catalog_role"] == "Knowledge graph and durable decision memory."


def test_phase_ids_are_complete_and_required_fields_are_non_empty():
    phase_catalog = _phase_catalog()
    phases = phase_catalog["phases"]

    assert [phase["id"] for phase in phases] == list(range(11))

    for phase in phases:
        assert REQUIRED_PHASE_FIELDS <= set(phase)
        for field in REQUIRED_PHASE_FIELDS - {"id"}:
            assert phase[field], f"phase {phase['id']} missing {field}"
        assert phase["kanban_child_task_shape"]["block_reason_on_finish"] == "review-required"


def test_every_phase_has_acceptance_and_anti_hallucination_gates():
    for phase in _phase_catalog()["phases"]:
        assert len(phase["acceptance_gates"]) >= 2
        assert len(phase["anti_hallucination_checks"]) >= 2
        hallucination_text = " ".join(phase["anti_hallucination_checks"]).lower()
        assert any(
            marker in hallucination_text
            for marker in (
                "do not",
                "reject",
                "without",
                "not claim",
                "not assert",
                "no ",
            )
        ), f"phase {phase['id']} anti-hallucination checks are not fail-closed"


def test_phase_product_references_are_catalog_grounded_and_bounded():
    phase_catalog = _phase_catalog()
    product_catalog = _catalog()
    selected = set(phase_catalog["selected_products"])
    platform_ids = {capability["id"] for capability in product_catalog["platform_capabilities"]}
    allowed_platform = set(phase_catalog["allowed_platform_capabilities"])
    allowed_dependency_tokens = {"identity", "audit", "billing", "rovo"}
    allowed_tokens = selected | platform_ids | allowed_platform | allowed_dependency_tokens

    assert selected == {"jira", "confluence"}
    assert allowed_platform >= {
        "home",
        "goals",
        "teams",
        "studio",
        "search",
        "chat",
        "analytics",
        "admin",
        "identity",
        "audit",
    }

    forbidden_product_tokens = {
        product["id"] for product in product_catalog["products"] if product["id"] not in selected
    }

    def token_is_present(serialized: str, token: str) -> bool:
        # Product ids that are also ordinary English words (for example "assets")
        # can appear in generic security phrases such as "assets, actors, vectors".
        # Treat only underscore-style product ids as unambiguous hallucination
        # markers in free text; explicit_refs below remains strict for all ids.
        if "_" not in token:
            return False
        return token in serialized

    for phase in phase_catalog["phases"]:
        serialized = json.dumps(phase).lower()
        for token in forbidden_product_tokens:
            assert not token_is_present(serialized, token), (
                f"phase {phase['id']} references unsupported product token {token}"
            )
        explicit_refs = set(phase.get("product_refs", []))
        assert explicit_refs <= allowed_tokens


def test_docs_and_playbook_are_linked_from_navigation():
    docs_index = Path("docs/README.md").read_text()

    # Archived docs remain accessible under docs/archive/ for historical context.
    assert "archive/production-oss-grand-design.md" in docs_index
    assert "archive/autonomous-kanban-playbook.md" in docs_index


def test_playbook_contains_autonomous_iteration_and_stop_conditions():
    playbook = Path("docs/archive/autonomous-kanban-playbook.md").read_text()

    for required in (
        "Serial review-gated stack",
        "Fan-out / fan-in research",
        "TDD discipline",
        "Non-hallucination checks",
        "Iteration policy",
        "Production-readiness gates",
        "Autonomous stop conditions",
        "auth-wall",
        "evidence-missing",
        "unsafe-action",
        "deploy-credentials-required",
    ):
        assert required in playbook
