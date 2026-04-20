# daily-report-skill

Claude Code skill for generating Chinese daily reports from session jsonl, GitHub activity, and facet metrics. The report is written for the author themselves (not a public blog audience), optimized for "six months later re-reading."

## How it works

When the user asks their Claude Code agent "写今天的日报" or "/daily-report 2026-04-19", this skill takes over:

1. **Bootstrap** — resolves a UTC+8 window, collects all Claude Code sessions and GitHub events in that window, aggregates token statistics.
2. **Session pipeline** — dispatches `session-reader` / `session-merger` sub-agents to compress raw jsonl into session cards + facets.
3. **Writing** — Opus writes the main body; Codex produces an independent opposing view; a neutral Claude sub-agent reconciles.
4. **Candidates** — another Opus pass extracts reflection / suggestion / memory candidates, each validated by a Haiku reviewer.
5. **Publish** — pushes to the author's Hexo blog + `facets` submodule, applies memory deltas, sends email and a final cc-connect notification.

All mechanical steps (window resolution, filtering, lint, template fill, publish) are Python scripts. The agent only handles writing judgement.

## Install

### Claude Code

Claude Code discovers user-level skills under `~/.claude/skills/<name>/`.

Ask your Claude Code agent to run:

    Fetch and follow instructions from https://raw.githubusercontent.com/moesin-lab/daily-report-skill/main/INSTALL.md


```bash
git clone git@github.com:moesin-lab/daily-report-skill.git ~/.claude/skills/daily-report
```

    Read ~/.claude/skills/daily-report/INSTALL.md and execute every step in order. Stop on any failure. Do not invent values that I need to fill in.

Or run the minimal sequence yourself:

```bash
git clone git@github.com:moesin-lab/daily-report-skill.git ~/.claude/skills/daily-report
cd ~/.claude/skills/daily-report
bash scripts/install-hooks.sh
bash scripts/install-agents.sh
cp .env.example .env                       # then edit required keys
```

