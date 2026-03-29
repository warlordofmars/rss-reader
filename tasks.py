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

    bump = "none"
    for msg in log.splitlines():
        if re.search(r"^[a-z]+(\(.+\))?!:|BREAKING CHANGE", msg):
            bump = "major"
            break
        elif re.search(r"^feat(\(.+\))?:", msg) and bump != "major":
            bump = "minor"
        elif re.search(r"^(fix|perf)(\(.+\))?:", msg) and bump == "none":
            bump = "patch"

    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        return version


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


# ── Test ──────────────────────────────────────────────────────────────────────


@task
def test_backend(ctx):
    """Run backend tests with pytest"""
    with ctx.cd(BACKEND):
        ctx.run("uv run pytest -v", pty=True)


@task
def test_frontend(ctx):
    """Run frontend tests"""
    with ctx.cd(FRONTEND):
        ctx.run("npm test", pty=True)


@task(test_backend, test_frontend)
def test(ctx):
    """Run all tests (backend + frontend)"""


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


# ── Clean ─────────────────────────────────────────────────────────────────────


@task
def clean(ctx):
    """Remove build artifacts (cdk.out, dist, __pycache__)"""
    ctx.run("find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true")
    ctx.run("rm -rf infra/cdk.out frontend/dist")
    print("Clean.")
