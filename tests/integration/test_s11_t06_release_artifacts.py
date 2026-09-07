"""S11-T06 integration checks for release artifacts and CI gates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.s11_release_boundary import REQUIRED_CHECKS

pytestmark = pytest.mark.integration


def test_github_workflow_declares_exact_required_quality_checks() -> None:
    workflow = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

    for check in REQUIRED_CHECKS:
        job_name = check.removeprefix("quality / ")
        assert f"  {job_name}:" in workflow
        assert f"    name: {job_name}" in workflow
    assert ":latest" not in workflow
    assert "force" not in workflow.lower()


def test_render_and_docker_artifacts_keep_single_container_boundary() -> None:
    render_yaml = Path("deploy/render.yaml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "type: web" in render_yaml
    assert "runtime: docker" in render_yaml
    assert "plan: starter" in render_yaml
    assert "autoDeploy: false" in render_yaml
    assert "healthCheckPath: /readyz" in render_yaml
    assert "kubernetes" not in render_yaml.lower()
    assert "python:3.12-slim" in dockerfile
    assert "scripts/s11_runtime_server.py" in dockerfile
    assert 'PYTHONPATH="/app"' in dockerfile


def test_release_boundary_cli_outputs_metadata_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/s11_release_boundary.py",
            "release-candidate",
            "--config",
            "deploy/render_staging_release.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["accepted"] is True
    text = json.dumps(payload).lower()
    assert "token" not in text
    assert "authorization" not in text
    assert "raw_response" not in text


def test_release_boundary_cli_fails_closed_on_mismatched_origin(tmp_path: Path) -> None:
    config = json.loads(Path("deploy/render_staging_release.json").read_text())
    config["allowed_cors_origins"] = ["https://attacker.example"]
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/s11_release_boundary.py",
            "release-candidate",
            "--config",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["accepted"] is False


def test_metadata_smoke_cli_records_only_safe_counts() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/s11_staging_smoke.py",
            "--config",
            "deploy/render_staging_release.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["accepted"] is True
    assert payload["metadata"]["request_count"] == 0
    assert payload["metadata"]["shopify_write_count"] == 0
    assert "raw" not in json.dumps(payload).lower()


def test_closed_beta_acceptance_matrix_is_exactly_three_read_only_products() -> None:
    config = json.loads(Path("deploy/render_staging_release.json").read_text())
    smoke = config["smoke_plan"]

    assert config["allowed_cors_origins"] == [
        "https://bys-user-store-578412-7a11gk0u.myshopify.com"
    ]
    assert smoke["products"] == [
        ["Mini3", "9278439686282", "50107364802698"],
        ["Air3", "9278460821642", "50107426603146"],
        ["Mavic3", "9278439719050", "50107364901002"],
    ]
    assert smoke["shopify_writes"] == 0
    assert smoke["retry_count"] == 0
    assert smoke["external_model_calls"] is False
    assert smoke["max_conversation_turns"] == 12
    assert smoke["max_shopify_reads_total"] == 18
    assert smoke["save_raw_payloads"] is False
