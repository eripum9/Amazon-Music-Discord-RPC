# MIT License - Copyright (c) 2026 eripum9

"""Check PR evidence structure; reviewers must still verify its truth."""

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath


SECTIONS = ("Scope", "Validation", "Regression Evidence", "Platform Checks", "Untested / Limitations")
PLACEHOLDER = re.compile(r"^(?:(?:todo|tbd|placeholder|fill (?:this )?in)\b.*|none provided|\.\.\.|\[.*\]|<.*>)\s*[.!]?$", re.I)
RUNTIME_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".jsx"}


def meaningful(value):
    value = re.sub(r"^[\s*`_:#-]+|[\s*`_]+$", "", value.strip())
    return bool(value) and not PLACEHOLDER.fullmatch(value)


def parse_sections(body):
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    sections = {}
    current = None
    for line in body.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            name = heading.group(1).strip()
            current = next((s for s in SECTIONS if s.lower() == name.lower()), None)
            if current:
                sections.setdefault(current, []).append("")
        elif current:
            sections[current][-1] += line + "\n"
    return {key: "\n".join(values).strip() for key, values in sections.items()}


def flatten_files(data):
    if not isinstance(data, list):
        raise ValueError("changed-files JSON must be a list or a list of API pages")
    result = []
    for item in data:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    if not result:
        raise ValueError("changed-files list is empty")
    for item in result:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str) or not item["filename"]:
            raise ValueError("each changed file must include filename and status")
        if item.get("status") not in {"added", "modified", "removed", "renamed", "copied", "changed", "unchanged"}:
            raise ValueError("each changed file must include a valid status")
        if item["status"] == "renamed" and (not isinstance(item.get("previous_filename"), str) or not item["previous_filename"]):
            raise ValueError("renamed files must include previous_filename")
    return result


def runtime_platform(path):
    parts = PurePosixPath(path).parts
    if len(parts) < 2 or parts[0] not in {"Windows", "MacOS", "Shared"}:
        return None
    if "tests" in (part.lower() for part in parts[1:-1]):
        return None
    return parts[0] if PurePosixPath(path).suffix.lower() in RUNTIME_SUFFIXES else None


def is_runtime(path):
    parts = PurePosixPath(path).parts
    return bool(parts) and "tests" not in (part.lower() for part in parts[:-1]) and not re.search(r"(?:^test_.*\.py$|_test\.py$|(?:\.test|\.spec)\.[cm]?[jt]sx?$)", parts[-1], re.I) and PurePosixPath(path).suffix.lower() in RUNTIME_SUFFIXES


def dependency_file(path):
    name = PurePosixPath(path).name
    return bool(re.fullmatch(r"requirements[^/]*\.(?:txt|lock)", name, re.I)) and not path.startswith(".github/workflows/")


def validate(event, files):
    errors = []
    pr = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pr, dict):
        return ["Event must contain a pull_request object."]
    head = pr.get("head", {}).get("sha", "") if isinstance(pr.get("head"), dict) else ""
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", head):
        return ["Event pull_request.head.sha must be a full 40-character commit SHA."]
    files = flatten_files(files)
    expected_count = pr.get("changed_files")
    if type(expected_count) is not int or expected_count < 0:
        return ["Event pull_request.changed_files must be a non-negative integer."]
    if len(files) != expected_count:
        return [f"Changed-files response has {len(files)} files but the PR reports {expected_count}; refusing incomplete or inconsistent data."]
    runtime = set()
    any_runtime = False
    for file in files:
        for path in (file["filename"], file.get("previous_filename", "")):
            platform = runtime_platform(path)
            if platform:
                runtime.add(platform)
            any_runtime |= is_runtime(path)
    author = pr.get("user", {}).get("login") if isinstance(pr.get("user"), dict) else None
    if author == "dependabot[bot]" and all(dependency_file(f["filename"]) and (not f.get("previous_filename") or dependency_file(f["previous_filename"])) for f in files):
        return []

    sections = parse_sections(pr.get("body") if isinstance(pr.get("body"), str) else "")
    for section in SECTIONS:
        lines = [line for line in sections.get(section, "").splitlines() if meaningful(line)]
        if not lines:
            errors.append(f"Complete the '{section}' section with substantive evidence.")

    validation = sections.get("Validation", "")
    fields = {}
    for match in re.finditer(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(Tested commit|Commands|Results)(?:\*\*)?\s*:\s*(.*)$", validation):
        fields.setdefault(match.group(1).lower(), []).append(match.group(2).strip())
    commits = fields.get("tested commit", [])
    if len(commits) != 1 or not re.fullmatch(r"[0-9a-fA-F]{40}", commits[0]) or commits[0].lower() != head.lower():
        errors.append("Validation: set 'Tested commit:' to the full 40-character PR head SHA.")
    for field in ("commands", "results"):
        if not fields.get(field) or not all(meaningful(value) for value in fields[field]):
            errors.append(f"Validation: provide a non-placeholder '{field.title()}:' value.")

    regression = sections.get("Regression Evidence", "")
    before_after = re.search(r"\bbefore\b", regression, re.I) and re.search(r"\bafter\b", regression, re.I)
    fail_pass = re.search(r"\b(?:fail(?:ed|ing|s|ure)?|red)\b", regression, re.I) and re.search(r"\b(?:pass(?:ed|ing|es)?|green)\b", regression, re.I)
    na = re.search(r"\bn\s*/\s*a\b\s*[:\-\u2013\u2014]?\s*(.+)", regression, re.I)
    na_reason = na and meaningful(na.group(1)) and len(na.group(1).strip()) >= 15 and not any_runtime
    if not ((before_after or fail_pass) and len(regression.strip()) >= 20) and not na_reason:
        errors.append("Regression Evidence: describe failing/before and passing/after behavior; for non-runtime changes, N/A needs a concrete reason.")

    changed_tests = {f["filename"] for f in files if f["status"] in {"added", "modified"}}
    for platform in sorted(runtime):
        allowed = {"Shared"} if platform == "Shared" else {platform, "Shared"}
        if not any(len(parts := PurePosixPath(path).parts) >= 3 and parts[0] in allowed and parts[1].lower() == "tests" and re.search(r"(?:^test_.*\.py$|_test\.py$|(?:\.test|\.spec)\.[cm]?[jt]sx?$)", parts[-1], re.I) for path in changed_tests):
            errors.append(f"{platform} runtime changes require an added or modified corresponding test in {' or '.join(sorted(allowed))}/tests.")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--files", required=True, type=Path)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        files = json.loads(args.files.read_text(encoding="utf-8"))
        errors = validate(event, files)
    except (OSError, ValueError, TypeError) as exc:
        errors = [f"Could not validate input: {exc}"]
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("See .github/PULL_REQUEST_TEMPLATE.md; manual review of evidence is mandatory.", file=sys.stderr)
        return 1
    print("Contribution evidence structure passed; manual review remains mandatory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
