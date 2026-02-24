#!/usr/bin/env python3
"""Sync git-tracked runtime configs to ~/.openclaw/.

Copies runtime/openclaw.json → ~/.openclaw/openclaw.json
Copies runtime/cron/jobs.json → ~/.openclaw/cron/jobs.json

If openclaw.json has $SOPS: placeholders, injects real values from
/run/robothor/secrets.env before writing to ~/.openclaw/.

Usage:
    python scripts/sync_runtime.py [--dry-run] [--yes] [--restart]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / "runtime"
OPENCLAW_DIR = Path.home() / ".openclaw"
SECRETS_ENV = Path("/run/robothor/secrets.env")
BACKUP_DIR = OPENCLAW_DIR / "backups"

FILES = [
    (RUNTIME_DIR / "openclaw.json", OPENCLAW_DIR / "openclaw.json"),
    (RUNTIME_DIR / "cron" / "jobs.json", OPENCLAW_DIR / "cron" / "jobs.json"),
]


def load_secrets() -> dict[str, str]:
    """Load secrets from /run/robothor/secrets.env and live runtime config.

    $SOPS: keys come from secrets.env (decrypted at runtime).
    $MANUAL: keys are extracted from the live runtime openclaw.json
    by scanning for values that differ between git and runtime copies.
    """
    secrets = {}

    # Load SOPS-managed secrets
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                secrets[key.strip()] = value

    # Load manual secrets by scanning live runtime config for values
    # that correspond to $MANUAL: placeholders in the git copy
    live_openclaw = OPENCLAW_DIR / "openclaw.json"
    if live_openclaw.exists():
        try:
            live_data = json.loads(live_openclaw.read_text())
            # Extract known manual-secret paths
            manual_paths = {
                "BRAVE_SEARCH_API_KEY": ["tools", "web", "search", "apiKey"],
            }
            for key, path in manual_paths.items():
                obj = live_data
                for p in path:
                    obj = obj.get(p, {}) if isinstance(obj, dict) else None
                    if obj is None:
                        break
                if obj and isinstance(obj, str) and not obj.startswith("$"):
                    secrets[key] = obj
        except (json.JSONDecodeError, OSError):
            pass

    return secrets


def inject_secrets(content: str, secrets: dict[str, str]) -> str:
    """Replace $SOPS:KEY_NAME and $MANUAL:KEY_NAME placeholders with real values."""
    def replacer(match):
        prefix = match.group(1)
        key = match.group(2)
        if key in secrets:
            return secrets[key]
        print(f"  WARNING: No secret found for ${prefix}:{key}", file=sys.stderr)
        return match.group(0)

    return re.sub(r"\$(SOPS|MANUAL):(\w+)", replacer, content)


def files_differ(src: Path, dst: Path, secrets: dict[str, str]) -> bool:
    """Check if source (with secrets injected) differs from destination."""
    if not dst.exists():
        return True
    src_content = src.read_text()
    if "$SOPS:" in src_content or "$MANUAL:" in src_content:
        src_content = inject_secrets(src_content, secrets)
    dst_content = dst.read_text()
    return src_content != dst_content


def show_diff(src: Path, dst: Path, secrets: dict[str, str]):
    """Show a summary diff between source and destination."""
    if not dst.exists():
        print(f"  {dst} does not exist (will be created)")
        return

    src_content = src.read_text()
    if "$SOPS:" in src_content or "$MANUAL:" in src_content:
        src_content = inject_secrets(src_content, secrets)

    # For JSON files, compare structure
    try:
        src_data = json.loads(src_content)
        dst_data = json.loads(dst.read_text())
        # Simple top-level key comparison
        src_keys = set(src_data.keys()) if isinstance(src_data, dict) else set()
        dst_keys = set(dst_data.keys()) if isinstance(dst_data, dict) else set()
        added = src_keys - dst_keys
        removed = dst_keys - src_keys
        if added:
            print(f"  + Added keys: {added}")
        if removed:
            print(f"  - Removed keys: {removed}")
        if not added and not removed:
            print(f"  ~ Content changed (same top-level structure)")
    except json.JSONDecodeError:
        print(f"  ~ Content changed")


def backup_runtime():
    """Backup current runtime files before overwriting."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / timestamp
    backup_path.mkdir(parents=True, exist_ok=True)

    for _, dst in FILES:
        if dst.exists():
            rel = dst.relative_to(OPENCLAW_DIR)
            backup_file = backup_path / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup_file)

    print(f"Backed up to {backup_path}")
    return backup_path


def sync(dry_run: bool = False, auto_yes: bool = False, restart: bool = False):
    """Main sync logic."""
    secrets = load_secrets()
    has_sops = False

    # Check for SOPS placeholders
    for src, _ in FILES:
        if src.exists() and ("$SOPS:" in src.read_text() or "$MANUAL:" in src.read_text()):
            has_sops = True
            break

    if has_sops and not secrets:
        print("WARNING: openclaw.json has $SOPS: placeholders but no secrets found")
        print(f"  Expected: {SECRETS_ENV}")
        print("  Secrets will NOT be injected. The synced file will have raw placeholders.")
        if not auto_yes:
            resp = input("Continue anyway? [y/N] ")
            if resp.lower() != "y":
                print("Aborted.")
                sys.exit(1)

    # Check which files need updating
    changes = []
    for src, dst in FILES:
        if not src.exists():
            print(f"SKIP: {src} not found in repo")
            continue
        if files_differ(src, dst, secrets):
            changes.append((src, dst))

    if not changes:
        print("No changes detected. Runtime configs match git.")
        return

    print(f"\n{len(changes)} file(s) to sync:")
    for src, dst in changes:
        print(f"\n  {src.relative_to(REPO_ROOT)} → {dst}")
        show_diff(src, dst, secrets)

    if dry_run:
        print("\n--dry-run: No files were modified.")
        return

    if not auto_yes:
        resp = input("\nProceed with sync? [y/N] ")
        if resp.lower() != "y":
            print("Aborted.")
            sys.exit(1)

    # Backup first
    backup_runtime()

    # Write files
    for src, dst in changes:
        content = src.read_text()
        if "$SOPS:" in content:
            content = inject_secrets(content, secrets)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content)
        print(f"Synced: {dst}")

    print("\nSync complete.")

    if restart:
        print("\nRestarting moltbot-gateway...")
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "moltbot-gateway"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("Gateway restarted successfully.")
        else:
            print(f"Gateway restart failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Sync git-tracked runtime configs to ~/.openclaw/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart moltbot-gateway after sync (requires sudo)",
    )
    args = parser.parse_args()
    sync(dry_run=args.dry_run, auto_yes=args.yes, restart=args.restart)


if __name__ == "__main__":
    main()
