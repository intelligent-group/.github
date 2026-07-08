#!/usr/bin/env python3
"""
Fleet gate: catch the "npm-ci browser-download hang" class.

Reference incident: intelligent-group/intelligentio deploy-production hung ~11min
on `npm ci` because puppeteer/playwright devDep postinstalls download browser
binaries (hundreds of MB) that stall the runner, in a job that never launches a
browser. Fix = PUPPETEER_SKIP_DOWNLOAD / PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD on the
install step + a timeout. (2026-07-08)

This linter runs inside a checked-out repo and classifies, per JOB, every
project-level npm install found in .github/workflows/*.yml:

  FAIL (hang-class): package.json has a browser dep, a job runs a PROJECT
      `npm ci`/`npm install`, that job launches NO browser, and the install has
      no skip-env in scope. This is exactly the intelligentio deploy hang.
  WARN: a browser-launching job runs a project install with no timeout at the
      job or step level (a stalled download hangs forever instead of failing fast).

NOT flagged (these never run the project's browser postinstalls):
  `npm install -g <pkg>`, `npm install <named-pkg>`, `--ignore-scripts`,
  `--package-lock-only`.

Exit 1 when FAILs exist and --enforce is passed; otherwise exit 0 (report-only).
Findings are printed and emitted as GitHub Actions annotations.
"""
import glob
import json
import os
import re
import sys

BROWSER_DEPS = {
    "puppeteer", "puppeteer-core",
    "playwright", "playwright-core", "@playwright/test",
    "@axe-core/playwright",
}

# Substrings in a job's step commands/uses that mean the job launches a browser
# and therefore genuinely needs the binary download (skip-env would break it).
BROWSER_LAUNCH_HINTS = (
    "playwright", "puppeteer", "lhci", "lighthouse", "@axe-core",
    "linkinator", "broken-link", "crawler", "chromium", "webkit",
    "boot-smoke", "carpet-bomb", "autoqa", "visual-regression",
    "test:e2e", "e2e", "browser",
)

SKIP_ENV_KEYS = ("PUPPETEER_SKIP_DOWNLOAD", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD")


def load_yaml():
    import yaml  # deferred so the error message is actionable
    return yaml


def find_browser_deps():
    """Return the set of browser deps declared anywhere in the repo's package.json files."""
    found = set()
    skip_dirs = {"node_modules", "testdata", "fixtures", "__fixtures__", "__tests__", ".gate"}
    for pj in glob.glob("**/package.json", recursive=True):
        if skip_dirs & set(pj.replace("\\", "/").split("/")):
            continue
        try:
            data = json.load(open(pj, encoding="utf-8"))
        except Exception:
            continue
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            for name in (data.get(section) or {}):
                if name in BROWSER_DEPS:
                    found.add(name)
    return found


def is_project_install(cmd):
    """True if `cmd` runs a project-level npm install that triggers postinstalls."""
    for raw in re.split(r"&&|\|\||;|\n", cmd):
        line = raw.strip()
        # ignore-scripts / lockfile-only never run postinstalls
        if "--ignore-scripts" in line or "--package-lock-only" in line:
            continue
        # `npm ci` (any flags) is always a full project install
        if re.search(r"\bnpm\s+ci\b", line):
            return True
        m = re.search(r"\bnpm\s+(install|i)\b(.*)", line)
        if m:
            rest = m.group(2)
            if re.search(r"(^|\s)(-g|--global)(\s|$)", rest):
                continue  # global install — not the project
            # any non-flag token after install == a named package (not project)
            tokens = [t for t in rest.split() if t and not t.startswith("-")]
            if tokens:
                continue  # `npm install <pkg>` — named
            return True   # bare `npm install` / `npm i` — project install
    return False


def collect_env_keys(*blocks):
    keys = set()
    for b in blocks:
        if isinstance(b, dict):
            keys.update(b.keys())
    return keys


def step_text(step):
    parts = []
    if isinstance(step, dict):
        if isinstance(step.get("run"), str):
            parts.append(step["run"])
        if isinstance(step.get("uses"), str):
            parts.append(step["uses"])
        if isinstance(step.get("name"), str):
            parts.append(step["name"])
    return "\n".join(parts).lower()


def job_launches_browser(steps):
    blob = "\n".join(step_text(s) for s in steps)
    return any(h in blob for h in BROWSER_LAUNCH_HINTS)


def annotate(level, file, msg):
    # GitHub Actions annotation
    print(f"::{level} file={file}::{msg}")


def main():
    enforce = "--enforce" in sys.argv
    try:
        yaml = load_yaml()
    except Exception:
        print("::error::PyYAML not available; `pip install pyyaml` before running this gate")
        return 1

    deps = find_browser_deps()
    if not deps:
        print("[npmci-hang-gate] No puppeteer/playwright browser deps in package.json -- nothing to check.")
        return 0
    print(f"[npmci-hang-gate] Browser deps present: {', '.join(sorted(deps))}")

    fails, warns = [], []
    wf_files = sorted(glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml"))
    for wf in wf_files:
        try:
            doc = yaml.safe_load(open(wf, encoding="utf-8"))
        except Exception as e:
            print(f"::warning file={wf}::could not parse YAML ({e}); skipped")
            continue
        if not isinstance(doc, dict):
            continue
        wf_env = collect_env_keys(doc.get("env"))
        jobs = doc.get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps") or []
            job_env = collect_env_keys(job.get("env"))
            job_has_timeout = "timeout-minutes" in job
            job_is_browser = job_launches_browser(steps)
            for step in steps:
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                if not is_project_install(step["run"]):
                    continue
                step_env = collect_env_keys(step.get("env"))
                in_scope = wf_env | job_env | step_env
                has_skip = any(k in in_scope for k in SKIP_ENV_KEYS)
                step_has_timeout = "timeout-minutes" in step
                loc = f"{wf} :: job '{job_name}'"
                if not job_is_browser:
                    if not has_skip:
                        fails.append(loc)
                        annotate("error", wf,
                                 f"job '{job_name}' runs a project npm install with browser deps present "
                                 f"but no {SKIP_ENV_KEYS[0]}/{SKIP_ENV_KEYS[1]} -- add skip-env + timeout "
                                 f"(npm-ci browser-download hang class).")
                else:
                    if not (job_has_timeout or step_has_timeout):
                        warns.append(loc)
                        annotate("warning", wf,
                                 f"job '{job_name}' launches a browser and runs a project npm install with "
                                 f"no timeout -- add timeout-minutes so a stalled browser download fails fast.")

    print("\n===== npm-ci browser-download-hang gate =====")
    print(f"FAIL (hang-class, non-browser job, no skip-env): {len(fails)}")
    for f in fails:
        print(f"  [FAIL] {f}")
    print(f"WARN (browser job, project install, no timeout): {len(warns)}")
    for w in warns:
        print(f"  [WARN] {w}")

    if fails and enforce:
        print("\nGate FAILED (enforce mode). Add skip-env + timeout to the flagged install steps.")
        return 1
    if fails:
        print("\nGate found hang-class jobs (report-only). Pass --enforce to block.")
    else:
        print("\nGate clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
