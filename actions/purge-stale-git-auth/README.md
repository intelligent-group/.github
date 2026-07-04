# purge-stale-git-auth

Composite action. Clears stale git `http.https://github.com/.extraheader`
and `url.*.insteadOf` overrides before `actions/checkout` runs, on
persistent self-hosted runners.

## The defect

Unlike GitHub-hosted runners, this org's self-hosted runners
(`pc-ultra7-igorg-orglevel`, and historically `MR-HOME-LP` /
`pc-ultra7-mruser`) are **persistent boxes**, not ephemeral VMs. Global git
config set by one job (or left behind when a job is cancelled/interrupted
mid-run, e.g. a "Configure git HTTPS for private github deps" style step)
survives on disk into the next job that lands on the same box.

`actions/checkout` always injects its own scoped `http.extraheader` (and,
on newer `actions/checkout` versions, an `insteadOf` rewrite) carrying the
job's own short-lived token. If a stale override from a previous job is
still present at a wider scope (`--global` or `--system`), git ends up
sending **both** `Authorization` headers on the same request. GitHub's
git-over-HTTPS backend rejects that outright:

```
remote: Duplicate header: "Authorization"
fatal: unable to access 'https://github.com/...': The requested URL
returned error: 400
```

Every job on the affected runner then fails at checkout, before any of the
job's own steps run — including jobs that have nothing to do with git auth.

Confirmed hits (2026-07-04): `ait-soc-sentinel` PRs #732/#719/#720,
`ait-hosted-agents` PRs #702/#703.

## Fix

Run this action as the **first step**, before `actions/checkout`, in any
job that lands on `[self-hosted, ...]`. It unsets the stale header/rewrite
at every config scope (system/global/local) and sweeps the well-known
gitconfig file locations directly, so `actions/checkout`'s own auth setup
is the only one left standing. It is a pure `git config --unset-all`
no-op on a clean runner and on GitHub-hosted (ephemeral) runners, so it is
safe to add unconditionally.

```yaml
jobs:
  my-job:
    runs-on: [self-hosted, ig-self-hosted]
    steps:
      - uses: intelligent-group/.github/actions/purge-stale-git-auth@main
      - uses: actions/checkout@v4
      # ...
```

## Longer-term: clean the runner boxes themselves

This action is the belt. The suspenders is manually inspecting/cleaning
`~/.gitconfig` (and `/etc/gitconfig`) on the runner boxes that have
actually exhibited the defect: `pc-ultra7-igorg-orglevel`, `MR-HOME-LP`,
`pc-ultra7-mruser`. That has not been done yet as of this action landing —
see the PR that introduced this action for the tracking note.

## Prior art

- `ait-soc-sentinel` main commit `06ef2e6` ("ci: purge stale git
  extraheader before checkout") — inline per-job version of step (1)/(2)
  below, applied across ~15 jobs in that repo.
- `ait-hosted-agents` `.github/workflows/deploy.yml` (branch
  `fix/20260701-jwt-trust-bypass`, commit `3e4b388`) — inline version
  scoped to `--global` extraheader + `url.*.insteadof`.
- `intelligent-group/.github` `.github/workflows/_qa-chrome-gate.yml`
  already carries an inline "Reset persistent-runner git auth
  (pre-checkout)" step (added in PR #23) — this action generalizes that
  same fix for every other reusable workflow / caller repo.
