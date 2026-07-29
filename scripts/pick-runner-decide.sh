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
#   env:    WEIGHT (optional, default "heavy").
#           WEIGHT=light  -> early-exits to the always-on "persistent" pool
#                            (routes light checks off the flaky ephemeral MIG;
#                            see the light branch + 2026-07-29(k) note below);
#                            on a genuine persistent-pool outage it falls back
#                            to the broader self-hosted pool (ig-self-hosted,
#                            incl. cloud MIG) and queues there -- NOT to
#                            billing-blocked ubuntu-latest (2026-07-29(l)).
#           WEIGHT=heavy  -> flows through the Tier 1-4 chain unchanged; here
#                            weight is notice/telemetry text only and does not
#                            change which tier is reachable (see _pick-runner.yml
#                            history note 2026-07-22(f)).
#   stdout: exactly two GITHUB_OUTPUT-format lines: runs_on=... / picked=...
#           (safe to `>> "$GITHUB_OUTPUT"` directly)
#   stderr: ::notice::/::warning:: workflow commands + diagnostic text
#
# WEIGHT=light short-circuits to the "persistent" pool before Tier 1 (see the
# light branch below). The Tier 1-4 chain is the HEAVY path:
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

# ----- Light-weight jobs: route to the always-on "persistent" pool -----
# 2026-07-29 (k): light checks (lint/typecheck/format/security-scan; <2min,
# low CPU) are the majority of check-runs on most PRs and were the dominant
# source of CI flakiness, because the Tier 1-4 chain below can land them on
# the one-shot ephemeral cloud MIG runners (ig-org-runner-mig-*), which boot
# mid-job, recycle under a running job, and race on registration. The 5
# always-on self-hosted runners (gram-runner-1, gram-runner-2,
# pc-ultra7-igorg, pc-ultra7-igorg-orglevel, pc-ultra7-mruser) now carry a
# distinct "persistent" label; the ephemeral MIG runners do NOT. Route light
# jobs to that stable pool.
#
# This is an INDEPENDENT detection, not a relabel of the Tier 1-4 outputs, on
# purpose: the Tier 1-4 chain keys availability off pc-*/ig-self-hosted
# labels, which are NOT a superset of the persistent pool -- gram-runner-1/2
# carry no pc-* prefix. Simply swapping the emitted label to "persistent"
# inside those tiers would let a Tier-2/3 branch (which fires on a MIG being
# online) emit ["self-hosted","persistent"] while zero persistent runners are
# up -- queueing against a dead pool. So light gets its own gate: emit the
# persistent label ONLY when >=1 persistent runner is actually online, else
# fall back to the BROADER self-hosted pool (["self-hosted","ig-self-hosted"],
# incl. cloud MIG) and QUEUE there -- NOT to ubuntu-latest. 2026-07-29(l):
# ubuntu-latest is GitHub-hosted and is billing-blocked during the org-wide
# GH Actions spend outage, so a light job that drops to it would fail/hang;
# the self-hosted pool has no billing dependency, so queueing there is the
# resilient light fallback. (This differs from the HEAVY path's Tier-4 final
# fallback, which still goes to ubuntu-latest -- that path is untouched.)
# Heavy is untouched and flows through Tier 1-4 below.
if [ "$WEIGHT" = "light" ]; then
  PERSIST_ONLINE_COUNT=$(echo "$RUNNERS" | jq -r \
    '[.runners[]? | select(.status=="online") | select([.labels[].name] | index("persistent"))] | length' \
    | head -1)
  # Same integer-hardening as Tier 3 (guards the 2026-07-22(g) multi-doc
  # count-corruption shape: anything not a bare integer -> 0).
  [[ "$PERSIST_ONLINE_COUNT" =~ ^[0-9]+$ ]] || PERSIST_ONLINE_COUNT=0
  if [ "$PERSIST_ONLINE_COUNT" -gt 0 ]; then
    echo "::notice::weight=light -- routing to always-on persistent pool (online=$PERSIST_ONLINE_COUNT) instead of ephemeral MIG; job queues natively if all busy" >&2
    echo 'runs_on=["self-hosted","persistent"]'
    echo 'picked=persistent'
    exit 0
  fi
  echo "::notice::weight=light but ZERO persistent runners online -- falling back to the broader self-hosted pool (ig-self-hosted, incl. cloud MIG); job queues there rather than dropping to billing-blocked ubuntu-latest" >&2
  echo 'runs_on=["self-hosted","ig-self-hosted"]'
  echo 'picked=ig-self-hosted-queued'
  exit 0
fi

# ===== Heavy path: Tier 1-4 chain below is byte-for-byte unchanged. =====

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
