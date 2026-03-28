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
import signal
import subprocess
import sys
from pathlib import Path

from invoke import task

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
INFRA = ROOT / "infra"
STACK = "RssReaderStack"
REGION = "us-east-1"


def _aws_account(ctx):
    # Allow override via env var — used in CI synth where no credentials are present
    if account := os.environ.get("AWS_ACCOUNT_ID"):
        return account
    return ctx.run(
        "aws sts get-caller-identity --query Account --output text",
        hide=True,
    ).stdout.strip()


def _cfn_output(ctx, key):
    return ctx.run(
        f"aws cloudformation describe-stacks --stack-name {STACK} --region {REGION}"
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
def synth(ctx):
    """Synthesize CDK stack (skips Docker bundling)"""
    account = _aws_account(ctx)
    with ctx.cd(INFRA):
        ctx.run(f"uv run cdk synth --no-staging -c account={account}", pty=True)


@task
def deploy(ctx):
    """Deploy CDK stack to AWS"""
    account = _aws_account(ctx)
    with ctx.cd(INFRA):
        ctx.run(
            f"uv run cdk deploy --require-approval never -c account={account}",
            pty=True,
        )


# ── AWS utilities ─────────────────────────────────────────────────────────────


@task
def outputs(ctx):
    """Print CloudFormation stack outputs"""
    ctx.run(
        f"aws cloudformation describe-stacks --stack-name {STACK}"
        f" --region {REGION}"
        " --query 'Stacks[0].Outputs' --output table",
        pty=True,
    )


@task
def logs(ctx):
    """Tail Lambda CloudWatch logs (Ctrl-C to stop)"""
    fn = _cfn_output(ctx, "LambdaFunctionName")
    ctx.run(f"aws logs tail /aws/lambda/{fn} --follow --region {REGION}", pty=True)


# ── Clean ─────────────────────────────────────────────────────────────────────


@task
def clean(ctx):
    """Remove build artifacts (cdk.out, dist, __pycache__)"""
    ctx.run("find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true")
    ctx.run("rm -rf infra/cdk.out frontend/dist")
    print("Clean.")
