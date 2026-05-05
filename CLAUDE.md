# Default Claude Code rules — inherited by every MRoot2025 repo

This is the **fallback `CLAUDE.md`** that GitHub auto-applies to any owned
repo that doesn't have its own. The canonical, fully-detailed rule set lives
at `MRoot2025/ait-claude-config/CLAUDE.md`. **Read that for the actual rules**;
this file is a pointer + the highest-priority items.

---

## Inherited from `MRoot2025/ait-claude-config`

The canonical mirror at `MRoot2025/ait-claude-config/CLAUDE.md` is the source
of truth. To clone it locally:

```bash
git clone https://github.com/MRoot2025/ait-claude-config ~/Projects/ait-claude-config
```

Then read `~/Projects/ait-claude-config/CLAUDE.md` for: Identity & Role,
Operating Mode (Research → Plan → Execute → Report), Decision Authority,
Automation Preferences, Non-Negotiables, Tenants, Toolchain, Default Dev
Stack, Tech Operations Stack, AI Stack, GCP Projects, Critical Known
Patterns, Code Standards, Agent Hierarchy, and Learn Protocol.

## Hard rules to surface immediately on every repo (do NOT violate even if local CLAUDE.md disagrees)

1. **NEVER overwrite rule/config files.** `CLAUDE.md`, `settings.json`,
   `agents/*.md`, `skills/*/SKILL.md`, `BUILD_MANIFEST.md`, `MEMORY.md` —
   default mode is APPEND or surgical Edit. Whole-file Write requires
   triple-confirm: state intent → show diff → wait for explicit "go" from
   Manuel.
2. **Secrets in GCP Secret Manager only** (project `intelligent-group-ait`).
   Never inline in chat / files / commits. Use the `secret-store` skill.
   Inline pastes are treated as exposed and rotated.
3. **`/remote-control` is the default session state.** Manuel runs it on
   every Claude Code session for mobile/phone access; assume it's enabled.
4. **Manuel is CEO, not a typing proxy.** All terminal commands run via
   Claude Code tool calls. "Open a separate terminal" is never the answer;
   if a script must run on the local shell, use the `! <command>` prefix in
   the same Claude Code session.
5. **PLAN → VALIDATE → CONFIRM → EXECUTE.** No exceptions for destructive
   or bulk ops. Get explicit confirmation before any irreversible action.
6. **Use agents in parallel by default** — single tool-use block, multiple
   Agent calls. Sequential only when one agent's output is required input
   to the next.
7. **After 2 failed fix attempts:** STOP, dispatch a research agent
   autonomously (no "want me to research?" pause), apply findings, retry,
   report.
8. **IG branding mandatory in customer-facing artifacts.** Logo + color
   tokens (teal `#05D2AB`, ink `#0c0c0c`) + Geist Sans/Mono. Brand reference
   in `MRoot2025/ait-claude-config/memory/reference_ig_brand.md`.

## Identity & Role (capsule)

Manuel Ruiz — Founder, CEO, and Chief Information Security Officer at
**Intelligent IT** (managed IT services / MSP). Front Row Group is a CLIENT,
not employer. GitHub: `MRoot2025` (private repos, HTTPS remotes). Primary
email: `mruiz@intelligentit.io`.

## Where to find the rest

- **Full rule set:** `MRoot2025/ait-claude-config/CLAUDE.md`
- **Memory (cross-session knowledge):** `MRoot2025/ait-claude-config/memory/*.md`
- **Build manifest (deferred work):** `MRoot2025/ait-claude-config/BUILD_MANIFEST.md`
- **Project template (new-repo bootstrap):** `MRoot2025/ait-claude-config/project-template/CLAUDE.md`
- **Stack-bootstrap skill (per-vendor automation):** `MRoot2025/ait-claude-config/skills/stack-bootstrap/SKILL.md`

If you're a fresh Claude Code session and have access to the local
filesystem, prefer reading the local clone of `ait-claude-config` directly —
it's always the most current version.
