import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_docker_assets_document_single_container_poc():
    dockerfile = _read("Dockerfile")
    compose = _read("docker-compose.yml")
    readme = _read("README.md")
    docker_doc = _read("docs/docker-poc.md")

    assert "FROM python:3.11-slim" in dockerfile
    assert "uvicorn" in dockerfile
    assert "INNERWORK_DATABASE_URL" in compose
    assert "./.innerwork:/tmp/innerwork" in compose
    assert "docker compose up --build" in readme
    assert "http://127.0.0.1:8000" in docker_doc


def test_docs_make_product_scope_and_frontend_backend_boundaries_explicit():
    grand_design = _read("docs/archive/production-oss-grand-design.md")
    live_guide = _read("docs/live-application.md")
    roadmap = _read("docs/production-grade-roadmap.md")
    product_scope = _read("docs/product-scope.md")

    assert "Not building Bitbucket, Trello, Loom, Jira Service Management" in grand_design
    assert "Frontend in the current PoC" in live_guide
    assert "Backend in the current PoC" in live_guide
    assert "Docker PoC" in live_guide
    assert "Phase A — Dockerized proof of concept" in roadmap
    assert "Phase B — Work-and-knowledge MVP" in roadmap
    assert "work graph" in product_scope
    assert "knowledge graph" in product_scope


def test_phase_catalog_carries_active_docker_poc_status():
    phase_catalog = json.loads(_read("data/production_oss_phases.json"))

    assert phase_catalog["selected_products"] == ["jira", "confluence"]
    assert phase_catalog["active_roadmap"]["current_phase"] == "A"
    assert phase_catalog["active_roadmap"]["phases"][0]["name"] == "Dockerized platform PoC"
    assert phase_catalog["active_roadmap"]["phases"][1]["name"] == "Work-and-knowledge MVP"
