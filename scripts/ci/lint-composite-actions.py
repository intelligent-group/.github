#!/usr/bin/env python3
"""Lightweight composite action.yml manifest linter.

actionlint (as of v1.7.x) does NOT parse action.yml / action.yaml as composite
action manifests -- pointing it at one directly produces bogus "workflow"
syntax errors (missing on/jobs sections) instead of linting the manifest, and
by default actionlint only globs .github/workflows/*.yml, so composite
manifests are silently skipped entirely. This script fills that gap for the
defect class that caused a silent prod-dead deploy (ait-innercircle,
2026-07-05, .github#35): a typo'd or renamed `${{ inputs.X }}` reference that
isn't declared in the manifest's `inputs:` block evaluates to an empty string
at runtime -- no error, no warning, just quietly wrong. `${{ }}` expressions
evaluate ANYWHERE in the manifest, including `description:` fields, not just
`run:`/`if:` steps.

Checks, for every action.yml/action.yaml with `runs.using: composite`:
  1. Every `${{ inputs.<name> }}` reference resolves to a declared `inputs:` key.
  2. No `${{ secrets.<name> }}` reference anywhere -- composite actions do not
     have access to the `secrets` context; it silently resolves empty at
     runtime instead of erroring.
  3. `${{ ... }}` expressions in the file are brace-balanced (catches
     truncated/malformed refs that would otherwise silently no-op).

Usage:
  python3 lint-composite-actions.py [path ...]   # defaults to repo root

Exit 0 = clean (or no composite actions found). Exit 1 = defects found.
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

EXPR_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
INPUT_REF_RE = re.compile(r"\binputs\.([A-Za-z0-9_-]+)")
SECRET_REF_RE = re.compile(r"\bsecrets\.([A-Za-z0-9_-]+)")


def find_manifests(paths):
    out = []
    for p in paths:
        root = Path(p)
        if root.is_file() and root.name in ("action.yml", "action.yaml"):
            out.append(root)
            continue
        for name in ("action.yml", "action.yaml"):
            out.extend(root.rglob(name))
    # de-dupe, skip node_modules / .git / vendored dirs
    seen = set()
    result = []
    for f in out:
        rp = f.resolve()
        if rp in seen:
            continue
        if any(part in ("node_modules", ".git", "vendor", "dist", "build") for part in f.parts):
            continue
        seen.add(rp)
        result.append(f)
    return sorted(result)


def lint_manifest(path: Path):
    errors = []
    text = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"{path}: YAML parse error: {e}"]

    if not isinstance(data, dict):
        return errors

    runs = data.get("runs") or {}
    if not isinstance(runs, dict) or runs.get("using") != "composite":
        return errors  # not a composite action -- nothing for this script to check

    declared_inputs = set((data.get("inputs") or {}).keys()) if isinstance(data.get("inputs"), dict) else set()

    # 1 & 3: brace balance + declared-input check, over every ${{ ... }} in the raw file
    open_count = text.count("${{")
    close_count = text.count("}}")
    if open_count != close_count:
        errors.append(
            f"{path}: unbalanced '${{{{' / '}}}}' markers ({open_count} open vs {close_count} close) "
            f"-- a malformed expression will silently no-op or corrupt the manifest"
        )

    for m in EXPR_RE.finditer(text):
        expr = m.group(1)
        line_no = text.count("\n", 0, m.start()) + 1

        for secret_match in SECRET_REF_RE.finditer(expr):
            errors.append(
                f"{path}:{line_no}: composite action references "
                f"'${{{{ secrets.{secret_match.group(1)} }}}}' -- composite actions have NO access "
                f"to the secrets context; this silently evaluates to an empty string. "
                f"Pass it as an explicit input instead."
            )

        for input_match in INPUT_REF_RE.finditer(expr):
            name = input_match.group(1)
            if name not in declared_inputs:
                errors.append(
                    f"{path}:{line_no}: '${{{{ inputs.{name} }}}}' references an undeclared input "
                    f"(declared inputs: {sorted(declared_inputs) or 'none'}) -- this silently "
                    f"evaluates to an empty string at runtime instead of failing. "
                    f"Root-cause pattern of the 2026-07-05 ait-innercircle prod-dead incident."
                )

    return errors


def main():
    paths = sys.argv[1:] or ["."]
    manifests = find_manifests(paths)
    if not manifests:
        print("lint-composite-actions: no composite action.yml/action.yaml manifests found -- nothing to check.")
        return 0

    all_errors = []
    for m in manifests:
        all_errors.extend(lint_manifest(m))

    if all_errors:
        print(f"lint-composite-actions: {len(all_errors)} issue(s) found across {len(manifests)} manifest(s):\n")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"lint-composite-actions: {len(manifests)} composite manifest(s) checked, all clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
