#!/usr/bin/env python3
"""
Gate E — env-var-conditional auth bypass scanner.

Detects the CVSS 9.1 anti-pattern where Clerk auth is gated on env-var
presence and falls back to an HTTP header read:

    if (process.env.CLERK_SECRET_KEY) {
        const { orgId } = auth()
    } else {
        // ZERO-AUTH: collapses when env var is absent (e.g. after --set-env-vars wipe)
        const orgId = req.headers.get('x-tenant-id')
    }

Fix: unconditional auth(). Misconfigured env should return 500, not bypass auth.

    const { orgId } = auth()
    if (!orgId) return Response.json({ error: 'Unauthorized' }, { status: 401 })

Exit codes:
  0 — no violations found
  1 — one or more violations found (prints file + char offset for each)
"""

import sys
import re

CLERK_ENV_IF = re.compile(
    r'if\s*\([^{]{0,120}process\.env\.CLERK[_A-Z]*(?:KEY|SECRET)[^{]{0,80}\)'
)

HEADER_FALLBACK = re.compile(
    r'(?:headers?\.get|headers?\[)\s*\(?[\'"]'
    r'x-(?:tenant|clerk-org|org|user|organization)-id[\'"]'
)

WINDOW_CHARS = 900  # ~20 lines of context after the if-condition

violations = []

for path in sys.argv[1:]:
    try:
        content = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue

    for m in CLERK_ENV_IF.finditer(content):
        window = content[m.start(): m.start() + WINDOW_CHARS]
        if HEADER_FALLBACK.search(window):
            # Find approximate line number
            line_no = content[: m.start()].count("\n") + 1
            violations.append((path, line_no, m.group(0)[:80]))

if violations:
    print("FAIL: env-var-conditional auth bypass detected.\n")
    for path, line_no, snippet in violations:
        print(f"  {path}:{line_no}")
        print(f"    matched: {snippet!r}")
        print()
    print("Fix: replace conditional with unconditional auth():")
    print("  const { orgId } = auth()")
    print("  if (!orgId) return Response.json({ error: 'Unauthorized' }, { status: 401 })")
    print()
    print("Misconfigured env (missing CLERK_SECRET_KEY) should cause a 500,")
    print("NOT silently fall through to zero-auth header reads.")
    sys.exit(1)

print(f"OK: scanned {len(sys.argv) - 1} file(s) — no env-var-conditional auth bypass found.")
sys.exit(0)
