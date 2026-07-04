# MRoot2025 / .github

**User-level defaults that flow into every MRoot2025 repo.**

GitHub auto-applies content from this special repo (`<owner>/.github`) as the
default for any owned repo that doesn't have a local override. Edits here
propagate to every repo for free — no per-repo PR needed.

## What lives here

| File / Path | Purpose |
|---|---|
| `profile/README.md` | Public-facing user profile README on github.com/MRoot2025 |
| `CLAUDE.md` | Default Claude Code rules — inherited by any repo without its own |
| `.github/ISSUE_TEMPLATE/*.md` | Default issue templates (bug + feature) |
| `.github/PULL_REQUEST_TEMPLATE.md` | Default PR template |
| `SECURITY.md` | Default security disclosure policy |
| `.github/workflows/_pick-runner.yml` | Reusable — picks a runner tier (PC self-hosted / MIG / ubuntu-latest) |
| `.github/workflows/_qa-chrome-gate.yml` | Reusable — Playwright Chrome QA gate |
| `.github/workflows/_qa-production-ready.yml` | Reusable — marks a PR production-ready once all gates pass |
| `.github/workflows/ig-product-gates.yml` | Reusable — Gates A-D (Next.js CVE floor, Clerk CSP/origins, /sign-in) |
| `actions/purge-stale-git-auth/` | Composite action — clears stale git auth left on persistent self-hosted runners before `actions/checkout` (see its README) |

## Source-of-truth coupling

The Claude Code rule set is **canonically maintained** in
`MRoot2025/ait-claude-config` (`CLAUDE.md`, `BUILD_MANIFEST.md`, `memory/*`,
`agents/*`, `skills/*`, `project-template/`).

The `CLAUDE.md` in this repo is a **lightweight pointer** that says:
"Inherits from `MRoot2025/ait-claude-config`. Read that for the full rule
set." Most projects bootstrapped via
`~/Projects/ait-claude-config/skills/stack-bootstrap/scripts/bootstrap-new-project.ps1`
get the full `project-template/CLAUDE.md` copied in directly; this fallback
catches everything else (forks, contributions, repos created outside the
bootstrap flow).

## Update flow

1. **For Claude Code rule changes** → edit
   `~/Projects/ait-claude-config/CLAUDE.md` first (and the matching
   `memory/*` entry). That's the canonical mirror.
2. **For org-wide GitHub conventions** (issue templates, PR templates,
   default README) → edit this repo directly.
3. Push to `main` of either repo. Changes propagate to all owned repos
   on next page-load (GitHub fetches templates lazily).

## Discovery

GitHub doesn't broadcast that templates exist. To verify a repo is using
defaults from here, open it and try to file an issue — you should see
templates pre-populated from `.github/ISSUE_TEMPLATE/`.

## Why a separate `intelligent-group/.github` repo?

This is the GitHub-supported pattern for user-level defaults. The
alternatives (per-repo copies, manual sync, contributor scripts) all drift.
This repo is the single global lever.
