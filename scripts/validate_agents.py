#!/usr/bin/env python3
"""Validate agent manifests against config files.

Detects drift between YAML manifests in docs/agents/ and the actual
config in runtime/openclaw.json, runtime/cron/jobs.json, and
brain/agent_capabilities.json.

Usage:
    python scripts/validate_agents.py                   # Check all agents
    python scripts/validate_agents.py --agent <id>      # Check one agent
    python scripts/validate_agents.py --verbose          # Show details
    python scripts/validate_agents.py --json             # JSON output
    python scripts/validate_agents.py --diff <id>        # Show config diff
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / "docs" / "agents"
OPENCLAW_PATH = REPO_ROOT / "runtime" / "openclaw.json"
JOBS_PATH = REPO_ROOT / "runtime" / "cron" / "jobs.json"
CAPABILITIES_PATH = REPO_ROOT / "brain" / "agent_capabilities.json"


class CheckResult:
    """Result of a single validation check."""

    def __init__(self, check_id: str, name: str):
        self.check_id = check_id
        self.name = name
        self.status = "PASS"  # PASS, FAIL, WARN, SKIP
        self.message = ""
        self.details: list[str] = []

    def fail(self, msg: str, details: list[str] | None = None):
        self.status = "FAIL"
        self.message = msg
        self.details = details or []
        return self

    def warn(self, msg: str, details: list[str] | None = None):
        self.status = "WARN"
        self.message = msg
        self.details = details or []
        return self

    def skip(self, msg: str):
        self.status = "SKIP"
        self.message = msg
        return self


def load_manifests(agent_id: str | None = None) -> dict:
    """Load YAML manifests from docs/agents/."""
    manifests = {}
    for f in sorted(MANIFEST_DIR.glob("*.yaml")):
        if f.name == "PLAYBOOK.md":
            continue
        with open(f) as fh:
            data = yaml.safe_load(fh)
        if data and "id" in data:
            if agent_id is None or data["id"] == agent_id:
                manifests[data["id"]] = data
    return manifests


def load_openclaw() -> dict:
    """Load openclaw.json."""
    with open(OPENCLAW_PATH) as f:
        return json.load(f)


def load_jobs() -> dict:
    """Load jobs.json."""
    with open(JOBS_PATH) as f:
        return json.load(f)


def load_capabilities() -> dict:
    """Load agent_capabilities.json."""
    with open(CAPABILITIES_PATH) as f:
        return json.load(f)


def find_agent_in_openclaw(openclaw: dict, agent_id: str) -> dict | None:
    """Find agent entry in openclaw.json agents.list."""
    for agent in openclaw.get("agents", {}).get("list", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def find_job(jobs: dict, agent_id: str) -> dict | None:
    """Find job entry in jobs.json by agentId."""
    for job in jobs.get("jobs", []):
        if job.get("agentId") == agent_id:
            return job
    return None


def check_id_consistency(manifest: dict, openclaw: dict, jobs: dict, caps: dict) -> CheckResult:
    """A. Check agent ID exists in all config files."""
    result = CheckResult("A", "ID consistency")
    agent_id = manifest["id"]
    missing = []

    if find_agent_in_openclaw(openclaw, agent_id) is None:
        missing.append("openclaw.json agents.list")
    if find_job(jobs, agent_id) is None:
        missing.append("jobs.json")
    if agent_id not in caps.get("agents", {}):
        missing.append("agent_capabilities.json")

    if missing:
        return result.fail(f"Agent '{agent_id}' missing from: {', '.join(missing)}")
    return result


def check_model_match(manifest: dict, openclaw: dict, jobs: dict) -> CheckResult:
    """B. Check model config matches manifest."""
    result = CheckResult("B", "Model match")
    agent_id = manifest["id"]
    oc_agent = find_agent_in_openclaw(openclaw, agent_id)
    job = find_job(jobs, agent_id)
    issues = []

    if oc_agent:
        m_primary = manifest.get("model", {}).get("primary", "")
        oc_primary = oc_agent.get("model", {}).get("primary", "")
        if m_primary != oc_primary:
            issues.append(f"primary: manifest={m_primary}, config={oc_primary}")

        m_fallbacks = manifest.get("model", {}).get("fallbacks", [])
        oc_fallbacks = oc_agent.get("model", {}).get("fallbacks", [])
        if m_fallbacks != oc_fallbacks:
            issues.append(f"fallbacks: manifest={m_fallbacks}, config={oc_fallbacks}")

    if job:
        m_alias = manifest.get("model", {}).get("payload_alias", "")
        j_model = job.get("payload", {}).get("model", "")
        if m_alias and m_alias != j_model:
            issues.append(f"payload_alias: manifest={m_alias}, jobs.json={j_model}")

    if issues:
        return result.fail("Model mismatch", issues)
    return result


def check_schedule_match(manifest: dict, jobs: dict) -> CheckResult:
    """C. Check schedule/delivery matches manifest."""
    result = CheckResult("C", "Schedule match")
    agent_id = manifest["id"]
    job = find_job(jobs, agent_id)
    if not job:
        return result.skip("No job found in jobs.json")

    issues = []
    m_sched = manifest.get("schedule", {})
    j_sched = job.get("schedule", {})

    if m_sched.get("cron", "") != j_sched.get("expr", ""):
        issues.append(f"cron: manifest={m_sched.get('cron')}, jobs.json={j_sched.get('expr')}")
    if m_sched.get("timezone", "") != j_sched.get("tz", ""):
        issues.append(f"timezone: manifest={m_sched.get('timezone')}, jobs.json={j_sched.get('tz')}")

    m_timeout = m_sched.get("timeout_seconds", 0)
    j_timeout = job.get("payload", {}).get("timeoutSeconds", 0)
    if m_timeout != j_timeout:
        issues.append(f"timeout: manifest={m_timeout}, jobs.json={j_timeout}")

    m_delivery = manifest.get("delivery", {})
    j_delivery = job.get("delivery", {})
    if m_delivery.get("mode", "") != j_delivery.get("mode", ""):
        issues.append(f"delivery mode: manifest={m_delivery.get('mode')}, jobs.json={j_delivery.get('mode')}")

    if m_delivery.get("mode") == "announce":
        if m_delivery.get("channel", "") != j_delivery.get("channel", ""):
            issues.append(f"delivery channel: manifest={m_delivery.get('channel')}, jobs.json={j_delivery.get('channel')}")
        if m_delivery.get("to", "") != j_delivery.get("to", ""):
            issues.append(f"delivery to: manifest={m_delivery.get('to')}, jobs.json={j_delivery.get('to')}")

    # Check stagger
    m_stagger = m_sched.get("stagger_ms")
    j_stagger = j_sched.get("staggerMs")
    if m_stagger != j_stagger:
        if m_stagger is not None or j_stagger is not None:
            issues.append(f"stagger_ms: manifest={m_stagger}, jobs.json={j_stagger}")

    if issues:
        return result.fail("Schedule mismatch", issues)
    return result


def check_rbac_match(manifest: dict, caps: dict) -> CheckResult:
    """D. Check RBAC tools/endpoints/streams match manifest."""
    result = CheckResult("D", "RBAC match")
    agent_id = manifest["id"]
    cap = caps.get("agents", {}).get(agent_id)
    if not cap:
        return result.skip("No RBAC entry found")

    issues = []
    m_tools = set(manifest.get("tools_allowed", []))
    c_tools = set(cap.get("tools", []))
    if m_tools != c_tools:
        added = m_tools - c_tools
        removed = c_tools - m_tools
        if added:
            issues.append(f"tools in manifest but not RBAC: {sorted(added)}")
        if removed:
            issues.append(f"tools in RBAC but not manifest: {sorted(removed)}")

    m_endpoints = set(manifest.get("bridge_endpoints", []))
    c_endpoints = set(cap.get("bridge_endpoints", []))
    if m_endpoints != c_endpoints:
        added = m_endpoints - c_endpoints
        removed = c_endpoints - m_endpoints
        if added:
            issues.append(f"endpoints in manifest but not RBAC: {sorted(added)}")
        if removed:
            issues.append(f"endpoints in RBAC but not manifest: {sorted(removed)}")

    m_streams_r = set(manifest.get("streams", {}).get("read", []))
    c_streams_r = set(cap.get("streams_read", []))
    if m_streams_r != c_streams_r:
        issues.append(f"streams_read: manifest={sorted(m_streams_r)}, config={sorted(c_streams_r)}")

    m_streams_w = set(manifest.get("streams", {}).get("write", []))
    c_streams_w = set(cap.get("streams_write", []))
    if m_streams_w != c_streams_w:
        issues.append(f"streams_write: manifest={sorted(m_streams_w)}, config={sorted(c_streams_w)}")

    if issues:
        return result.fail("RBAC mismatch", issues)
    return result


def check_deny_list_match(manifest: dict, openclaw: dict) -> CheckResult:
    """E. Check deny list matches manifest."""
    result = CheckResult("E", "Deny list match")
    agent_id = manifest["id"]
    oc_agent = find_agent_in_openclaw(openclaw, agent_id)
    if not oc_agent:
        return result.skip("No openclaw.json entry found")

    m_denied = set(manifest.get("tools_denied", []))
    oc_denied = set(oc_agent.get("tools", {}).get("deny", []))

    if m_denied != oc_denied:
        issues = []
        added = m_denied - oc_denied
        removed = oc_denied - m_denied
        if added:
            issues.append(f"in manifest but not deny list: {sorted(added)}")
        if removed:
            issues.append(f"in deny list but not manifest: {sorted(removed)}")
        return result.fail("Deny list mismatch", issues)
    return result


def check_relationships(manifest: dict, all_manifests: dict) -> CheckResult:
    """F. Check relationship targets have manifests."""
    result = CheckResult("F", "Relationships")
    issues = []

    for field in ["creates_tasks_for", "receives_tasks_from"]:
        for target in manifest.get(field, []):
            if target not in all_manifests:
                issues.append(f"{field} target '{target}' has no manifest")

    reports_to = manifest.get("reports_to")
    if reports_to and reports_to not in all_manifests:
        issues.append(f"reports_to '{reports_to}' has no manifest")

    escalates_to = manifest.get("escalates_to")
    if escalates_to and escalates_to not in all_manifests:
        issues.append(f"escalates_to '{escalates_to}' has no manifest")

    if issues:
        return result.warn("Relationship targets incomplete", issues)
    return result


def check_permission_coherence(manifest: dict) -> CheckResult:
    """G. Check no tool in both allowed AND denied."""
    result = CheckResult("G", "Permission coherence")
    allowed = set(manifest.get("tools_allowed", []))
    denied = set(manifest.get("tools_denied", []))
    overlap = allowed & denied

    if overlap:
        return result.warn(f"Tools in both allowed and denied: {sorted(overlap)}")
    return result


def check_file_existence(manifest: dict) -> CheckResult:
    """H. Check instruction and bootstrap files exist on disk."""
    result = CheckResult("H", "File existence")
    issues = []

    instr_file = manifest.get("instruction_file")
    if instr_file:
        full_path = REPO_ROOT / instr_file
        if not full_path.exists():
            issues.append(f"instruction_file not found: {instr_file}")

    for bf in manifest.get("bootstrap_files", []):
        full_path = REPO_ROOT / bf
        if not full_path.exists():
            issues.append(f"bootstrap_file not found: {bf}")

    if issues:
        return result.fail("Missing files", issues)
    return result


def check_status_coverage(manifest: dict, all_manifests: dict) -> CheckResult:
    """I. Check supervisor reads all declared status files."""
    result = CheckResult("I", "Status coverage")

    # Only check for the supervisor
    if manifest["id"] != "supervisor":
        return result.skip("Only checked for supervisor")

    supervisor_job_path = JOBS_PATH
    with open(supervisor_job_path) as f:
        jobs = json.load(f)
    supervisor_job = find_job(jobs, "supervisor")
    if not supervisor_job:
        return result.skip("No supervisor job found")

    payload_msg = supervisor_job.get("payload", {}).get("message", "")
    missing = []

    for aid, m in all_manifests.items():
        status_file = m.get("status_file")
        if not status_file:
            continue
        # Extract just the filename
        filename = Path(status_file).name
        if filename not in payload_msg:
            missing.append(f"{aid}: {filename}")

    if missing:
        return result.warn(f"Supervisor payload doesn't reference: {missing}")
    return result


def validate_agent(
    manifest: dict,
    openclaw: dict,
    jobs: dict,
    caps: dict,
    all_manifests: dict,
) -> list[CheckResult]:
    """Run all checks for a single agent."""
    results = [
        check_id_consistency(manifest, openclaw, jobs, caps),
        check_model_match(manifest, openclaw, jobs),
        check_schedule_match(manifest, jobs),
        check_rbac_match(manifest, caps),
        check_deny_list_match(manifest, openclaw),
        check_relationships(manifest, all_manifests),
        check_permission_coherence(manifest),
        check_file_existence(manifest),
        check_status_coverage(manifest, all_manifests),
    ]
    return results


def show_diff(manifest: dict, openclaw: dict, jobs: dict, caps: dict):
    """Show detailed diff between manifest and current config."""
    agent_id = manifest["id"]
    print(f"\n{agent_id}: manifest vs current config")

    # openclaw.json
    oc_agent = find_agent_in_openclaw(openclaw, agent_id)
    if oc_agent:
        print(f"\n  openclaw.json:")
        m_primary = manifest.get("model", {}).get("primary", "")
        oc_primary = oc_agent.get("model", {}).get("primary", "")
        status = "MATCH" if m_primary == oc_primary else "MISMATCH"
        print(f"    model.primary: {status}")
        if status == "MISMATCH":
            print(f"      manifest: {m_primary}")
            print(f"      actual:   {oc_primary}")

        m_deny = sorted(manifest.get("tools_denied", []))
        oc_deny = sorted(oc_agent.get("tools", {}).get("deny", []))
        status = "MATCH" if m_deny == oc_deny else "MISMATCH"
        print(f"    tools.deny: {status} ({len(oc_deny)} tools)")
        if status == "MISMATCH":
            print(f"      manifest: {m_deny}")
            print(f"      actual:   {oc_deny}")
    else:
        print(f"\n  openclaw.json: NOT FOUND")

    # jobs.json
    job = find_job(jobs, agent_id)
    if job:
        print(f"\n  jobs.json (job {job['id'][:12]}...):")
        m_cron = manifest.get("schedule", {}).get("cron", "")
        j_cron = job.get("schedule", {}).get("expr", "")
        status = "MATCH" if m_cron == j_cron else "MISMATCH"
        print(f"    schedule: {status}")
        if status == "MISMATCH":
            print(f"      manifest: {m_cron}")
            print(f"      actual:   {j_cron}")

        m_alias = manifest.get("model", {}).get("payload_alias", "")
        j_model = job.get("payload", {}).get("model", "")
        status = "MATCH" if m_alias == j_model else "MISMATCH"
        print(f"    payload.model: {status} ({j_model})")

        m_mode = manifest.get("delivery", {}).get("mode", "")
        j_mode = job.get("delivery", {}).get("mode", "")
        status = "MATCH" if m_mode == j_mode else "MISMATCH"
        print(f"    delivery.mode: {status} ({j_mode})")
    else:
        print(f"\n  jobs.json: NOT FOUND")

    # capabilities
    cap = caps.get("agents", {}).get(agent_id)
    if cap:
        m_tools = set(manifest.get("tools_allowed", []))
        c_tools = set(cap.get("tools", []))
        status = "MATCH" if m_tools == c_tools else "MISMATCH"
        print(f"\n  agent_capabilities.json:")
        print(f"    tools: {status} ({len(c_tools)} tools)")
        if status == "MISMATCH":
            added = m_tools - c_tools
            removed = c_tools - m_tools
            if added:
                print(f"      manifest has: {sorted(added)}")
            if removed:
                print(f"      actual has:   {sorted(removed)}")
    else:
        print(f"\n  agent_capabilities.json: NOT FOUND")


def main():
    parser = argparse.ArgumentParser(description="Validate agent manifests against config files")
    parser.add_argument("--agent", "-a", help="Check a single agent by ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show check details")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--diff", "-d", metavar="AGENT_ID", help="Show config diff for an agent")
    args = parser.parse_args()

    # Verify required files exist
    for path, name in [
        (OPENCLAW_PATH, "runtime/openclaw.json"),
        (JOBS_PATH, "runtime/cron/jobs.json"),
        (CAPABILITIES_PATH, "brain/agent_capabilities.json"),
    ]:
        if not path.exists():
            print(f"ERROR: {name} not found at {path}", file=sys.stderr)
            sys.exit(2)

    openclaw = load_openclaw()
    jobs = load_jobs()
    caps = load_capabilities()

    # Load all manifests for relationship checks
    all_manifests = load_manifests()

    if not all_manifests:
        print("ERROR: No manifests found in docs/agents/*.yaml", file=sys.stderr)
        sys.exit(2)

    # Diff mode
    if args.diff:
        target = load_manifests(args.diff)
        if not target:
            print(f"ERROR: No manifest found for '{args.diff}'", file=sys.stderr)
            sys.exit(1)
        show_diff(target[args.diff], openclaw, jobs, caps)
        sys.exit(0)

    # Filter to single agent if specified
    if args.agent:
        target = load_manifests(args.agent)
        if not target:
            print(f"ERROR: No manifest found for '{args.agent}'", file=sys.stderr)
            sys.exit(1)
    else:
        target = all_manifests

    # Run validation
    all_results = {}
    total_pass = 0
    total_warn = 0
    total_fail = 0
    total_skip = 0

    for agent_id, manifest in sorted(target.items()):
        results = validate_agent(manifest, openclaw, jobs, caps, all_manifests)
        all_results[agent_id] = results

        passes = sum(1 for r in results if r.status == "PASS")
        warns = sum(1 for r in results if r.status == "WARN")
        fails = sum(1 for r in results if r.status == "FAIL")
        skips = sum(1 for r in results if r.status == "SKIP")
        total_pass += passes
        total_warn += warns
        total_fail += fails
        total_skip += skips

    # JSON output
    if args.json:
        output = {}
        for agent_id, results in all_results.items():
            output[agent_id] = [
                {
                    "check": r.check_id,
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "details": r.details,
                }
                for r in results
            ]
        json.dump(
            {
                "agents": output,
                "summary": {
                    "total_agents": len(all_results),
                    "total_checks": total_pass + total_warn + total_fail + total_skip,
                    "pass": total_pass,
                    "warn": total_warn,
                    "fail": total_fail,
                    "skip": total_skip,
                },
            },
            sys.stdout,
            indent=2,
        )
        print()
        sys.exit(1 if total_fail > 0 else 0)

    # Human-readable output
    print("=== Agent Fleet Validation ===")
    print(f"Config: {OPENCLAW_PATH.relative_to(REPO_ROOT)}, {JOBS_PATH.relative_to(REPO_ROOT)}, {CAPABILITIES_PATH.relative_to(REPO_ROOT)}")
    print(f"Manifests: docs/agents/*.yaml ({len(all_manifests)} total)")
    print()

    for agent_id, results in sorted(all_results.items()):
        passes = sum(1 for r in results if r.status == "PASS")
        warns = sum(1 for r in results if r.status == "WARN")
        fails = sum(1 for r in results if r.status == "FAIL")
        active = [r for r in results if r.status != "SKIP"]

        status_parts = []
        if passes:
            status_parts.append(f"{passes} PASS")
        if warns:
            status_parts.append(f"{warns} WARN")
        if fails:
            status_parts.append(f"{fails} FAIL")

        dots = "." * max(1, 40 - len(agent_id))
        print(f"{agent_id} {dots} {', '.join(status_parts)}")

        if args.verbose or fails > 0:
            for r in results:
                if r.status == "SKIP":
                    continue
                icon = {"PASS": "+", "WARN": "~", "FAIL": "!"}[r.status]
                print(f"  [{icon}] {r.check_id}. {r.name}: {r.status}", end="")
                if r.message:
                    print(f" — {r.message}", end="")
                print()
                if args.verbose and r.details:
                    for d in r.details:
                        print(f"      {d}")

    print()
    total_agents = len(all_results)
    agents_clean = sum(
        1 for results in all_results.values()
        if all(r.status in ("PASS", "SKIP") for r in results)
    )
    agents_warn = sum(
        1 for results in all_results.values()
        if any(r.status == "WARN" for r in results)
        and not any(r.status == "FAIL" for r in results)
    )
    agents_fail = sum(
        1 for results in all_results.values()
        if any(r.status == "FAIL" for r in results)
    )
    print(f"SUMMARY: {total_agents} agents — {agents_clean} clean, {agents_warn} warnings, {agents_fail} failures")

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
