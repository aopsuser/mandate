#!/usr/bin/env python3
"""Publish this repository to GitHub without a git binary.

Uses the GitHub REST API: the repo is initialized with a first commit (the API
refuses blobs on a completely empty repository), then every file is uploaded as
a blob and assembled into one commit on `main`.

    GITHUB_TOKEN=... python3 scripts/publish_api.py [--repo-name mandate] [--dry-run]

Works with a classic token with `repo` scope. No git, no gh required.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"

DESCRIPTION = (
    "Spend authority for autonomous agents — signed, scoped, revocable budgets "
    "settled through PayPal."
)
TOPICS = ["paypal", "ai-agents", "agentic-commerce", "fintech", "hackathon", "python"]

SKIP_DIRS = {".git", "data", "__pycache__", ".local", ".venv", "venv", "node_modules"}
SKIP_FILES = {".env", ".github_token", ".DS_Store", "gh.zip"}
SKIP_SUFFIXES = {".pyc"}


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if value:
        return value.strip()
    try:
        result = subprocess.run(
            [str(Path.home() / ".local/bin/gh"), "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            "No GitHub token. Set GITHUB_TOKEN, or run `gh auth login --web` first."
        ) from exc
    return result.stdout.strip()


class ApiError(RuntimeError):
    def __init__(self, status: int, method: str, path: str, body: str) -> None:
        super().__init__(f"GitHub API {method} {path} failed ({status}): {body}")
        self.status = status


class Client:
    def __init__(self, token_value: str) -> None:
        self.token = token_value

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{API}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "mandate-publish",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ApiError(exc.code, method, path, detail) from exc


def collect_files() -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        parts = relative.parts
        if any(part in SKIP_DIRS for part in parts[:-1]):
            continue
        if relative.name in SKIP_FILES or relative.suffix in SKIP_SUFFIXES:
            continue
        files.append((relative.as_posix(), path.read_bytes()))
    return files


def ensure_initialised(client: Client, full: str) -> str:
    """Return the current main commit sha, creating a first commit if needed."""
    try:
        ref = client.call("GET", f"/repos/{full}/git/ref/heads/main")
        return ref["object"]["sha"]
    except ApiError as exc:
        if exc.status not in (404, 409):
            raise

    readme = (ROOT / "README.md").read_bytes()
    client.call(
        "PUT",
        f"/repos/{full}/contents/README.md",
        {
            "message": "Initialize repository",
            "content": base64.b64encode(readme).decode("ascii"),
        },
    )
    print("• initialised repository with a first commit")
    ref = client.call("GET", f"/repos/{full}/git/ref/heads/main")
    return ref["object"]["sha"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-name", default="mandate")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = collect_files()
    total = sum(len(blob) for _, blob in files)
    print(f"• {len(files)} files, {total / 1024:.1f} KiB")

    if args.dry_run:
        for name, blob in files:
            print(f"   {name}  ({len(blob)} B)")
        return 0

    client = Client(token())
    user = client.call("GET", "/user")
    owner = user["login"]
    repo = args.repo_name
    full = f"{owner}/{repo}"
    print(f"• authenticated as {owner}")

    try:
        client.call(
            "POST",
            "/user/repos",
            {
                "name": repo,
                "description": DESCRIPTION,
                "private": False,
                "has_issues": True,
                "has_wiki": False,
                "has_projects": False,
                "auto_init": False,
            },
        )
        print(f"• created https://github.com/{full}")
    except ApiError as exc:
        if exc.status != 422:
            raise
        print(f"• repository {full} already exists — adding a new commit")

    base_sha = ensure_initialised(client, full)
    base_commit = client.call("GET", f"/repos/{full}/git/commits/{base_sha}")
    base_tree = base_commit["tree"]["sha"]

    blobs = []
    for index, (name, content) in enumerate(files, start=1):
        result = client.call(
            "POST",
            f"/repos/{full}/git/blobs",
            {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
        )
        blobs.append({"path": name, "mode": "100644", "type": "blob", "sha": result["sha"]})
        if index % 5 == 0 or index == len(files):
            print(f"  uploaded {index}/{len(files)} blobs")

    tree = client.call(
        "POST",
        f"/repos/{full}/git/trees",
        {"base_tree": base_tree, "tree": blobs},
    )
    commit = client.call(
        "POST",
        f"/repos/{full}/git/commits",
        {
            "message": "Mandate: spend authority for autonomous agents",
            "tree": tree["sha"],
            "parents": [base_sha],
        },
    )
    print(f"• commit {commit['sha'][:12]}")

    client.call(
        "PATCH",
        f"/repos/{full}/git/refs/heads/main",
        {"sha": commit["sha"], "force": False},
    )

    client.call("PUT", f"/repos/{full}/topics", {"names": TOPICS})
    client.call("PATCH", f"/repos/{full}", {"description": DESCRIPTION, "private": False})

    print()
    print(f"✓ https://github.com/{full}")
    print("  Check the About sidebar shows: MIT license")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
