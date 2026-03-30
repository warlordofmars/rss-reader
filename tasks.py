"""
Invoke task definitions for the RSS Reader monorepo.

Usage:
    uv run inv --list               # list all tasks
    uv run inv lint                 # lint everything
    uv run inv lint-backend         # lint backend only
    uv run inv test                 # run all tests
    uv run inv dev                  # start backend + frontend locally
    uv run inv deploy               # deploy to AWS via CDK
"""

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from invoke import task

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
INFRA = ROOT / "infra"
REGION = "us-east-1"


def _stack_name(env):
    return "RssReaderStack" if env == "prod" else f"RssReaderStack-{env}"


def _infer_next_version(ctx):
    """Infer the next semver from commits since the last tag using conventional commit rules."""
    try:
        last_tag = ctx.run("git describe --tags --abbrev=0", hide=True).stdout.strip()
    except Exception:
        last_tag = "v0.0.0"

    version = last_tag.lstrip("v")
    major, minor, patch = (int(x) for x in version.split("."))

    try:
        log = ctx.run(
            f"git log {last_tag}..HEAD --pretty=format:%s", hide=True
        ).stdout.strip()
    except Exception:
        log = ""

    bump = "patch"  # default: at least a patch bump
    for msg in log.splitlines():
        if re.search(r"^[a-z]+(\(.+\))?!:|BREAKING CHANGE", msg):
            bump = "major"
            break
        elif re.search(r"^feat(\(.+\))?:", msg) and bump != "major":
            bump = "minor"

    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def _ci_pytest_args() -> str:
    """Return --md-report flags when running in GitHub Actions."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    return f' --md-report --md-report-output="{summary}"' if summary else ""


def _aws_account(ctx):
    # Allow override via env var — used in CI synth where no credentials are present
    if account := os.environ.get("AWS_ACCOUNT_ID"):
        return account
    return ctx.run(
        "aws sts get-caller-identity --query Account --output text",
        hide=True,
    ).stdout.strip()


def _cfn_output(ctx, key, env="prod"):
    stack = _stack_name(env)
    return ctx.run(
        f"aws cloudformation describe-stacks --stack-name {stack} --region {REGION}"
        f" --query \"Stacks[0].Outputs[?OutputKey=='{key}'].OutputValue\""
        " --output text",
        hide=True,
    ).stdout.strip()


# ── Lint ──────────────────────────────────────────────────────────────────────


@task
def lint_backend(ctx):
    """Lint backend Python with ruff"""
    with ctx.cd(BACKEND):
        ctx.run("uv run ruff check .", pty=True)


@task
def lint_frontend(ctx):
    """Lint frontend with ESLint"""
    with ctx.cd(FRONTEND):
        ctx.run("npm run lint", pty=True)


@task
def lint_infra(ctx):
    """Lint CDK infra with ruff"""
    with ctx.cd(INFRA):
        ctx.run("uv run ruff check .", pty=True)


@task(lint_backend, lint_frontend, lint_infra)
def lint(ctx):
    """Lint everything (backend + frontend + infra)"""


# ── Audit ─────────────────────────────────────────────────────────────────────


@task
def audit_backend(ctx):
    """Security audit backend dependencies (pip-audit)"""
    # CVE-2026-4539: affects pygments (transitive dep of pip-audit itself), no fix available yet
    with ctx.cd(BACKEND):
        ctx.run("uv run pip-audit --ignore-vuln CVE-2026-4539", pty=True)


@task
def audit_frontend(ctx):
    """Security audit frontend dependencies (npm audit)"""
    with ctx.cd(FRONTEND):
        ctx.run("npm audit --audit-level=high", pty=True)


@task(audit_backend, audit_frontend)
def audit(ctx):
    """Audit all dependencies (backend + frontend)"""


# ── Test ──────────────────────────────────────────────────────────────────────


@task
def test_backend(ctx):
    """Run backend tests with pytest"""
    with ctx.cd(BACKEND):
        ctx.run(f"uv run pytest -v{_ci_pytest_args()}", pty=True)


@task
def test_frontend(ctx):
    """Run frontend tests"""
    ci = bool(os.environ.get("CI"))
    extra = (
        " -- --reporter=verbose --reporter=junit --outputFile.junit=vitest-report.xml"
        if ci
        else ""
    )
    with ctx.cd(FRONTEND):
        ctx.run(f"npm test{extra}", pty=not ci)


@task(test_backend, test_frontend)
def test(ctx):
    """Run all tests (backend + frontend)"""


@task
def playwright(ctx, env=None, admin_email="e2e@test.com"):
    """Run Playwright browser E2E tests. Defaults to localhost; use --env dev or --env prod for deployed envs."""
    extra_env = {"E2E_ADMIN_EMAIL": admin_email}
    if env:
        extra_env["E2E_FRONTEND_URL"] = (
            "https://rss.warlordofmars.net" if env == "prod" else f"https://rss-{env}.warlordofmars.net"
        )
        extra_env["E2E_API_URL"] = (
            "https://api.rss.warlordofmars.net" if env == "prod" else f"https://api.rss-{env}.warlordofmars.net"
        )
    with ctx.cd(FRONTEND):
        ctx.run("npx playwright test", env=extra_env, pty=True)


@task
def playwright_local(ctx, admin_email="e2e@test.com"):
    """Run Playwright browser E2E tests against local dev servers (starts them automatically)."""
    import time

    procs = [
        subprocess.Popen(
            ["uv", "run", "uvicorn", "main:app", "--reload", "--port", "8000"],
            cwd=BACKEND,
        ),
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND,
        ),
    ]

    def _shutdown():
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()

    # Wait for both servers to be ready
    import urllib.request
    import urllib.error

    for label, url in [("backend", "http://localhost:8000/version"), ("frontend", "http://localhost:5173")]:
        for _ in range(30):
            try:
                urllib.request.urlopen(url, timeout=1)
                print(f"{label} ready")
                break
            except Exception:
                time.sleep(1)
        else:
            _shutdown()
            raise SystemExit(f"{label} did not start in time")

    try:
        with ctx.cd(FRONTEND):
            ctx.run(
                "npx playwright test",
                env={"E2E_ADMIN_EMAIL": admin_email},
                pty=True,
            )
    finally:
        _shutdown()


@task
def test_e2e(ctx, env="dev", admin_pass="admin"):
    """Run E2E tests against a deployed environment. Use --env prod for prod."""
    base_url = (
        "https://api.rss.warlordofmars.net"
        if env == "prod"
        else f"https://api.rss-{env}.warlordofmars.net"
    )
    with ctx.cd(BACKEND):
        ctx.run(
            f"uv run pytest tests/e2e -v{_ci_pytest_args()}",
            env={"E2E_BASE_URL": base_url, "E2E_ADMIN_PASS": admin_pass},
            pty=True,
        )


@task
def smoke(ctx, env="prod", admin_pass="admin"):
    """Run smoke tests against a deployed environment (default: prod)."""
    base_url = (
        "https://api.rss.warlordofmars.net"
        if env == "prod"
        else f"https://api.rss-{env}.warlordofmars.net"
    )
    with ctx.cd(BACKEND):
        ctx.run(
            f"uv run pytest tests/e2e/test_smoke.py -v{_ci_pytest_args()}",
            env={
                "E2E_BASE_URL": base_url,
                "E2E_ADMIN_PASS": admin_pass,
                "E2E_EXPECT_INFRA_LINKS": "true",
            },
            pty=True,
        )


# ── Local dev ─────────────────────────────────────────────────────────────────


@task
def dev(ctx):
    """Start backend and frontend dev servers (Ctrl-C to stop both)"""
    procs = [
        subprocess.Popen(
            ["uv", "run", "uvicorn", "main:app", "--reload"],
            cwd=BACKEND,
        ),
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=FRONTEND,
        ),
    ]

    def _shutdown(sig, frame):
        print("\nShutting down...")
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for p in procs:
        p.wait()


# ── CDK ───────────────────────────────────────────────────────────────────────


@task
def synth(ctx, env="prod"):
    """Synthesize CDK stack (skips Docker bundling). Use --env dev for dev stack."""
    account = _aws_account(ctx)
    with ctx.cd(INFRA):
        ctx.run(
            f"uv run cdk synth --no-staging -c account={account} -c env={env}",
            pty=True,
        )


@task
def deploy(ctx, env="prod"):
    """Deploy CDK stack to AWS. Use --env dev for dev stack."""
    account = _aws_account(ctx)
    stack = _stack_name(env)
    if env == "prod":
        version = os.environ.get("APP_VERSION", "dev")
    else:
        short_sha = ctx.run("git rev-parse --short HEAD", hide=True).stdout.strip()
        version = f"{_infer_next_version(ctx)}-{env}.{short_sha}"
    with ctx.cd(INFRA):
        ctx.run(
            f"uv run cdk deploy {stack} --require-approval never"
            f" -c account={account} -c env={env}",
            env={"APP_VERSION": version},
            pty=True,
        )


# ── AWS utilities ─────────────────────────────────────────────────────────────


@task
def outputs(ctx, env="prod"):
    """Print CloudFormation stack outputs. Use --env dev for dev stack."""
    stack = _stack_name(env)
    ctx.run(
        f"aws cloudformation describe-stacks --stack-name {stack}"
        f" --region {REGION}"
        " --query 'Stacks[0].Outputs' --output table --no-cli-pager",
        pty=True,
    )


@task
def logs(ctx, env="prod"):
    """Tail Lambda CloudWatch logs (Ctrl-C to stop). Use --env dev for dev stack."""
    fn = _cfn_output(ctx, "LambdaFunctionName", env=env)
    ctx.run(f"aws logs tail /aws/lambda/{fn} --follow --region {REGION}", pty=True)


# ── Release utilities ─────────────────────────────────────────────────────────


@task
def back_merge(ctx):
    """Open a PR to merge main back into development after a prod release."""
    result = ctx.run(
        "gh pr create"
        " --base development"
        " --head main"
        " --title 'chore: merge main back to development'"
        " --body 'Back-merge after prod release. Merge using **merge commit** (not squash).'",
        warn=True,
        hide="both",
    )
    if result.ok:
        pr_url = result.stdout.strip().splitlines()[-1]
        print(f"PR created: {pr_url}")
        ctx.run(f"gh pr merge '{pr_url}' --auto --merge", warn=True)
    else:
        print("PR already exists or nothing to merge — skipping")


# ── Clean ─────────────────────────────────────────────────────────────────────


@task
def clean(ctx):
    """Remove build artifacts (cdk.out, dist, __pycache__)"""
    ctx.run("find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true")
    ctx.run("rm -rf infra/cdk.out frontend/dist")
    print("Clean.")
