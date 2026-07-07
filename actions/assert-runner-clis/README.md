# assert-runner-clis

Composite action. Fails a job at its very first step if a required CLI
(e.g. `gcloud`) is missing from `PATH` on the runner — instead of the
failure surfacing deep inside an unrelated step, unattributed.

## The defect

Persistent self-hosted runners in this org (`[self-hosted, ig-self-hosted]`,
`[self-hosted, pc-cpu]`) are hand-provisioned boxes, not ephemeral VMs
rebuilt from a known-good image on every job. Nothing guarantees every CLI
a job might call is actually installed on a given box.

Confirmed hit (2026-07-05): the box at `/opt/actions-runner-igorg`
(label `[self-hosted, ig-self-hosted]`) never had Google Cloud SDK
installed. Two unrelated repos hit the same failure the same way — a
`gcloud secrets versions access ...` step deep inside an otherwise-unrelated
job failed with `gcloud: command not found`:

- `intelligent-group/ait-innercircle`, run 28737309100, "Broken link BFS
  crawl" job, step "Pull Firecrawl API key from GSM" (via
  `.github/workflows/broken-link-crawler.yml`)
- `intelligent-group/AiTBMS`, run 28748629023, "Pull Firecrawl API key
  from GSM" step (via `.github/workflows/qa-gate-13-broken-link.yml`)

Neither failure was attributable to "the runner is missing a CLI" from the
log alone — it looked like an app-level bug in a random step, and it
would have recurred on every gcloud-dependent job on that box until
someone happened to trace it back.

## Fix

Run this action as the **first step** in any job that calls a CLI beyond
what every GitHub-hosted runner ships with by default (`gh`, `node`) —
before `actions/checkout` even, since it needs no repo content:

```yaml
jobs:
  my-job:
    runs-on: [self-hosted, ig-self-hosted]
    steps:
      - uses: intelligent-group/.github/actions/assert-runner-clis@main
        with:
          required: 'gcloud gh node'
          runner-name: ${{ runner.name }}
      - uses: actions/checkout@v4
      # ...
```

If any listed CLI is missing, the job fails immediately with a single
`::error::` line naming every missing CLI and the runner, plus a pointer
to the provisioning workflow:

```
gh workflow run runner-provision-clis.yml -R intelligent-group/ait-claude-config --ref main
```

`required` defaults to `'gh node'` if omitted — pass the full list your
job actually needs (e.g. add `gcloud`) explicitly.

## Post-mortem: the action itself broke everything it gated (2026-07-05 – 2026-07-07)

The `runner-name` input's `description:` field (in this README's own "Fix"
example above, and originally in `action.yml`) documented its usage with the
literal text `${{ runner.name }}`. GitHub Actions template-evaluates every
`${{ }}` token found anywhere in an `action.yml` manifest — including plain
`description:` strings meant only as human-readable docs, not just `run:`/
`if:` expressions. The `runner` context isn't available at manifest-parse
time in that position, so loading the action itself failed with
`Unrecognized named-value: 'runner'` at "Set up job" — before checkout, before
any step, on every single caller — with no code change to any caller needed
to trigger it.

Because this action runs first in `deploy.yml`'s `deploy-vercel` job (exactly
per its own usage guidance above), it silently blocked
`intelligent-group/ait-innercircle`'s production Vercel deploy on every push
to `main` for two days, while every other CI check (build, typecheck, PR
checks) stayed green — nothing surfaced this as a deploy problem until a
Playwright E2E run against live prod caught a stale ambiguous-FK PostgREST
error (`PGRST201`) that had already been fixed in `main` days earlier.

`actionlint.yml` in this repo never caught it: it only lints
`.github/workflows/*.yml`, never `actions/**/action.yml` — composite action
manifests use a different schema and actionlint's workflow linter doesn't
parse them. `actions-smoke-test.yml` (added alongside this fix) closes that
gap by actually *invoking* every composite action in `actions/**` on a real
GitHub-hosted runner, so a manifest-parse failure like this one fails CI on
the introducing PR instead of shipping via auto-merge.

**Lesson for any future `action.yml` in this repo:** never write a literal
`${{ ... }}` token inside a `description:` field, even as an illustrative
example. Describe the context/field being referenced in prose instead (e.g.
"the runner context's `name` field") or wrap illustrative snippets in a
way that avoids the literal double-curly-brace token entirely.

## Longer-term: provisioning

This action is the gate. The provisioning workflow
(`runner-provision-clis.yml` in `intelligent-group/ait-claude-config`)
is the fix — it installs Google Cloud SDK on the affected runner pool
and persists it via the runner's `.path` file. `scripts/ig-org-runner-startup.sh`
in that same repo also bakes the install into the GCE MIG boot path for
when the (currently scale-to-zero) MIG pool is scaled back up.

## Prior art

- `actions/purge-stale-git-auth` in this repo — same "gate the defect at
  job start on persistent self-hosted runners" shape, different defect
  (stale git auth headers instead of a missing CLI).
