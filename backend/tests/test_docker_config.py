"""The Docker set-up, checked statically: what must hold even on a machine without Docker."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CR = b"\r"
DOCKER_FILES = (
    "backend/Dockerfile",
    "backend/docker-entrypoint.sh",
    "web/Dockerfile",
    "web/nginx.conf",
    "web/security_headers.base.conf",
    "docker-compose.yml",
    "docker-compose.hardened.yml",
    ".dockerignore",
    "web/.dockerignore",
)


def load_yaml(name: str) -> dict[str, Any]:
    data = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def nginx_locations() -> dict[str, str]:
    """Location path -> block body (comments removed), from the repository's own nginx.conf."""
    lines = read("web/nginx.conf").splitlines()
    conf = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    return dict(re.findall(r"location\s+([^\s{]+(?:\s+/\S*)?)\s*\{([^}]*)\}", conf))


@pytest.mark.parametrize("name", DOCKER_FILES)
def test_docker_files_use_unix_line_endings(name: str) -> None:
    """A carriage return breaks `sh` scripts and nginx configs inside a Linux container."""
    assert CR not in (ROOT / name).read_bytes(), name


def test_only_the_web_container_publishes_a_port() -> None:
    services = load_yaml("docker-compose.yml")["services"]
    assert set(services) == {"backend", "web"}
    assert "ports" not in services["backend"]
    assert services["backend"]["expose"] == ["8000"]
    assert services["web"]["ports"] == ["8080:8080"]


def test_the_web_container_waits_for_a_healthy_api() -> None:
    web = load_yaml("docker-compose.yml")["services"]["web"]
    assert web["depends_on"]["backend"]["condition"] == "service_healthy"


def test_the_data_lives_in_a_named_volume() -> None:
    compose = load_yaml("docker-compose.yml")
    assert "studyroute-data" in compose["volumes"]
    assert "studyroute-data:/srv/data" in compose["services"]["backend"]["volumes"]


def test_every_setting_compose_passes_is_documented_in_env_example() -> None:
    environment = load_yaml("docker-compose.yml")["services"]["backend"]["environment"]
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", read(".env.example"), re.MULTILINE))
    assert sorted(set(environment) - documented) == []


def test_compose_ships_no_secret_values() -> None:
    environment = load_yaml("docker-compose.yml")["services"]["backend"]["environment"]
    for name, value in environment.items():
        optional = rf"\$\{{{name}:-[a-z]*\}}"  # ${NAME:-} or ${NAME:-sandbox}
        assert re.fullmatch(optional, str(value)), f"{name} has a fixed value"


def test_the_hardened_overlay_only_touches_existing_services() -> None:
    base = load_yaml("docker-compose.yml")["services"]
    overlay = load_yaml("docker-compose.hardened.yml")["services"]
    assert set(overlay) == set(base)
    for service in overlay.values():
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert "/tmp" in service["tmpfs"]


def test_the_entrypoint_seeds_unless_production_then_serves() -> None:
    script = read("backend/docker-entrypoint.sh")
    assert re.search(r"^set -eu$", script, re.MULTILINE)
    assert 'APP_ENV:-sandbox}" != "production"' in script
    assert "python -m app.scripts.seed --if-empty" in script
    assert re.search(r"^exec uvicorn app\.main:create_app --factory", script, re.MULTILINE)
    assert script.index("seed --if-empty") < script.index("exec uvicorn")
    assert "--no-server-header" in script, "the server software is not announced to clients"


def test_the_api_image_runs_as_a_non_root_user_with_a_health_check() -> None:
    dockerfile = read("backend/Dockerfile")
    assert re.search(r"^USER studyroute$", dockerfile, re.MULTILINE)
    assert "useradd --system" in dockerfile
    assert not re.search(r"^USER\s+(root|0)", dockerfile, re.MULTILINE)
    assert "HEALTHCHECK" in dockerfile
    assert re.search(r"^FROM python:3\.12", dockerfile, re.MULTILINE)


def test_the_api_image_installs_runtime_requirements_only() -> None:
    dockerfile = read("backend/Dockerfile")
    assert "pip install -r requirements.txt" in dockerfile
    assert "requirements-dev" not in dockerfile


def test_the_build_context_leaves_out_secrets_and_local_state() -> None:
    ignored = read(".dockerignore").splitlines()
    for pattern in (".git", ".env", "data/", "*.db", "**/node_modules", "**/.venv"):
        assert pattern in ignored, pattern


def test_the_web_image_is_unprivileged_and_ships_the_security_headers() -> None:
    dockerfile = read("web/Dockerfile")
    assert "FROM nginxinc/nginx-unprivileged" in dockerfile
    # The build writes security_headers.conf (the policy plus the hashes of the exported inline scripts).
    assert (
        "COPY --from=build /app/security_headers.conf /etc/nginx/security_headers.conf"
        in dockerfile
    )
    assert "RUN npm run build" in dockerfile
    assert "COPY nginx.conf /etc/nginx/conf.d/default.conf" in dockerfile
    assert "EXPOSE 8080" in dockerfile


def test_nginx_proxies_the_api_and_health_to_the_backend() -> None:
    locations = nginx_locations()
    assert "proxy_pass http://backend:8000;" in locations["/api/"]
    assert "proxy_pass http://backend:8000/health;" in locations["= /health"]
    assert "X-Forwarded-For $remote_addr" in locations["/api/"]


def test_nginx_does_not_add_security_headers_to_api_responses() -> None:
    """The API sends its own stricter ones; adding the page's too sent each header twice."""
    locations = nginx_locations()
    for path in ("/api/", "= /health"):
        assert "add_header" not in locations[path], path
        assert "security_headers.conf" not in locations[path], path


def test_nginx_adds_the_security_headers_to_the_page_and_the_assets() -> None:
    locations = nginx_locations()
    for path in ("/", "/_next/static/"):
        assert "include /etc/nginx/security_headers.conf;" in locations[path], path


def test_the_request_size_limit_is_set_and_the_version_is_hidden() -> None:
    conf = read("web/nginx.conf")
    assert "client_max_body_size 128k;" in conf
    assert "server_tokens off;" in conf


def test_ci_builds_and_smoke_tests_the_compose_stack() -> None:
    ci = load_yaml(".github/workflows/ci.yml")
    steps = "\n".join(str(step.get("run", "")) for step in ci["jobs"]["docker"]["steps"])
    assert "docker compose up -d --build --wait" in steps
    assert "python scripts/docker_smoke.py http://localhost:8080" in steps
    assert "demo_flow" in steps
    assert "docker compose down -v" in steps


def test_the_image_switches_off_onnx_runtime_telemetry() -> None:
    """ONNX Runtime 1.31 contacts Microsoft on Linux unless told not to (seen in a packet capture)."""
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^ENV ORT_DISABLE_TELEMETRY=1$", dockerfile, re.MULTILINE)
