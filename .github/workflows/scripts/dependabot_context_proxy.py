#!/usr/bin/env python3
"""
Dependabot-context PROXY test: extracts a workflow's dependabot skip-check
step and re-executes the REAL run: block (not a reimplementation) under a
restricted GITHUB_TOKEN (contents: read only) with no custom secrets, to
catch the class of bug where that step crashes ungracefully instead of
degrading to a safe default.

Scope: this only recognizes ONE concrete pattern -- a step whose `run:`
writes `skip=<true|false|$var>` to $GITHUB_OUTPUT, gated on
`github.actor == 'dependabot[bot]'`. It does not attempt to execute
arbitrary workflow steps. See _dependabot-context-proxy.yml header comment
for the full scope statement (what this catches / does not catch).
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

SKIP_OUTPUT_RE = re.compile(
    r'skip=(?:true|false|\$\{?\w+\}?)"?\s*>>\s*"?\$\{?GITHUB_OUTPUT\}?"?'
)

# Known-safe GitHub Actions expressions this proxy can substitute with a
# fixture value. Anything else found in the extracted step is unsupported
# and causes a loud failure rather than a silent/incorrect substitution.
def build_expr_subs(ctx):
    return [
        (re.compile(r'\$\{\{\s*github\.actor\s*\}\}'), ctx['actor']),
        (re.compile(r'\$\{\{\s*github\.repository\s*\}\}'), ctx['repository']),
        (re.compile(r'\$\{\{\s*github\.repository_owner\s*\}\}'), ctx['repository_owner']),
        (re.compile(r'\$\{\{\s*github\.event_name\s*\}\}'), ctx['event_name']),
        (re.compile(r'\$\{\{\s*github\.event\.action\s*\}\}'), ctx['event_action']),
        (re.compile(r'\$\{\{\s*github\.event\.pull_request\.base\.sha\s*\}\}'), ctx['base_sha']),
        (re.compile(r'\$\{\{\s*github\.event\.pull_request\.head\.sha\s*\}\}'), ctx['head_sha']),
        (re.compile(r'\$\{\{\s*github\.event\.pull_request\.number\s*\}\}'), ctx['pr_number']),
        (re.compile(r'\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}'), ctx['github_token']),
        (re.compile(r'\$\{\{\s*github\.token\s*\}\}'), ctx['github_token']),
    ]

LEFTOVER_EXPR_RE = re.compile(r'\$\{\{[^}]*\}\}')
CUSTOM_SECRET_RE = re.compile(r'secrets\.(\w+)')

MUTATING_HINT_RE = re.compile(
    r'\bbranches\s+create\b|\bbranches\s+delete\b|migrate\s+deploy|-X\s*(POST|PUT|DELETE|PATCH)'
    r'|gcloud\s+\S+\s+(create|delete|deploy)|terraform\s+apply|\bnpm\s+publish\b',
    re.IGNORECASE,
)


def find_skip_step(workflow_path):
    with open(workflow_path) as f:
        doc = yaml.safe_load(f)
    jobs = doc.get('jobs', {})
    for job_name, job in jobs.items():
        steps = job.get('steps', [])
        for idx, step in enumerate(steps):
            run = step.get('run', '') or ''
            if SKIP_OUTPUT_RE.search(run):
                return job_name, idx, step, steps
    return None, None, None, None


def substitute(text, ctx):
    """Returns (substituted_text, custom_secrets_found, unsupported_exprs)."""
    if text is None:
        return None, [], []
    for pattern, value in build_expr_subs(ctx):
        text = pattern.sub(value, text)
    custom_secrets = []
    unsupported = []
    for m in LEFTOVER_EXPR_RE.finditer(text):
        expr = m.group(0)
        sec = CUSTOM_SECRET_RE.search(expr)
        if sec:
            custom_secrets.append(sec.group(1))
        else:
            unsupported.append(expr)
    for name in custom_secrets:
        text = re.sub(re.escape('${{ secrets.%s }}' % name), '', text)
        text = re.sub(r'\$\{\{\s*secrets\.%s\s*\}\}' % re.escape(name), '', text)
    return text, sorted(set(custom_secrets)), sorted(set(unsupported))


def run_extracted_step(step, ctx, cwd):
    """Executes the step's real run: block under the restricted fixture context.
    Returns dict with exit_code, stdout, stderr, outputs, custom_secrets, unsupported.
    """
    run_text = step.get('run', '')
    env_block = step.get('env', {}) or {}

    sub_run, secrets_in_run, unsupported_in_run = substitute(run_text, ctx)

    sub_env = {}
    secrets_in_env = []
    unsupported_in_env = []
    for k, v in env_block.items():
        sv, secs, unsup = substitute(str(v), ctx)
        sub_env[k] = sv
        secrets_in_env += secs
        unsupported_in_env += unsup

    custom_secrets = sorted(set(secrets_in_run + secrets_in_env))
    unsupported = sorted(set(unsupported_in_run + unsupported_in_env))

    if unsupported:
        return {
            'ran': False,
            'exit_code': None,
            'stdout': '',
            'stderr': '',
            'outputs': {},
            'custom_secrets': custom_secrets,
            'unsupported': unsupported,
        }

    with tempfile.TemporaryDirectory() as tmp:
        output_file = os.path.join(tmp, 'github_output')
        open(output_file, 'w').close()

        proc_env = dict(os.environ)
        proc_env.update(sub_env)
        proc_env['GITHUB_OUTPUT'] = output_file
        # Custom secrets are deliberately absent from proc_env -- this is the
        # core of the proxy: dependabot-triggered runs never receive them.
        for name in custom_secrets:
            proc_env.pop(name, None)

        shell = step.get('shell', 'bash')
        shell_cmd = ['bash', '-c'] if shell in ('bash', None) else ['sh', '-c']

        try:
            proc = subprocess.run(
                shell_cmd + [sub_run],
                cwd=cwd,
                env=proc_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            exit_code = -1
            stdout, stderr = (e.stdout or ''), 'TIMEOUT after 60s'

        outputs = {}
        with open(output_file) as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    k, _, v = line.partition('=')
                    outputs[k] = v

        return {
            'ran': True,
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'outputs': outputs,
            'custom_secrets': custom_secrets,
            'unsupported': unsupported,
        }


def static_gate_check(steps, skip_idx, skip_step_id):
    """Class-4 static check: a job runs its steps sequentially and unconditionally
    unless each step has its OWN `if:` gate -- gating only the mutating/secret step
    itself is not sufficient if an earlier, ungated step (e.g. a CLI install) can
    fail first and never let execution reach the gated step at all (real incident:
    ait-soc-sentinel PR #772, ungated `supabase/setup-cli` blocked the
    already-gated `branches create` step). So: find the LAST step that references
    a custom secret or looks state-mutating, then require EVERY step between the
    skip-check step and that one (inclusive) to carry its own gate."""
    tail = steps[skip_idx + 1:]

    def is_guard_worthy(step):
        run = step.get('run', '') or ''
        uses = step.get('uses', '') or ''
        env_block = step.get('env', {}) or {}
        env_text = ' '.join(str(v) for v in env_block.values())
        combined = run + ' ' + uses + ' ' + env_text
        references_custom_secret = bool(
            [m for m in CUSTOM_SECRET_RE.finditer(combined) if m.group(1) != 'GITHUB_TOKEN']
        )
        looks_mutating = bool(MUTATING_HINT_RE.search(combined))
        return references_custom_secret, looks_mutating

    last_guard_worthy_idx = None
    for i, step in enumerate(tail):
        secret, mutating = is_guard_worthy(step)
        if secret or mutating:
            last_guard_worthy_idx = i

    if last_guard_worthy_idx is None:
        return []

    gate_pattern = re.compile(r'steps\.%s\.outputs\.skip' % re.escape(skip_step_id))
    violations = []
    for i, step in enumerate(tail[:last_guard_worthy_idx + 1]):
        if_cond = step.get('if', '') or ''
        if not gate_pattern.search(if_cond):
            secret, mutating = is_guard_worthy(step)
            reason = 'custom secret' if secret else ('mutating call' if mutating else
                      'runs before a gated mutating/secret step and can block reaching it')
            violations.append({
                'name': step.get('name', step.get('uses', '<unnamed>')),
                'reason': reason,
                'if': if_cond or '(none)',
            })
    return violations


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', required=True, help='Path to workflow YAML to test')
    p.add_argument('--mode', required=True,
                    choices=['synthetic-no-migration', 'synthetic-with-migration', 'real-shas', 'static-only'])
    p.add_argument('--base-sha', default=None)
    p.add_argument('--head-sha', default=None)
    p.add_argument('--migration-test-path', default='supabase/migrations/00000000000000_dependabot_proxy_test.sql')
    p.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'intelligent-group/proxy-test'))
    p.add_argument('--github-token', default=os.environ.get('GITHUB_TOKEN', ''))
    p.add_argument('--expect-skip', default=None, choices=['true', 'false'])
    p.add_argument('--allow-not-found', action='store_true',
                    help='Exit 0 (not 1) when no skip-check step is found in target')
    args = p.parse_args()

    job_name, idx, step, steps = find_skip_step(args.target)
    if step is None:
        msg = f"No dependabot skip-check step found in {args.target} (pattern: writes skip=... to $GITHUB_OUTPUT)."
        if args.allow_not_found:
            print(f"::notice::{msg} Nothing to test.")
            sys.exit(0)
        print(f"::error::{msg}", file=sys.stderr)
        sys.exit(1)

    step_id = step.get('id', f'step{idx}')
    print(f"::notice::Found skip-check step '{step_id}' (job '{job_name}') in {args.target}")

    if args.mode == 'static-only':
        violations = static_gate_check(steps, idx, step_id)
        if violations:
            print(f"::error::{len(violations)} step(s) after '{step_id}' reference a custom secret or "
                  f"perform a mutating call WITHOUT gating on steps.{step_id}.outputs.skip:")
            for v in violations:
                print(f"  - {v['name']!r} ({v['reason']}), if: {v['if']}")
            sys.exit(1)
        print(f"::notice::static gate check passed: all downstream secret/mutating steps are gated on '{step_id}'")
        sys.exit(0)

    with tempfile.TemporaryDirectory() as repo_dir:
        base_sha, head_sha = args.base_sha, args.head_sha
        run_text = step.get('run', '')
        is_api_based = bool(re.search(r'curl.*api\.github\.com', run_text))

        if args.mode in ('synthetic-no-migration', 'synthetic-with-migration'):
            if is_api_based:
                print(f"::notice::step '{step_id}' performs a live API call (Compare-commits style); "
                      f"local synthetic-git fixtures don't apply here -- use --mode real-shas. Skipping (not a failure).")
                sys.exit(0)
            # Build a real origin remote (bare repo) + a shallow clone that only has
            # HEAD, not base_sha -- this mirrors real CI shallow-checkout behavior,
            # since the extracted script does `git fetch --depth=1 origin <base_sha>`
            # and needs a working `origin` to fetch from.
            bare_dir = os.path.join(repo_dir, 'origin.git')
            work_dir = os.path.join(repo_dir, 'work')
            subprocess.run(['git', 'init', '-q', '--bare', bare_dir], check=True)
            subprocess.run(['git', 'init', '-q', '-b', 'main', work_dir], check=True)
            subprocess.run(['git', '-C', work_dir, 'config', 'user.email', 'proxy@intelligentit.io'], check=True)
            subprocess.run(['git', '-C', work_dir, 'config', 'user.name', 'dependabot-proxy'], check=True)
            subprocess.run(['git', '-C', work_dir, 'remote', 'add', 'origin', bare_dir], check=True)
            open(os.path.join(work_dir, 'README.md'), 'w').write('base\n')
            subprocess.run(['git', '-C', work_dir, 'add', '.'], check=True)
            subprocess.run(['git', '-C', work_dir, 'commit', '-q', '-m', 'base'], check=True)
            subprocess.run(['git', '-C', work_dir, 'push', '-q', 'origin', 'main'], check=True)
            base_sha = subprocess.run(['git', '-C', work_dir, 'rev-parse', 'HEAD'],
                                       capture_output=True, text=True, check=True).stdout.strip()
            if args.mode == 'synthetic-with-migration':
                mig_path = os.path.join(work_dir, args.migration_test_path)
                os.makedirs(os.path.dirname(mig_path), exist_ok=True)
                open(mig_path, 'w').write('-- proxy test migration\n')
            else:
                open(os.path.join(work_dir, 'CHANGELOG.md'), 'w').write('bump\n')
            subprocess.run(['git', '-C', work_dir, 'add', '.'], check=True)
            subprocess.run(['git', '-C', work_dir, 'commit', '-q', '-m', 'head'], check=True)
            subprocess.run(['git', '-C', work_dir, 'push', '-q', 'origin', 'main'], check=True)
            head_sha = subprocess.run(['git', '-C', work_dir, 'rev-parse', 'HEAD'],
                                       capture_output=True, text=True, check=True).stdout.strip()
            exec_cwd = os.path.join(repo_dir, 'exec')
            subprocess.run(['git', 'clone', '-q', '--depth', '1', bare_dir, exec_cwd], check=True)
        else:  # real-shas
            if not (base_sha and head_sha):
                print("::error::--mode real-shas requires --base-sha and --head-sha", file=sys.stderr)
                sys.exit(2)
            exec_cwd = os.getcwd()

        ctx = {
            'actor': 'dependabot[bot]',
            'repository': args.repository,
            'repository_owner': args.repository.split('/')[0],
            'event_name': 'pull_request',
            'event_action': 'synchronize',
            'base_sha': base_sha or '',
            'head_sha': head_sha or '',
            'pr_number': '999999',
            'github_token': args.github_token,
        }

        result = run_extracted_step(step, ctx, exec_cwd)

    if result['unsupported']:
        print(f"::error::step '{step_id}' contains expressions this proxy doesn't know how to substitute: "
              f"{result['unsupported']} -- extend the allowlist in dependabot_context_proxy.py or degrade "
              f"this target to --mode static-only.", file=sys.stderr)
        sys.exit(1)

    if result['custom_secrets']:
        print(f"::notice::custom secrets referenced by this step and left EMPTY (dependabot-context proxy): "
              f"{result['custom_secrets']}")

    print(f"::notice::exit_code={result['exit_code']} outputs={result['outputs']}")
    if result['stdout']:
        print("--- stdout ---")
        print(result['stdout'])
    if result['stderr']:
        print("--- stderr ---")
        print(result['stderr'])

    if result['exit_code'] != 0:
        print(f"::error::skip-check step '{step_id}' EXITED NON-ZERO ({result['exit_code']}) under the "
              f"restricted dependabot-proxy context. A real dependabot run would fail the same way instead "
              f"of degrading to a safe default.", file=sys.stderr)
        sys.exit(1)

    if 'skip' not in result['outputs']:
        print(f"::error::skip-check step '{step_id}' exited 0 but never wrote a 'skip' output.", file=sys.stderr)
        sys.exit(1)

    if args.expect_skip is not None and result['outputs']['skip'] != args.expect_skip:
        print(f"::error::expected skip={args.expect_skip}, got skip={result['outputs']['skip']}", file=sys.stderr)
        sys.exit(1)

    print(f"::notice::PASS -- skip='{result['outputs']['skip']}' computed cleanly under restricted dependabot-proxy context")
    sys.exit(0)


if __name__ == '__main__':
    main()
