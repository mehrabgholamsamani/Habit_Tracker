from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_container_drops_root_and_excludes_compilers():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split(" AS runtime", maxsplit=1)[1]

    assert "USER app" in runtime
    assert "gcc" not in runtime
    assert "libpq-dev" not in runtime


def test_database_retry_does_not_log_connection_exception():
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "except Exception as" not in entrypoint
    assert "{exc}" not in entrypoint


def test_production_does_not_enable_reload_or_implicitly_run_release_tasks():
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert 'if [ "$environment" = "development" ]' in entrypoint
    assert 'RUN_MIGRATIONS' in entrypoint
    assert 'RUN_SEED' in entrypoint
    assert "python -m app.startup migrate" in entrypoint


def test_runtime_image_excludes_test_sources():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=app:app . ." not in dockerfile
    assert "COPY --chown=app:app app ./app" in dockerfile


def test_base_image_is_digest_pinned():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]

    assert from_lines
    assert all("@sha256:" in line for line in from_lines)


def test_runtime_dependencies_are_exactly_pinned():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    dependencies = [line.strip() for line in requirements if line.strip() and not line.startswith("#")]

    assert dependencies
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s]+", item) for item in dependencies)
