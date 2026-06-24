# intelligent-group / .github

**Org-wide defaults and reusable CI/QA workflows for every `intelligent-group` repo.**

GitHub auto-applies content from this special repo (`<owner>/.github`) as the
default for any owned repo that doesn't have a local override. Edits here
propagate to every repo for free — no per-repo PR needed.

## What lives here

| File / Path | Purpose |
|---|---|
| `profile/README.md` | Public-facing org profile README |
| `CLAUDE.md` | Default Claude Code rules — inherited by any repo without its own |
| `.github/ISSUE_TEMPLATE/*.md` | Default issue templates (bug + feature) |
| `.github/PULL_REQUEST_TEMPLATE.md` | Default PR template |
| `SECURITY.md` | Default security disclosure policy |
| `.github/workflows/_pick-runner.yml` | Runner selector (pc-cpu > MIG > ubuntu-latest) |
| `.github/workflows/qa-tier0.yml` | **Tier 0** — Blocking fast gate (GitHub-hosted, <5 min) |
| `.github/workflows/qa-heavy.yml` | **Tier Heavy** — Comprehensive security + quality (self-hosted) |
| `.github/workflows/qa-tier2-scheduled.yml` | **Tier 2** — Nightly gauntlet + post-deploy smoke |
| `consumer-template/qa.yml` | Drop-in stub a repo copies to call all three tiers |

---

## QA / CI Tiering

Intelligent Group uses a **three-tier QA architecture**. Every repo inherits the same
gate policy by calling these reusable workflows with `uses:`. No copy-paste, no drift.

```
Tier 0   ──▶  Blocking  ──▶  GitHub-hosted (ubuntu-latest)  ──▶  <5 min
Tier Heavy ──▶  Informational  ──▶  Self-hosted (heavy runners)  ──▶  15-30 min
Tier 2   ──▶  Nightly/dispatch  ──▶  Self-hosted  ──▶  off-peak (07:17 UTC)
```

### Tier 0 — Blocking Fast Gate (`qa-tier0.yml`)

Runs on **every PR and push**. Must complete in under 5 minutes. Blocks merges.
All jobs run on `ubuntu-latest` (free GitHub-hosted runners). Jobs **skip gracefully**
when the repo lacks the relevant script, but **fail hard on real violations**.

| Job | What it checks |
|-----|----------------|
| `typecheck` | `tsc --noEmit` — no type errors |
| `lint-format` | ESLint (max-warnings 0) + Prettier format check |
| `build` | `npm run build` succeeds |
| `unit-tests` | Unit test suite passes |
| `secret-scan` | gitleaks — no secrets in history |
| `dependency-audit` | `npm audit --audit-level critical` |
| `license-scan` | Deny GPL / AGPL / LGPL dependencies |
| `auth-guard-check` | Every API route imports an auth guard |
| `tenant-scope-lint` | Every DB query in an API route references orgId/tenantId |
| `zod-env-check` | Every request-body parse has a Zod schema; `.env.example` exists |
| `migration-safety` | DROP/TRUNCATE inside transaction; ADD COLUMN NOT NULL has DEFAULT |

### Tier Heavy — Security & Quality Gate (`qa-heavy.yml`)

Runs **after Tier 0** on self-hosted heavy runners. Informational by default
(`continue-on-error: true`). Promote individual jobs to required in branch
protection once runners are stable.

**Runner gate:** entire workflow is skipped unless the org/repo variable
`SELF_HOSTED_READY=true` is set. This prevents infinite queue hangs when
no self-hosted runner exists yet.

| Job | Tool | Category |
|-----|------|----------|
| `pgtap-tenant-isolation` | pgTAP | DB — RLS tenant isolation (real DB) |
| `security-evals` | promptfoo | Domain evals — LLM safety |
| `codeql` | CodeQL | SAST — javascript/typescript |
| `dast-zap` | OWASP ZAP | DAST — baseline web scan |
| `trivy-scan` | Trivy | Container + filesystem vuln scan |
| `e2e-playwright` | Playwright | Full browser E2E test suite |
| `lighthouse-axe` | Lighthouse + axe | Performance + accessibility |
| `iac-scan` | tfsec + checkov | IaC security lint |
| `ai-safety` | promptfoo red-team | AI red-team: prompt-injection, PII-leak, jailbreak |
| `supply-chain` | syft + SLSA | SBOM (SPDX), SLSA attestation, pinned-dep verify |
| `compliance-evidence` | built-in | SOC2/HIPAA control-evidence JSON artifact (365-day retention) |
| `autoqa-verdict` | built-in | Aggregate markdown summary in workflow run |

