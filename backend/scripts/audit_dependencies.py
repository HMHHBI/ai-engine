#!/usr/bin/env python3
"""
Evaluates pip-audit JSON output against production security policy:
- Exit 1: One or more unexempted HIGH or CRITICAL vulnerabilities with available fix.
- Exit 0: Clean, exempted, or only non-blocking/unfixed advisories reported.
- Exit 2: Execution or JSON parse error.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


def load_exceptions(exceptions_path: str) -> dict[str, str]:
    if not os.path.exists(exceptions_path):
        return {}
    try:
        with open(exceptions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                f"{item['package'].lower()}:{item['vuln_id']}": item.get("reason", "No justification provided")
                for item in data.get("exceptions", [])
            }
    except Exception as exc:
        print(f"WARNING: Could not parse exceptions file {exceptions_path}: {exc}", file=sys.stderr)
        return {}


def extract_severity(vuln: dict) -> str:
    description = vuln.get("description", "") or ""
    
    m = re.search(r"severity:\s*([a-zA-Z]+)", description, re.IGNORECASE)
    if m:
        lvl = m.group(1).upper()
        if lvl in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
            return "MODERATE" if lvl == "MEDIUM" else lvl

    combined = (
        " ".join(vuln.get("aliases", [])) + " " + description[:400]
    ).upper()

    if "CRITICAL" in combined:
        return "CRITICAL"
    if "HIGH" in combined:
        return "HIGH"
    if "MODERATE" in combined or "MEDIUM" in combined:
        return "MODERATE"
    if "LOW" in combined:
        return "LOW"

    return "UNKNOWN"


def run_audit(requirements_path: str = "requirements.txt", exceptions_path: str = "security-exceptions.json") -> int:
    exceptions = load_exceptions(exceptions_path)

    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        requirements_path,
        "-f",
        "json",
    ]

    print(f"Running pip-audit against {requirements_path} (exceptions from {exceptions_path})...")
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if not proc.stdout.strip():
        print(f"ERROR: pip-audit produced no output. Stderr: {proc.stderr}", file=sys.stderr)
        return 2

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Could not parse pip-audit JSON: {exc}\nStdout:\n{proc.stdout}", file=sys.stderr)
        return 2

    dependencies = data.get("dependencies", [])
    blocking_violations: list[dict] = []
    advisories_reported: list[dict] = []

    for dep in dependencies:
        pkg_name = dep.get("name", "unknown")
        installed_ver = dep.get("version", "unknown")
        vulns = dep.get("vulns", [])

        for vuln in vulns:
            vuln_id = vuln.get("id", "UNKNOWN_ID")
            fix_versions = vuln.get("fix_versions", [])
            has_fix = bool(fix_versions)
            severity = extract_severity(vuln)
            
            exc_key = f"{pkg_name.lower()}:{vuln_id}"
            is_exempt = exc_key in exceptions
            exempt_reason = exceptions.get(exc_key)

            record = {
                "package": pkg_name,
                "installed": installed_ver,
                "vuln_id": vuln_id,
                "severity": severity,
                "has_fix": has_fix,
                "fix_versions": fix_versions,
                "is_exempt": is_exempt,
                "exempt_reason": exempt_reason,
            }
            advisories_reported.append(record)

            if severity in BLOCKING_SEVERITIES and has_fix and not is_exempt:
                blocking_violations.append(record)

    print("\n" + "=" * 80)
    print(f"PIP-AUDIT POLICY REPORT: {len(advisories_reported)} Advisory Record(s) Evaluated")
    print("=" * 80)

    for item in advisories_reported:
        if item["is_exempt"]:
            tag = "EXEMPTED"
        elif item in blocking_violations:
            tag = "BLOCKING (Actionable Fix Available)"
        else:
            tag = "REPORT ONLY"

        msg = (
            f"[{tag}] {item['package']}=={item['installed']} | {item['vuln_id']} "
            f"| Severity: {item['severity']} | Fixes: {item['fix_versions'] if item['has_fix'] else 'None'}"
        )
        if item["is_exempt"]:
            msg += f" | Reason: {item['exempt_reason']}"
        print(msg)

    print("=" * 80 + "\n")

    if blocking_violations:
        print(
            f"FAILED: Found {len(blocking_violations)} unexempted actionable HIGH/CRITICAL vulnerability with available fixes.",
            file=sys.stderr,
        )
        return 1

    print("PASSED: Zero unexempted actionable blocking vulnerabilities.")
    return 0


if __name__ == "__main__":
    req_file = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    exc_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(req_file), "security-exceptions.json")
    sys.exit(run_audit(req_file, exc_file))
