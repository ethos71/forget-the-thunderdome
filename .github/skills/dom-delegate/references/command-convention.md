# Bot command convention — `@<bot> --<command>`

The one rule for how any bot in this org exposes and runs commands.

## The rule

**Invoke a bot command as `@<bot> --<command>`** — the bot (agent) followed by
a `--flag`:

```
@smartballz --usage        @job --task src/x.py 'fix typo' 'echo ok'
@dom --update              @nyx --status
```

**Never a bare `/<command>`.** Bare slash-commands collide with:
- **Claude Code built-ins:** `/usage`, `/init`, `/review`, `/model`, `/help`,
  `/status`, `/clear`, `/compact`, … (this is why the usage report is
  `@bot --usage` / `dom usage`, not `/usage`).
- **GitHub Copilot** slash-commands.

Namespacing every command under the bot is the unique surface that can't clash.

## How it wires up

`--<command>` maps to the shell umbrella `dom <command>` (see
`.github/commands/dom`), or to a repo-provided script for repo-specific
commands (e.g. `dom start` → `.github/commands/start`). A bot's agent persona
(`.github/agents/<bot>.md`) documents which `--<command>` flags it answers; the
canonical index lives in the shipped `@dom` persona (`.github/agents/dom.md`).

## Adding a new command

1. Add a `dom <command>` subcommand to `.github/commands/dom`.
2. Add a `--<command>` row to the index in `.github/agents/dom.md`.
3. Have the owning bot's persona map `@<bot> --<command>` → `dom <command>`.

Do **not**: create a `.claude/commands/<name>.md` slash-command, add a root
`/<name>` script meant to be typed as `/<name>`, or document any feature as a
bare `/<command>`.
