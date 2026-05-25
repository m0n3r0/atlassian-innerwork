from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from .broker import EdgeBroker
from .catalog import broker_catalog, product_catalog, production_oss_phases
from .control_plane import ControlPlane
from .domain import default_workflow
from .domain_store import (
    DomainStore,
    DuplicateProjectKeyError,
    ProjectNotFoundError,
    WorkItemNotFoundError,
)
from .serialization import (
    operation_result_to_dict,
    snapshot_to_dict,
    spec_from_dict,
    spec_to_dict,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="innerwork",
        description="CLI for the Innerwork open-source edge broker reference app.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("catalog", help="Print the broker catalog as JSON")
    subcommands.add_parser("products", help="Print the grounded public product catalog as JSON")
    subcommands.add_parser("phases", help="Print production OSS phases as JSON")
    validate = subcommands.add_parser("validate", help="Validate an EdgeService YAML/JSON manifest")
    validate.add_argument("manifest", type=Path)
    render = subcommands.add_parser(
        "render",
        help="Validate a manifest and render a control-plane snapshot",
    )
    render.add_argument("manifest", type=Path)
    serve = subcommands.add_parser("serve", help="Run the FastAPI application with uvicorn")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host, default: 127.0.0.1")
    serve.add_argument("--port", default="8000", help="Bind port, default: 8000")
    serve.add_argument("--state", type=Path, help="Optional JSON state file for restart-safe demos")
    serve.add_argument(
        "--database-url",
        help="Optional durable SQLite URL, e.g. sqlite:///.innerwork/innerwork.db",
    )
    serve.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the uvicorn command and environment instead of starting the server",
    )

    # ----- work-graph domain (Phase B slice 1) ------------------------------
    subcommands.add_parser("workflow", help="Print the default work-item workflow as JSON")

    def _add_db_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--database-url",
            help="SQLite URL, e.g. sqlite:///.innerwork/innerwork.db (env: INNERWORK_DATABASE_URL)",
        )

    projects_list = subcommands.add_parser("projects", help="List work-graph projects (JSON)")
    _add_db_arg(projects_list)

    project_create = subcommands.add_parser("project-create", help="Create a work-graph project")
    _add_db_arg(project_create)
    project_create.add_argument("--key", required=True, help="Project key, uppercase, e.g. ENG")
    project_create.add_argument("--name", required=True, help="Project display name")
    project_create.add_argument("--owner", required=True, help="Project owner identifier")

    work_items_list = subcommands.add_parser(
        "work-items", help="List work items (JSON), optionally filtered by project/state"
    )
    _add_db_arg(work_items_list)
    work_items_list.add_argument("--project-id", help="Filter by project_id")
    work_items_list.add_argument("--state", help="Filter by workflow state")

    work_item_create = subcommands.add_parser(
        "work-item-create", help="Create a work item under a project"
    )
    _add_db_arg(work_item_create)
    work_item_create.add_argument("--project-id", required=True)
    work_item_create.add_argument("--title", required=True)
    work_item_create.add_argument("--description", default="")
    work_item_create.add_argument("--assignee", default="")

    work_item_transition = subcommands.add_parser(
        "work-item-transition", help="Transition a work item to a new state"
    )
    _add_db_arg(work_item_transition)
    work_item_transition.add_argument("--work-item-id", required=True)
    work_item_transition.add_argument("--to-state", required=True)
    work_item_transition.add_argument("--actor", required=True)
    work_item_transition.add_argument("--reason", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "catalog":
        _print_json(broker_catalog())
        return 0
    if args.command == "products":
        _print_json(product_catalog())
        return 0
    if args.command == "phases":
        _print_json(production_oss_phases())
        return 0
    if args.command == "validate":
        spec = _load_manifest(args.manifest)
        _print_json({"valid": True, "service": spec_to_dict(spec)})
        return 0
    if args.command == "render":
        broker = EdgeBroker()
        spec = _load_manifest(args.manifest)
        operation = broker.provision(spec)
        result = broker.last_operation(operation.operation_id)
        if result.state != "succeeded":
            _print_json({"valid": False, "operation": operation_result_to_dict(result)})
            return 1
        _print_json(snapshot_to_dict(ControlPlane(broker).snapshot()))
        return 0
    if args.command == "serve":
        return _serve(args.host, args.port, args.state, args.database_url, args.dry_run)
    if args.command == "workflow":
        _print_json(default_workflow().to_dict())
        return 0
    if args.command in {
        "projects",
        "project-create",
        "work-items",
        "work-item-create",
        "work-item-transition",
    }:
        return _domain_dispatch(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _load_manifest(path: Path):
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload = _extract_spec(raw)
    return spec_from_dict(payload)


def _extract_spec(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a mapping")
    spec = raw.get("spec", raw)
    if not isinstance(spec, dict):
        raise ValueError("manifest spec must be a mapping")
    return spec


def _serve(
    host: str,
    port: str,
    state: Path | None,
    database_url: str | None,
    dry_run: bool,
) -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "innerwork.app:app",
        "--host",
        host,
        "--port",
        port,
    ]
    environment = os.environ.copy()
    public_environment: dict[str, str] = {}
    if state is not None:
        environment["INNERWORK_STATE_PATH"] = str(state)
        public_environment["INNERWORK_STATE_PATH"] = str(state)
    if database_url is not None:
        environment["INNERWORK_DATABASE_URL"] = database_url
        public_environment["INNERWORK_DATABASE_URL"] = database_url
    if dry_run:
        _print_json({"command": command, "environment": public_environment})
        return 0
    return subprocess.call(command, env=environment)


def _resolve_database_url(args: argparse.Namespace) -> Path:
    raw = getattr(args, "database_url", None) or os.environ.get("INNERWORK_DATABASE_URL")
    if not raw:
        sys.stderr.write(
            "error: --database-url or INNERWORK_DATABASE_URL is required "
            "(e.g. sqlite:///.innerwork/innerwork.db)\n"
        )
        raise SystemExit(2)
    prefix = "sqlite:///"
    if not raw.startswith(prefix):
        sys.stderr.write("error: only sqlite:/// URLs are supported by the CLI\n")
        raise SystemExit(2)
    return Path(raw[len(prefix) :])


def _domain_dispatch(args: argparse.Namespace) -> int:
    store = DomainStore(_resolve_database_url(args))
    import uuid

    if args.command == "projects":
        _print_json({"projects": [p.to_dict() for p in store.list_projects()]})
        return 0
    if args.command == "project-create":
        try:
            project = store.create_project(
                project_id=str(uuid.uuid4()),
                key=args.key,
                name=args.name,
                owner=args.owner,
            )
        except DuplicateProjectKeyError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1
        _print_json(project.to_dict())
        return 0
    if args.command == "work-items":
        items = store.list_work_items(
            project_id=getattr(args, "project_id", None),
            state=getattr(args, "state", None),
        )
        _print_json({"work_items": [i.to_dict() for i in items]})
        return 0
    if args.command == "work-item-create":
        try:
            item = store.create_work_item(
                work_item_id=str(uuid.uuid4()),
                project_id=args.project_id,
                title=args.title,
                description=args.description,
                assignee=args.assignee,
            )
        except ProjectNotFoundError:
            sys.stderr.write(f"error: project not found: {args.project_id}\n")
            return 1
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1
        _print_json(item.to_dict())
        return 0
    if args.command == "work-item-transition":
        try:
            item, transition = store.transition_work_item(
                work_item_id=args.work_item_id,
                to_state=args.to_state,
                actor=args.actor,
                reason=args.reason,
            )
        except WorkItemNotFoundError:
            sys.stderr.write(f"error: work item not found: {args.work_item_id}\n")
            return 1
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1
        _print_json({"work_item": item.to_dict(), "transition": transition.to_dict()})
        return 0
    raise AssertionError(f"unhandled domain command: {args.command}")


def _print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
