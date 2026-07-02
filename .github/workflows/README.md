# Intelligent Group Reusable Workflow Gates

Shared CI/CD gates for all IG product repositories. Each gate prevents a class of production incidents.

## Gate Catalog

### `ig-product-gates.yml`
**Wires:** Every Next.js product deploying to production.

**Gates:**
- **Gate A** — Next.js CVE floor (minimum secure version)
- **Gate B** — Clerk CSP includes satellite FAPI host
- **Gate C** — Clerk instance allowed_origins includes product URL
- **Gate D** — /sign-in route resolves (not 404)

**Usage:**
```yaml
jobs:
  gates:
    uses: intelligent-group/.github/.github/workflows/ig-product-gates.yml@main
    with:
      product_url: https://myproduct.intelligentit.io
      next_config_path: next.config.ts
    secrets:
      CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}
```

---

### `supabase-pool-compliance-gate.yml`
**Wires:** Every service deploying to Cloud Run with Postgres backend (Supabase).

**Catches:**
1. **Missing DIRECT_URL with pgbouncer/Supavisor** → prisma migrate deploy crash-loop at boot
2. **Pool exhaustion** (connection_limit × max-instances > 190) → entire fleet query timeouts

**Incidents prevented:**
- 2026-06-25: ait-ai-gateway 26h outage (DIRECT_URL missing)
- 2026-06-26: Fleet-wide Supavisor pool exhaustion

**Usage:**
```yaml
jobs:
  pool-compliance:
    uses: intelligent-group/.github/.github/workflows/supabase-pool-compliance-gate.yml@main
    with:
      max_instances: '10'           # Cloud Run max-instances
      connection_limit: '2'         # Prisma datasource connection_limit
      skip_direct_url_check: false  # Set true only if not using Supavisor
```

**Configuration details:**

#### Gate A: DIRECT_URL Check
When DATABASE_URL uses Supavisor (port 6543) or pgbouncer, Prisma requires a direct connection to perform DDL migrations.

- **Problem:** Using only pgbouncer (port 6543) → prisma migrate deploy fails → container crash-loop
- **Solution:** Set DIRECT_URL to true Postgres port (5432):
  ```
  DIRECT_URL=postgresql://user:password@db.supabase.co:5432/postgres
  ```

#### Gate B: Pool Math
Supavisor has a hard 200-connection limit. Cloud Run instances each consume `connection_limit` connections from that pool.

- **Safe threshold:** ≤190 (5% headroom)
- **Warning threshold:** >150 (<75% of safe)
- **Crash threshold:** >190

**Example safe configs:**
```
max_instances=10, connection_limit=2  → 20 total (✓ safe)
max_instances=20, connection_limit=1  → 20 total (✓ safe)
max_instances=50, connection_limit=5  → 250 total (✗ crash)
```

---

## Integration Checklist

When adding a new service to Cloud Run:

- [ ] Add pool-compliance gate to service's main CI workflow
- [ ] Set `max_instances` to the value in your Cloud Run deploy config
- [ ] Set `connection_limit` from `schema.prisma` datasource or `DATABASE_URL` query param
- [ ] If using Supavisor (port 6543): confirm DIRECT_URL is set in Cloud Run secrets
- [ ] Run `git push` and verify gates pass on PR

---

## Gate Failures

### Gate A fails: "DIRECT_URL is MISSING"
You're using Supavisor (port 6543) but missing the direct connection URL.

**Fix:**
1. Set `DIRECT_URL` in Cloud Run deploy:
   ```bash
   gcloud run services update SERVICE_NAME \
     --update-secrets DATABASE_URL=key:version,DIRECT_URL=key:version
   ```
2. Redeploy to apply the new secret.

### Gate B fails: "Pool math EXCEEDS safe limit"
Your connection math is too high. Reduce either `max_instances` or `connection_limit`.

**Fix:**
1. Lower `max_instances` in your Cloud Run config, or
2. Lower `connection_limit` in `schema.prisma` / `DATABASE_URL`
3. Aim for ≤20 total connections initially; scale carefully after monitoring.

---

## References

- [Supabase Connection Pooling](https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooler)
- [Prisma with Supavisor](https://supabase.com/docs/guides/database/connecting-to-postgres#prisma)
- [Cloud Run Instance Scaling](https://cloud.google.com/run/docs/about-executions)
- Incident Report: ait-ai-gateway 2026-06-25 (P1, 26h outage, DIRECT_URL missing)
- Incident Report: Fleet-wide pool exhaustion 2026-06-26 (connection_limit overflow)