See [`INSTALL.md`](INSTALL.md) for the full agent-executable checklist with verification steps, and [Configuration](#configuration) for the `.env` reference.

### Other CLIs

Codex CLI / Cursor / OpenCode / Gemini CLI: **currently unsupported.** This skill dispatches `session-reader` / `session-merger` sub-agents via Claude Code's `Agent` tool; no equivalent mechanism in other CLIs yet.

## Trigger

```
/daily-report
/daily-report 2026-04-19
/daily-report WINDOW_END=1745020800
```

Or plain natural language: "生成今天的日报".

## Configuration

### `.env` — required

Bootstrap refuses to run without all three.

| Key | Example | Purpose |
|---|---|---|
| `GITHUB_USER` | `your-login` | GitHub activity collection |
| `DAILY_REPORT_REPO` | `your-login/your-blog-repo` | publish verification |
| `DAILY_REPORT_EMAIL_TO` | `you@example.com` | email recipient |

### `.env` — strongly recommended

Without these, identity falls back to neutral "作者" / "Claude Agent" / "用户".

| Key | Used by | Example |
|---|---|---|
| `AUTHOR_NAME` | signature text | `Your Name` |
| `AUTHOR_URL` | signature link | `https://github.com/your-login` |
| `AUTHOR_AGENT_NAME` | "给自己（…）" header | `YourAgent` |
| `USER_NAME` | "给用户（…）" header | `YourUser` |

### `.env` — optional

Hook overrides, `cc-connect` session overrides, Codex group id — see `.env.example` for the full catalog.

### Runtime dependencies

| Tool | Needed for | If absent |
|---|---|---|
| `cc-connect` | `DR_NOTIFY_CMD` default | `DR_NOTIFY_CMD=:` silences |
| `mails` CLI | `DR_MAIL_CMD` default | `DR_MAIL_CMD=:` silences |
| `codex` CLI | Opposing-view review | auto-degrades to positive-only |
| Hexo blog + `facets` submodule | blog publish | required — no fallback |

### `PERSONA.md` — optional narrative voice

```bash
cp PERSONA.example.md PERSONA.md
```

Unlike `.env` (mechanical substitution), `PERSONA.md` is free-form guidance the writing agent reads as a style reference.

## How the agent runs this

The entry point is `SKILL.md`, loaded by Claude Code when the user triggers the skill. `SKILL.md` directs the agent through five workflows under `reference/workflows/`:

- `00-bootstrap` — window, sessions, token stats
- `01-session-pipeline` — session-reader / session-merger / facet publish
- `01b-outside-notes` — sandbox-outside notes aggregation (optional)
- `02-write-review` — main body → privacy → opposing → neutral → candidates → final assembly → TL;DR
- `03-publish-notify` — blog push, memory deltas, email, final notification

`99-rules.md` lists privacy and failure-mode rules enforced at every step.

## Pluggable hooks

These env variables override the default implementations without editing skill code:

| Variable | Default | Contract |
|---|---|---|
| `DR_NOTIFY_CMD` | `scripts/publish/send-cc-notification.sh` | argv[1] = message, or stdin if no argv |
| `DR_MAIL_CMD` | `scripts/publish/send-email.sh` | reads `TARGET_DATE` / `RUN_DIR` env, argv[1] = markdown path (optional) |
| `DR_FACETS_PUBLISH_CMD` | `scripts/publish/publish-artifacts.sh` | reads `TARGET_DATE` / `RUN_DIR` env |
| `DR_MAIL_SUCCESS_GREP` | `Sent via mails.dev` | success-marker regex for the mail command's log |

Use `DR_NOTIFY_CMD=:` (shell no-op) to silence any hook entirely.

## Security

Two-layer protection against committing local identity / credentials:

1. `.gitignore` never tracks `.env` / `PERSONA.md` by default.
2. `hooks/pre-commit` refuses commits containing either file in the stage, including `git add -f` override.

Both layers must fail for a leak. The hook is a local convention; for a remote enforcement layer, add a GitHub Action on push/PR to scan diff (not included by default).

## Sub-agent model policy

| Task | Model |
|---|---|
| Privacy review, candidate validator, one-shot script runner | Haiku |
| `session-reader` (structured compression) | Sonnet (default), Haiku allowed for short / cached, never Opus |
| `session-merger` | Sonnet default, Opus for cross-3+ sessions or contradictions |
| Main-body writing, candidate generator, final assembly, neutral analysis | Opus |
| Opposing view | Codex (external, via `codex-review` skill) |

## Development

```bash
cd scripts
python3 -m unittest discover -s tests
```

All scripts are stdlib-only. No pip install.

### Layout

```
.
├── SKILL.md                    # agent entry, read first
├── PERSONA.example.md          # identity / voice template
├── .env.example                # full config catalog
├── hooks/pre-commit            # blocks .env / PERSONA.md commits
├── agents/                     # bundled sub-agent definitions (session-reader / session-merger)
├── reference/                  # progressive-disclosure workflow docs
│   ├── workflows/
│   ├── prompts/
│   └── templates/
└── scripts/                    # stdlib-only Python + shell
    ├── bootstrap.py            # window, sessions, tokens, GH events, .env loader
    ├── window/
    ├── collect/
    ├── session/
    ├── review/
    ├── publish/
    ├── tests/
    ├── install-hooks.sh        # enable pre-commit hook
    └── install-agents.sh       # sync agents/*.md to ~/.claude/agents/
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `GITHUB_USER is required` | `.env` missing or bootstrap wasn't run (direct-invoking a sub-script bypasses `_load_dotenv`). Enter the workflow from its documented entry. |
| Signature shows "作者 — Claude Agent" | `AUTHOR_*` env not loaded. Confirm `.env` exists and the calling process went through `bootstrap.py`. |
| Email fails with `bun: No such file` | `mails` CLI (default `DR_MAIL_CMD`) needs `bun` runtime; install `bun`, or set `DR_MAIL_CMD=:` to skip email. |
| `pre-commit: 拒绝提交 .env` | Intended behavior. Never force-add `.env`. Put your values in `.env`, not elsewhere. |
| `core.hooksPath` not set | Step 2 was skipped. Run `bash scripts/install-hooks.sh`. |
| `Agent` tool reports `session-reader` / `session-merger` not found | Step 2.5 was skipped. Run `bash scripts/install-agents.sh`. |

## License

MIT License — see `LICENSE`.

## Authors

- **Sentixxx** — author / spec / product decisions
- **sentixA** — Claude Code agent implementer
- **Claude Opus 4.7 (1M context)** — underlying model

## Related

- [obra/superpowers](https://github.com/obra/superpowers) — general-purpose skill methodology for coding agents; its install / philosophy shape informed this README.
