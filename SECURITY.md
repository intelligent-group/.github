# Security policy

## Reporting a vulnerability

Email **mruiz@intelligentit.io** with subject `[SECURITY] <repo-name>`.

Please include:

- A clear description of the vulnerability
- Steps to reproduce
- Affected commits / branches / deployments if known
- Your suggested severity (informational / low / medium / high / critical)

## What we commit to

- Acknowledge receipt within 2 business days
- Provide a remediation timeline within 5 business days
- Credit you in the fix release notes (unless you prefer anonymity)

## Scope

In scope: any code in this GitHub organization, customer-facing AiT product
URLs (`*.intelligentit.io`, `aitcrm.intelligentit.io`, `aitattend.intelligentit.io`,
`aitcsg.intelligentit.io`), and the `intelligent-group-ait` GCP project.

Out of scope: third-party services we depend on (Supabase, Vercel, Clerk,
GCP — please report directly to those vendors).

## What's NOT a vulnerability

- Reports about missing security headers on internal-only / staging URLs
- Theoretical issues without reproduction steps
- Social engineering / phishing scenarios that require Manuel to take an
  action he wouldn't normally take
