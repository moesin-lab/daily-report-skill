# INSTALL.md — Agent-executable installation walkthrough

You are a Claude Code (or equivalent) agent helping install the `daily-report` skill. Execute the steps below in order. After each step, verify the expected outcome and stop immediately if any check fails — do **not** continue to later steps on a failure. Report failures to the user with the exact error; do not silently recover.

## Step 0 — Place the skill at `~/.claude/skills/daily-report/`

Verify the skill is already at Claude Code's user-level skill discovery path:

```bash
test -f ~/.claude/skills/daily-report/SKILL.md && echo OK || echo MISSING
```

If `OK`: skip to Step 1.

If `MISSING`: ask the user which placement strategy they want. Do **not** pick silently.

> I don't find daily-report at ~/.claude/skills/daily-report. How should I install it?
>
> - **A) Standalone clone** (simplest — the skill has its own independent git dir)
> - **B) Git submodule** (if ~/.claude is itself a git repo you back up elsewhere)

On **A**, run:

```bash
git clone git@github.com:moesin-lab/daily-report-skill.git ~/.claude/skills/daily-report
```

On **B**, run (must be executed from the `~/.claude` repo root):

```bash
cd ~/.claude
git submodule add git@github.com:moesin-lab/daily-report-skill.git skills/daily-report
git commit -m "chore: add daily-report skill submodule"
```

Prefer SSH. If the user reports SSH auth failure, ask whether to switch to HTTPS (`https://github.com/moesin-lab/daily-report-skill.git`) — do not auto-fallback; HTTPS on a private repo needs a valid `GH_TOKEN`.

After placing, re-run the `test -f` check. Must print `OK` before continuing.

## Step 1 — Check prerequisites

```bash
claude --version
python3 --version
git --version
gh auth status
```

Expected: all four print version / auth info without error.

Python must be `>= 3.11`. If not, stop and tell the user.

## Step 2 — Install pre-commit hook

```bash
cd ~/.claude/skills/daily-report
bash scripts/install-hooks.sh
```

Expected stdout contains: `core.hooksPath=hooks`.

Verify:

```bash
git -C ~/.claude/skills/daily-report config --get core.hooksPath
```

Expected: `hooks`.

## Step 3 — Install bundled sub-agents

```bash
cd ~/.claude/skills/daily-report
bash scripts/install-agents.sh
```

Expected stdout ends with: `[install-agents] mode=symlink installed=N into /home/…/.claude/agents` where `N` is the number of agent files that were newly linked. Already-installed identical files are skipped silently (not an error).

Verify:

```bash
ls ~/.claude/agents/ | grep -E "^session-(reader|merger)"
```

Expected: five lines, matching `session-reader.md`, `session-reader.card.md`, `session-reader.facet.md`, `session-merger.md`, `session-merger.card.md`.

## Step 4 — Create `.env` from template

Check whether `.env` already exists. **Do not overwrite it** if it does.

```bash
test -f ~/.claude/skills/daily-report/.env && echo EXISTS || echo MISSING
```

If `MISSING`: copy the template and ask the user to fill in required values. You as the agent must **not invent values** for these.

```bash
cp ~/.claude/skills/daily-report/.env.example ~/.claude/skills/daily-report/.env
```

Then present the user with this block and ask them to fill in the three required keys:

```
Required (skill refuses to run without these):
  GITHUB_USER=<your GitHub login>
  DAILY_REPORT_REPO=<owner/repo of your blog>
  DAILY_REPORT_EMAIL_TO=<email address for the daily report>

Strongly recommended (otherwise identity falls back to neutral "作者" / "用户"):
  AUTHOR_NAME=<display name>
  AUTHOR_URL=<your GitHub profile or homepage>
  AUTHOR_AGENT_NAME=<the agent-as-author name, e.g. MyAgent>
  USER_NAME=<your collaborator's name>
```

Wait for the user to confirm they have saved the file before continuing.

## Step 5 — (Optional) Create `PERSONA.md`

Ask the user: "Do you want to define a custom narrative voice via `PERSONA.md`? (y/N)"

If yes:

```bash
cp ~/.claude/skills/daily-report/PERSONA.example.md ~/.claude/skills/daily-report/PERSONA.md
```

Then show the user `PERSONA.example.md` and tell them to edit `PERSONA.md` with their preferences.

## Step 6 — Smoke-test `.env` loading

```bash
cd ~/.claude/skills/daily-report
env -i HOME="$HOME" PATH="$PATH" python3 scripts/bootstrap.py \
  --skip-github --args 2026-01-01 --run-dir /tmp/dr-smoke 2>&1 | head -20
```

Expected: stdout contains `export GITHUB_USER='…'` (the value the user set), and does **not** contain `is required` errors.

If you see `$VAR is required`: `.env` is missing that key or has an empty value. Stop and report.

## Step 7 — Smoke-test identity injection

```bash
cd ~/.claude/skills/daily-report
env -i HOME="$HOME" PATH="$PATH" python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('b', 'scripts/bootstrap.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import subprocess
print(subprocess.run(['python3', 'scripts/publish/render-signature.py'],
                    capture_output=True, text=True).stdout)
"
```

Expected: the rendered signature contains the user's `AUTHOR_NAME` and `AUTHOR_URL`, **not** the neutral fallback `作者 — Claude Agent`.

If you see neutral fallback: `AUTHOR_*` keys are missing or empty. Tell the user to set them in `.env` and rerun this step.

## Step 8 — Run the test suite (optional sanity check)

```bash
cd ~/.claude/skills/daily-report/scripts
python3 -m unittest discover -s tests 2>&1 | tail -3
```

Expected last line: `OK` and total test count (currently 98).

If any test fails: stop and report to user. This is not blocking for install, but signals a possibly broken checkout.

## Step 9 — Report completion

If all previous steps passed, tell the user:

> `daily-report` skill installed at `~/.claude/skills/daily-report`. To generate today's report, say "写今天的日报" or run `/daily-report`. The skill entry `SKILL.md` has been discovered by Claude Code and will activate automatically.

If any optional dependency is missing (`cc-connect`, `mails`, `codex`), mention what degrades:
- no `cc-connect` → set `DR_NOTIFY_CMD=:` in `.env` or final notification fails
- no `mails` → set `DR_MAIL_CMD=:` or email fails
- no `codex` → opposing-view review auto-degrades to positive-only

Stop. Do not trigger a daily report yourself; wait for the user to ask.
