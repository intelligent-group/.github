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
