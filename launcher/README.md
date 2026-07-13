# ftt desktop launcher

A no-terminal GUI front-end for **forget-the-thunderdome**. It sets up your
`profile.yaml` with a first-run wizard, then drives the existing CLIs
(`src/job_cli.py`, and the gmail tracker) from buttons — the same commands the
Quickstart runs, minus the terminal.

Built with **Tkinter** (Python standard library), so there is nothing extra to
install to run it from source.

## Run

```bash
python3 launcher/ftt_launcher.py
```

- **First run** (no `profile.yaml` yet): a scrollable wizard collects who you
  are, what roles/locations/comp you want, your story, and screening answers —
  the exact fields in `profile.yaml.example` — then writes `profile.yaml` at the
  repo root via `yaml.safe_dump`.
- **Later runs** (profile exists): you land straight on the main screen.

### Main screen

| Button        | What it runs                                                    |
|---------------|-----------------------------------------------------------------|
| Dashboard     | `python3 src/job_cli.py dashboard` (uses `dashboard --html` and opens the file in your browser automatically if/when the HTML flag lands in the CLI) |
| Find jobs     | `python3 src/job_cli.py jobs`                                    |
| Follow-ups    | `python3 src/job_cli.py follow-ups`                             |
| Sync email    | `python3 mcp-servers/gmail-server/gmail_tracker.py --sync --days 30` |
| Edit profile  | Re-opens the wizard, prefilled from your current `profile.yaml` |

Command output shows in a scrollable text area. Subprocess errors are caught and
displayed — the window never crashes on a failed command.

### Headless self-check (no window)

```bash
python3 launcher/ftt_launcher.py --check
```

Prints a report (Python version, whether `src/job_cli.py` exists, whether
`profile.yaml` exists, whether Tk is importable) and exits without opening a
window. Useful for CI and for confirming the install before you have a display.

## Architecture

Logic and UI are deliberately separated so the logic is testable without a
display:

- **Pure functions** (import-safe, no Tk touched at import time):
  `build_profile_dict`, `write_profile`, `profile_exists`, `load_profile`,
  `run_command`, `dashboard_supports_html`, `self_check`.
- **Tk UI**: `LauncherApp` / `launch_gui` import `tkinter` *inside* the
  function, so `import ftt_launcher` works on a headless box (no `$DISPLAY`).

## Packaging — turn this into a "no Python install" double-click app

Running from source needs Python. To hand someone a single file they can
double-click with **no Python installed**, freeze it with
[PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --onefile --windowed launcher/ftt_launcher.py
```

- `--onefile` bundles the Python runtime + Tk + your code into one executable.
- `--windowed` (aka `--noconsole`) suppresses the terminal so it launches like a
  native GUI app.

Output lands in `dist/`:

- **Linux** — `dist/ftt_launcher` (an ELF binary)
- **macOS** — `dist/ftt_launcher` plus a `.app` bundle (build on macOS)
- **Windows** — `dist/ftt_launcher.exe` (build on Windows)

PyInstaller does **not** cross-compile: build each platform's artifact on that
platform (or in CI runners for each OS).

This freeze step is the roadmap's "desktop launcher with no Python install"
deliverable. It is **not** run automatically here — this repo ships the source
launcher; freezing is an explicit, per-platform release step.

A convenience wrapper is included:

```bash
bash launcher/build.sh      # runs the PyInstaller command, or tells you how to install it
```

## Notes / caveats

- Actually *showing* the GUI needs a graphical display (`$DISPLAY` on Linux). On
  a headless machine use `--check`.
- The frozen app still expects the ftt repo layout (`src/job_cli.py`, `data/`,
  `profile.yaml`) alongside it, since it shells out to those CLIs.
