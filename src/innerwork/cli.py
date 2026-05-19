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


def _print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
