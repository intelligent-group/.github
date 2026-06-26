#!/usr/bin/env bash
# Gate B — Clerk CSP FAPI host check
# Verifies that next.config.ts includes the satellite FAPI host in CSP directives.
# Exits 0 if check passes or no Clerk config detected; 1 if CSP is missing FAPI host.
set -euo pipefail

NEXT_CONFIG="${1:-next.config.ts}"

if [ ! -f "$NEXT_CONFIG" ]; then
  # Try next.config.js fallback
  if [ -f "next.config.js" ]; then
    NEXT_CONFIG="next.config.js"
  elif [ -f "next.config.mjs" ]; then
    NEXT_CONFIG="next.config.mjs"
  else
    echo "::notice::Gate B: no next.config.* found — skipping Clerk CSP check (not a Next.js repo)"
    exit 0
  fi
fi

echo "Checking $NEXT_CONFIG for Clerk FAPI CSP entries..."

# Check if Clerk is referenced at all — if not, skip
if ! grep -qi "clerk" "$NEXT_CONFIG" 2>/dev/null; then
  echo "::notice::Gate B: no Clerk reference found in $NEXT_CONFIG — skipping CSP check"
  exit 0
fi

# Look for FAPI host pattern — either the literal frontend-api.clerk.services or
# a dynamic reference using NEXT_PUBLIC_CLERK_DOMAIN / satelliteFAPI variable
FAPI_PATTERNS=(
  "clerk\\..*intelligentit\\.io"
  "frontend-api\\.clerk\\.services"
  "satelliteFAPI"
  "NEXT_PUBLIC_CLERK_DOMAIN"
  "clerkDomain"
  "fapiHost"
)

FOUND=0
for PATTERN in "${FAPI_PATTERNS[@]}"; do
  if grep -qE "$PATTERN" "$NEXT_CONFIG" 2>/dev/null; then
    echo "Gate B PASS: found FAPI pattern '$PATTERN' in $NEXT_CONFIG"
    FOUND=1
    break
  fi
done

if [ "$FOUND" -eq 0 ]; then
  echo "::error::Gate B FAIL: $NEXT_CONFIG has Clerk but CSP does not include satellite FAPI host"
  echo ""
  echo "Required: script-src, connect-src, and frame-src must include the satellite FAPI endpoint."
  echo "Pattern to add (derive from NEXT_PUBLIC_CLERK_DOMAIN env var):"
  echo "  const satelliteFAPI = \`https://clerk.\${process.env.NEXT_PUBLIC_CLERK_DOMAIN}\`"
  echo "See ait-claude-config skills/new-ig-product/SKILL.md Gate B3 for full CSP template."
  exit 1
fi