### Tier 2 — Scheduled Nightly (`qa-tier2-scheduled.yml`)

Runs on **cron `17 7 * * *`** (07:17 UTC, off-peak) and via `workflow_dispatch`.
Also callable as a reusable workflow for post-deploy smoke from another repo.
All jobs continue-on-error; gated by `SELF_HOSTED_READY=true`.

| Job | What it does |
|-----|-------------|
| `multi-tenant-isolation` | Matrix across all tenant slugs — RLS probe, cross-tenant data isolation |
| `audit-gauntlet` | Full dep audit (all severities) + full license audit + outdated report |
| `killswitch-breaker` | Validates kill-switch and spend/anomaly-breaker patterns exist + test |
| `post-deploy-smoke` | Health-check + auth guard smoke + `scripts/smoke-*.ts` scripts |
| `nightly-summary` | Markdown verdict table in GitHub run summary |

---

## Runner Classes

| Label | Type | When used |
|-------|------|-----------|
| `pc-cpu` | Self-hosted (Manuel's PC) | Preferred for all jobs when online |
| `mroot-self-hosted` | Self-hosted (MIG/GCE) | Heavy jobs when PC offline |
| `ubuntu-latest` | GitHub-hosted | Tier 0 always; fallback for heavy when self-hosted offline |

Runner selection is handled by `_pick-runner.yml`. Pass `weight: light` for
Tier 0 tasks and `weight: heavy` for Tier Heavy / Tier 2. See `_pick-runner.yml`
for PAT requirement and HIPAA note.

---

## Runner Gate — How `SELF_HOSTED_READY` Works

Heavy and Tier 2 workflows check:

```yaml
if: ${{ vars.SELF_HOSTED_READY == 'true' }}
```

Set this at **org level** (propagates to all repos) or **repo level** (overrides org):

```bash
# Org-level (all repos)
gh variable set SELF_HOSTED_READY --body "true" --org intelligent-group

# Repo-level override
gh variable set SELF_HOSTED_READY --body "true" --repo intelligent-group/my-repo
```

Until `SELF_HOSTED_READY=true`, all heavy/nightly jobs are **skipped silently**
(not queued, not pending). Tier 0 is always on and unaffected.

---

## Adopting in a New Repo — Quick Start

1. Copy `consumer-template/qa.yml` to your repo's `.github/workflows/qa.yml`
2. Adjust the three inputs (`node-version`, `has-db`, `has-web`)
3. Push — Tier 0 starts immediately on every PR
4. When self-hosted runners are ready, set `SELF_HOSTED_READY=true`

```bash
cp consumer-template/qa.yml path/to/your-repo/.github/workflows/qa.yml
```

Secrets inherited via `secrets: inherit` (org-level secrets):
- `RUNNER_QUERY_PAT` — PAT with `administration:read` for runner selection
- `DATABASE_URL` — Postgres connection string (if `has-db: true`)
- `SMOKE_API_KEY` — API key for smoke tests
- `GITLEAKS_LICENSE` — Gitleaks license (optional, for private repos)

---

## Adding a New Gate

All gates live here. To add a new check:

1. Add a new job to the appropriate tier file in `.github/workflows/`
2. Follow the skip-if-absent pattern: check for the tool/script, emit `::notice::` and `exit 0` if missing
3. Open a PR against `main` here — all repos pick it up automatically on next run

---

## Source-of-Truth Coupling

The Claude Code rule set is **canonically maintained** in
`MRoot2025/ait-claude-config` (`CLAUDE.md`, `BUILD_MANIFEST.md`, `memory/*`,
`agents/*`, `skills/*`, `project-template/`).

The `CLAUDE.md` in this repo is a **lightweight pointer**. Most projects
bootstrapped via the stack-bootstrap skill get the full `project-template/CLAUDE.md`
copied in directly; this fallback catches forks, contributions, and repos
created outside the bootstrap flow.

## Update Flow

1. **For Claude Code rule changes** → edit `~/Projects/ait-claude-config/CLAUDE.md` first.
2. **For QA gate changes** → edit the relevant `qa-tier*.yml` here; all repos inherit automatically.
3. **For org-wide GitHub conventions** → edit this repo directly and push to `main`.

## Default Admins

`mruiz@intelligentit.io` and `twhittall@intelligentit.io` are administrators
of this repo and the `intelligent-group` org.

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
