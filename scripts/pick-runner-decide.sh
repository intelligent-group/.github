#!/usr/bin/env bash
# pick-runner-decide.sh -- pure decision logic for _pick-runner.yml, extracted
# 2026-07-22 for unit testability. Prior to this, the identical logic lived
# inline in a workflow `run:` block and could only be exercised by real GH
# Actions runs -- which is how 6 independent bugs (dead label, busy/offline
# conflation, secrets:inherit trap, repo-vs-org API scope, and two stdout-
# swallow/count-corruption bugs) each shipped, individually tested "fixed" in
# isolation, and only surfaced live one at a time over the same day. See
# scripts/gates/__evals__/pick-runner-decide/ for the fixture-based eval that
# exercises all 4 tiers without needing live infra conditions to align.
#
# Contract:
#   stdin:  runners JSON, shape {"runners":[{status,busy,labels:[{name}]}...]}
#           (the raw response body of GET /orgs/{org}/actions/runners, or the
#           {"runners":[]} fallback on a failed query)
#   env:    WEIGHT (optional, default "heavy") -- notice/telemetry text only,
#           does not change which tier is reachable (see _pick-runner.yml
#           history note 2026-07-22(f))
#   stdout: exactly two GITHUB_OUTPUT-format lines: runs_on=... / picked=...
#           (safe to `>> "$GITHUB_OUTPUT"` directly)
#   stderr: ::notice::/::warning:: workflow commands + diagnostic text
#
# Tier 1 -- PC online + IDLE          -> route to self-hosted, prefer PC
# Tier 2 -- PC busy, MIG online+IDLE  -> route to self-hosted, prefer MIG
# Tier 3 -- nothing idle, but PC or MIG registered+ONLINE (just busy)
#                                     -> route to self-hosted anyway; the job
#                                        QUEUES natively on GitHub's side
# Tier 4 -- PC AND MIG both have ZERO online runners (genuine outage)
#                                     -> ubuntu-latest (final fallback)
set -euo pipefail

WEIGHT="${WEIGHT:-heavy}"
if [ "$WEIGHT" != "light" ] && [ "$WEIGHT" != "heavy" ]; then
  echo "::warning::invalid weight '$WEIGHT'; defaulting to 'heavy'" >&2
  WEIGHT=heavy
fi
echo "weight=$WEIGHT" >&2

RUNNERS="$(cat)"

# ----- Tier 1: PC (any "pc-*" labeled runner), online + idle -----
# Prefix match, not the dead exact-string "pc-cpu" -- see _pick-runner.yml
# 2026-07-22(b). Real labels observed: pc-ultra7-igorg, pc-ultra7-mruser, etc.
PC_IDLE=$(echo "$RUNNERS" | jq -r \
  '.runners[]? | select(.status=="online" and .busy==false) | select([.labels[].name] | any(startswith("pc-"))) | .name' \
  | head -1)
PC_ONLINE_COUNT=$(echo "$RUNNERS" | jq -r \
  '[.runners[]? | select(.status=="online") | select([.labels[].name] | any(startswith("pc-")))] | length' \
  | head -1)

if [ -n "$PC_IDLE" ]; then
  echo "::notice::Picked Tier-1 PC runner: $PC_IDLE (weight=$WEIGHT)" >&2
  echo 'runs_on=["self-hosted","ig-self-hosted"]'
  echo 'picked=pc'
  exit 0
fi

# ----- Tier 2: MIG (ig-self-hosted), online + idle -----
MIG_IDLE=$(echo "$RUNNERS" | jq -r \
  '.runners[]? | select(.status=="online" and .busy==false) | select([.labels[].name] | index("ig-self-hosted")) | .name' \
  | head -1)
MIG_ONLINE_COUNT=$(echo "$RUNNERS" | jq -r \
  '[.runners[]? | select(.status=="online") | select([.labels[].name] | index("ig-self-hosted"))] | length' \
  | head -1)

if [ -n "$MIG_IDLE" ]; then
  echo "::notice::PC busy/offline + weight=$WEIGHT; picked Tier-2 MIG: $MIG_IDLE" >&2
  echo 'runs_on=["self-hosted","ig-self-hosted"]'
  echo 'picked=ig-self-hosted'
  exit 0
fi

# ----- Tier 3: nothing idle, but self-hosted infra is registered and
# ONLINE (just fully busy) -- queue there instead of bailing. -----
# Defense in depth: guarantee a clean single integer even if jq ever
# misbehaves again -- this is the exact shape of the 2026-07-22(g) stdout-
# swallow bug (multi-document input made jq emit the count once PER
# document, e.g. "0\n0" -- a bare ${VAR:-0} does NOT catch this, since the
# variable IS set, just to multi-line garbage; caught by this suite's
# regression-2026-07-22g-malformed-duplicate.json fixture). Validate it's
# actually a bare integer; anything else (empty, multi-line, "null") -> 0.
[[ "$PC_ONLINE_COUNT" =~ ^[0-9]+$ ]] || PC_ONLINE_COUNT=0
[[ "$MIG_ONLINE_COUNT" =~ ^[0-9]+$ ]] || MIG_ONLINE_COUNT=0
TOTAL_ONLINE=$((PC_ONLINE_COUNT + MIG_ONLINE_COUNT))
if [ "$TOTAL_ONLINE" -gt 0 ]; then
  echo "::notice::All self-hosted busy (PC online=$PC_ONLINE_COUNT, MIG online=$MIG_ONLINE_COUNT, weight=$WEIGHT) -- queueing on self-hosted rather than bailing to ubuntu-latest" >&2
  echo 'runs_on=["self-hosted","ig-self-hosted"]'
  echo 'picked=ig-self-hosted-queued'
  exit 0
fi

# ----- Tier 4: final fallback -- ZERO self-hosted runners online at all
# (genuine outage, not merely busy). Only condition that should ever reach
# ubuntu-latest now. -----
echo "::notice::No self-hosted runners online at all (PC=$PC_ONLINE_COUNT, MIG=$MIG_ONLINE_COUNT) -- final fallback to ubuntu-latest" >&2
echo 'runs_on=["ubuntu-latest"]'
echo 'picked=ubuntu-latest'
