#!/usr/bin/env python3
"""
ftt desktop launcher — a GUI front-end for the forget-the-thunderdome
job-search toolkit.

Two layers live in this file:

  1. PURE LOGIC (no Tk, import-safe, no $DISPLAY needed)
       build_profile_dict, write_profile, profile_exists,
       run_command, self_check, dashboard_supports_html
     These are unit-testable and drive the CLIs in ``src/job_cli.py``.

  2. THE TK UI (LauncherApp + launch_gui/main)
       ``tkinter`` is imported *inside* the functions, never at module
       top level, so ``import ftt_launcher`` works headless (CI / --check).

Usage:
  python3 launcher/ftt_launcher.py            # open the GUI
  python3 launcher/ftt_launcher.py --check    # headless self-check, no window
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# This file lives in <repo>/launcher/ftt_launcher.py, so the repo root is the
# parent of the directory containing this file.
LAUNCHER_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAUNCHER_DIR.parent
JOB_CLI = REPO_ROOT / "src" / "job_cli.py"
DEFAULT_PROFILE = REPO_ROOT / "profile.yaml"


# ===========================================================================
# PURE LOGIC (display-free, import-safe)
# ===========================================================================

def _as_list(value) -> list[str]:
    """Coerce a wizard input into a clean list of strings.

    Accepts an actual list, or a string with newline- and/or comma-separated
    items. Blank entries are dropped and surrounding whitespace trimmed.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        text = str(value)
        # Split on newlines first, then commas within each line.
        items = []
        for line in text.splitlines():
            items.extend(line.split(","))
    return [str(item).strip() for item in items if str(item).strip()]


def _s(inputs: dict, key: str, default: str = "") -> str:
    """Fetch a scalar input as a stripped string."""
    val = inputs.get(key, default)
    return "" if val is None else str(val).strip()


def build_profile_dict(inputs: dict) -> dict:
    """Map flat wizard field inputs to the nested profile.yaml structure.

    The structure mirrors ``profile.yaml.example`` exactly: top-level keys
    ``identity``, ``search``, ``narrative``, ``answers``, ``email``,
    ``calendar``.

    List-style fields (target_roles, keywords, locations, target_companies,
    key_strengths, and work-history highlights) accept either a Python list
    or a newline/comma-separated string.
    """
    inputs = inputs or {}

    # ---- min_salary: tolerate "$120,000", "120k", "" -> int ----
    raw_salary = _s(inputs, "min_salary", "0")
    min_salary = 0
    if raw_salary:
        cleaned = raw_salary.lower().replace("$", "").replace(",", "").strip()
        mult = 1
        if cleaned.endswith("k"):
            mult = 1000
            cleaned = cleaned[:-1].strip()
        try:
            min_salary = int(float(cleaned) * mult)
        except ValueError:
            min_salary = 0

    remote_only = inputs.get("remote_only", True)
    if isinstance(remote_only, str):
        remote_only = remote_only.strip().lower() in ("1", "true", "yes", "y", "on")
    else:
        remote_only = bool(remote_only)

    identity = {
        "name": _s(inputs, "name"),
        "first_name": _s(inputs, "first_name"),
        "last_name": _s(inputs, "last_name"),
        "email": _s(inputs, "email"),
        "phone": _s(inputs, "phone"),
        "location": _s(inputs, "location"),
        "city": _s(inputs, "city"),
        "state": _s(inputs, "state"),
        "zip": _s(inputs, "zip"),
        "country": _s(inputs, "country", "United States"),
        "linkedin": _s(inputs, "linkedin"),
        "github": _s(inputs, "github"),
    }

    search = {
        "target_roles": _as_list(inputs.get("target_roles")),
        "keywords": _as_list(inputs.get("keywords")),
        "min_salary": min_salary,
        "remote_only": remote_only,
        "locations": _as_list(inputs.get("locations")),
        "target_companies": _as_list(inputs.get("target_companies")),
    }

    narrative = {
        "elevator_pitch": _s(inputs, "elevator_pitch"),
        "key_strengths": _as_list(inputs.get("key_strengths")),
        "tech_summary": _s(inputs, "tech_summary"),
        "work_history": _build_work_history(inputs),
    }

    answers = {
        "years_experience": _s(inputs, "years_experience"),
        "work_authorization": _s(inputs, "work_authorization"),
        "visa_sponsorship": _s(inputs, "visa_sponsorship"),
        "availability": _s(inputs, "availability"),
        "notice_period": _s(inputs, "notice_period"),
        "employment_type": _s(inputs, "employment_type"),
        "about_you": _s(inputs, "about_you"),
        "why_interested": _s(inputs, "why_interested"),
        "proudest_project": _s(inputs, "proudest_project"),
        "why_leaving": _s(inputs, "why_leaving"),
    }

    email = {"provider": _s(inputs, "email_provider", "gmail") or "gmail"}
    calendar = {"provider": _s(inputs, "calendar_provider", "ics") or "ics"}

    return {
        "identity": identity,
        "search": search,
        "narrative": narrative,
        "answers": answers,
        "email": email,
        "calendar": calendar,
    }


def _build_work_history(inputs: dict) -> list[dict]:
    """Build the work_history list.

    If ``work_history`` is already provided as a list of dicts, pass it
    through. Otherwise assemble a single most-recent entry from the flat
    wizard fields wh_company / wh_title / wh_years / wh_highlights. Returns
    an empty list if no work-history data was supplied.
    """
    wh = inputs.get("work_history")
    if isinstance(wh, list):
        return wh

    company = _s(inputs, "wh_company")
    title = _s(inputs, "wh_title")
    years = _s(inputs, "wh_years")
    highlights = _as_list(inputs.get("wh_highlights"))

    if not any([company, title, years, highlights]):
        return []

    entry: dict = {}
    if company:
        entry["company"] = company
    if title:
        entry["title"] = title
    if years:
        entry["years"] = years
    if highlights:
        entry["highlights"] = highlights
    return [entry]


def write_profile(data: dict, path: str | os.PathLike = "profile.yaml") -> str:
    """Write ``data`` as YAML to ``path`` using yaml.safe_dump.

    Returns the (string) path written. Keys are kept in insertion order
    (sort_keys=False) so the file reads top-to-bottom like the example.
    """
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            data,
            fh,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    return path


def profile_exists(path: str | os.PathLike = "profile.yaml") -> bool:
    """True if a profile YAML file exists at ``path``."""
    return os.path.isfile(os.fspath(path))


def load_profile(path: str | os.PathLike = "profile.yaml") -> dict:
    """Load a profile YAML file into a dict (empty dict if unreadable)."""
    try:
        with open(os.fspath(path), "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def run_command(args: list[str], cwd: str | os.PathLike | None = None) -> tuple[int, str]:
    """Run ``python3 src/job_cli.py <args>`` and capture combined output.

    ``args`` are the CLI arguments *after* the script name, e.g.
    ``["dashboard"]`` or ``["jobs", "--min-score", "70"]``.

    Returns ``(returncode, combined_output)``. Subprocess failures never
    raise — they come back as a non-zero return code with the error text in
    the output, so the GUI can display them without crashing.
    """
    cwd = os.fspath(cwd) if cwd is not None else str(REPO_ROOT)
    cmd = [sys.executable or "python3", str(JOB_CLI), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out after 600s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return 127, f"Could not run command: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return 1, f"Unexpected error running command: {exc}"


def dashboard_supports_html(cli_path: str | os.PathLike = JOB_CLI) -> bool:
    """Best-effort check for a ``dashboard --html`` flag in the CLI.

    The CLI in this repo renders a text dashboard today; an HTML renderer is
    on the roadmap. Rather than hard-code either answer, we scan the CLI
    source for an ``--html`` reference so the launcher automatically uses the
    HTML path the moment the flag lands.
    """
    try:
        text = Path(os.fspath(cli_path)).read_text(encoding="utf-8")
    except OSError:
        return False
    return "--html" in text


def self_check(profile_path: str | os.PathLike = DEFAULT_PROFILE) -> dict:
    """Verify the environment and return a report dict (no window).

    Reports Python version adequacy, presence of ``src/job_cli.py``, whether
    a profile exists, and whether Tkinter is importable in this interpreter.
    """
    py_ok = sys.version_info >= (3, 9)
    tk_available = False
    tk_error = None
    try:  # import here, not at module top level
        import tkinter  # noqa: F401
        tk_available = True
    except Exception as exc:  # ImportError or display-less environments
        tk_error = str(exc)

    report = {
        "python_version": ".".join(str(p) for p in sys.version_info[:3]),
        "python_ok": bool(py_ok),
        "repo_root": str(REPO_ROOT),
        "job_cli_path": str(JOB_CLI),
        "job_cli_exists": JOB_CLI.is_file(),
        "profile_path": str(profile_path),
        "profile_exists": profile_exists(profile_path),
        "dashboard_html_supported": dashboard_supports_html(),
        "tkinter_importable": tk_available,
        "display": os.environ.get("DISPLAY", ""),
    }
    if tk_error:
        report["tkinter_error"] = tk_error

    report["ok"] = bool(py_ok and report["job_cli_exists"])
    return report


def _format_report(report: dict) -> str:
    """Human-readable rendering of a self_check report."""
    width = max(len(k) for k in report)
    lines = ["ftt launcher — self check", "=" * 30]
    for key, value in report.items():
        lines.append(f"{key.rjust(width)} : {value}")
    return "\n".join(lines)


# ===========================================================================
# TK UI
# ===========================================================================

# Grouped field spec used by the wizard. Each entry:
#   (input_key, label, widget)  widget in {"entry", "text", "check"}
WIZARD_SECTIONS = [
    ("Who you are", [
        ("name", "Full name", "entry"),
        ("first_name", "First name", "entry"),
        ("last_name", "Last name", "entry"),
        ("email", "Email", "entry"),
        ("phone", "Phone", "entry"),
        ("location", "Location (display)", "entry"),
        ("city", "City", "entry"),
        ("state", "State", "entry"),
        ("zip", "ZIP / postal code", "entry"),
        ("country", "Country", "entry"),
        ("linkedin", "LinkedIn URL", "entry"),
        ("github", "GitHub URL", "entry"),
    ]),
    ("What you're looking for", [
        ("target_roles", "Target roles (one per line)", "text"),
        ("keywords", "Keywords (one per line)", "text"),
        ("min_salary", "Minimum base salary (USD)", "entry"),
        ("remote_only", "Remote only?", "check"),
        ("locations", "Acceptable locations (one per line)", "text"),
        ("target_companies", "Target companies (one per line)", "text"),
    ]),
    ("Your story", [
        ("elevator_pitch", "Elevator pitch", "text"),
        ("key_strengths", "Key strengths (one per line)", "text"),
        ("tech_summary", "Tech summary (one line)", "entry"),
        ("wh_company", "Most recent — company", "entry"),
        ("wh_title", "Most recent — title", "entry"),
        ("wh_years", "Most recent — years (e.g. 2019-2025)", "entry"),
        ("wh_highlights", "Most recent — highlights (one per line)", "text"),
    ]),
    ("Screening answers", [
        ("years_experience", "Years of experience", "entry"),
        ("work_authorization", "Work authorization", "entry"),
        ("visa_sponsorship", "Visa sponsorship", "entry"),
        ("availability", "Availability", "entry"),
        ("notice_period", "Notice period", "entry"),
        ("employment_type", "Employment type", "entry"),
        ("about_you", "About you", "text"),
        ("why_interested", "Why interested", "text"),
        ("proudest_project", "Proudest project", "text"),
        ("why_leaving", "Why leaving", "entry"),
    ]),
    ("Providers", [
        ("email_provider", "Email provider (gmail | msgraph | imap)", "entry"),
        ("calendar_provider", "Calendar provider (ics | google | msgraph)", "entry"),
    ]),
]

# Defaults for a fresh wizard so required-ish fields aren't blank.
WIZARD_DEFAULTS = {
    "country": "United States",
    "remote_only": True,
    "email_provider": "gmail",
    "calendar_provider": "ics",
    "work_authorization": "US Citizen",
    "visa_sponsorship": "Not required",
    "availability": "Two weeks notice",
    "notice_period": "Two weeks",
    "employment_type": "Full-time Permanent",
}


def _profile_to_inputs(profile: dict) -> dict:
    """Flatten a loaded profile dict back into wizard input keys (for prefill)."""
    profile = profile or {}
    identity = profile.get("identity", {}) or {}
    search = profile.get("search", {}) or {}
    narrative = profile.get("narrative", {}) or {}
    answers = profile.get("answers", {}) or {}

    def joinlist(v):
        return "\n".join(str(x) for x in v) if isinstance(v, (list, tuple)) else (v or "")

    inputs: dict = {}
    inputs.update({k: identity.get(k, "") for k in (
        "name", "first_name", "last_name", "email", "phone", "location",
        "city", "state", "zip", "country", "linkedin", "github")})

    inputs["target_roles"] = joinlist(search.get("target_roles", []))
    inputs["keywords"] = joinlist(search.get("keywords", []))
    inputs["min_salary"] = search.get("min_salary", 0)
    inputs["remote_only"] = bool(search.get("remote_only", True))
    inputs["locations"] = joinlist(search.get("locations", []))
    inputs["target_companies"] = joinlist(search.get("target_companies", []))

    inputs["elevator_pitch"] = narrative.get("elevator_pitch", "")
    inputs["key_strengths"] = joinlist(narrative.get("key_strengths", []))
    inputs["tech_summary"] = narrative.get("tech_summary", "")

    wh = narrative.get("work_history", []) or []
    if wh:
        first = wh[0] or {}
        inputs["wh_company"] = first.get("company", "")
        inputs["wh_title"] = first.get("title", "")
        inputs["wh_years"] = first.get("years", "")
        inputs["wh_highlights"] = joinlist(first.get("highlights", []))

    for k in ("years_experience", "work_authorization", "visa_sponsorship",
              "availability", "notice_period", "employment_type", "about_you",
              "why_interested", "proudest_project", "why_leaving"):
        inputs[k] = answers.get(k, "")

    inputs["email_provider"] = (profile.get("email", {}) or {}).get("provider", "gmail")
    inputs["calendar_provider"] = (profile.get("calendar", {}) or {}).get("provider", "ics")
    return inputs


class LauncherApp:
    """The Tk application. Tk is imported by the caller and handed in so this
    module never touches tkinter at import time."""

    def __init__(self, tk, ttk, messagebox, scrolledtext, profile_path=DEFAULT_PROFILE):
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.scrolledtext = scrolledtext
        self.profile_path = str(profile_path)

        self.root = tk.Tk()
        self.root.title("forget-the-thunderdome — launcher")
        self.root.geometry("820x640")
        self.root.minsize(640, 480)

        self._wizard_widgets: dict = {}

        if profile_exists(self.profile_path):
            self.show_main()
        else:
            self.show_wizard()

    # -- screen management ---------------------------------------------------
    def _clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    # -- wizard --------------------------------------------------------------
    def show_wizard(self, prefill: dict | None = None):
        tk, ttk = self.tk, self.ttk
        self._clear()
        self._wizard_widgets = {}

        if prefill is None:
            if profile_exists(self.profile_path):
                prefill = _profile_to_inputs(load_profile(self.profile_path))
            else:
                prefill = dict(WIZARD_DEFAULTS)

        header = ttk.Label(
            self.root,
            text="First-run profile setup — this writes profile.yaml",
            font=("TkDefaultFont", 12, "bold"),
        )
        header.pack(anchor="w", padx=12, pady=(10, 4))

        sub = ttk.Label(
            self.root,
            text="Fields with multiple items: put one per line. You can edit "
                 "profile.yaml by hand later.",
        )
        sub.pack(anchor="w", padx=12, pady=(0, 6))

        # Scrollable form area.
        canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        form = ttk.Frame(canvas)
        form.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0))
        scrollbar.pack(side="right", fill="y")

        row = 0
        for section_title, fields in WIZARD_SECTIONS:
            sec = ttk.Label(form, text=section_title,
                            font=("TkDefaultFont", 11, "bold"))
            sec.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 4))
            row += 1
            for key, label, kind in fields:
                value = prefill.get(key, WIZARD_DEFAULTS.get(key, ""))
                ttk.Label(form, text=label).grid(
                    row=row, column=0, sticky="nw", padx=(4, 8), pady=2)
                if kind == "check":
                    var = tk.BooleanVar(value=bool(value))
                    ttk.Checkbutton(form, variable=var).grid(
                        row=row, column=1, sticky="w", pady=2)
                    self._wizard_widgets[key] = ("check", var)
                elif kind == "text":
                    txt = tk.Text(form, width=52, height=3, wrap="word")
                    if value:
                        txt.insert("1.0", str(value))
                    txt.grid(row=row, column=1, sticky="we", pady=2)
                    self._wizard_widgets[key] = ("text", txt)
                else:
                    var = tk.StringVar(value="" if value is None else str(value))
                    ttk.Entry(form, textvariable=var, width=54).grid(
                        row=row, column=1, sticky="we", pady=2)
                    self._wizard_widgets[key] = ("entry", var)
                row += 1

        form.columnconfigure(1, weight=1)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=12, pady=8)
        ttk.Button(btns, text="Save profile", command=self._on_save_profile).pack(
            side="right")
        if profile_exists(self.profile_path):
            ttk.Button(btns, text="Cancel", command=self.show_main).pack(
                side="right", padx=(0, 8))

    def _collect_wizard_inputs(self) -> dict:
        inputs: dict = {}
        for key, (kind, widget) in self._wizard_widgets.items():
            if kind == "check":
                inputs[key] = bool(widget.get())
            elif kind == "text":
                inputs[key] = widget.get("1.0", "end").strip()
            else:
                inputs[key] = widget.get().strip()
        return inputs

    def _on_save_profile(self):
        try:
            inputs = self._collect_wizard_inputs()
            data = build_profile_dict(inputs)
            if not data["identity"]["name"] and not data["identity"]["email"]:
                self.messagebox.showwarning(
                    "Missing info",
                    "Please provide at least a name or an email before saving.",
                )
                return
            path = write_profile(data, self.profile_path)
            self.messagebox.showinfo("Saved", f"Profile written to:\n{path}")
            self.show_main()
        except Exception as exc:  # never crash the window
            self.messagebox.showerror("Could not save profile", str(exc))

    # -- main screen ---------------------------------------------------------
    def show_main(self):
        ttk = self.ttk
        tk = self.tk
        self._clear()

        ttk.Label(
            self.root,
            text="forget-the-thunderdome",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 0))
        ttk.Label(
            self.root,
            text=f"Profile: {self.profile_path}",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=12)
        buttons = [
            ("Dashboard", self.on_dashboard),
            ("Find jobs", self.on_jobs),
            ("Follow-ups", self.on_followups),
            ("Sync email", self.on_sync_email),
            ("Edit profile", self.on_edit_profile),
        ]
        for label, cmd in buttons:
            ttk.Button(bar, text=label, command=cmd).pack(side="left", padx=4, pady=4)

        self.output = self.scrolledtext.ScrolledText(self.root, wrap="word", height=24)
        self.output.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        self._set_output(
            "Ready. Choose an action above.\n\n"
            f"Repo: {REPO_ROOT}\n"
            f"CLI:  {JOB_CLI}\n"
        )

    def _set_output(self, text: str):
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)

    def _append_output(self, text: str):
        self.output.insert("end", text)
        self.output.see("end")

    def _run_and_show(self, args: list[str], heading: str) -> tuple[int, str]:
        self._set_output(f"$ python3 src/job_cli.py {' '.join(args)}\n\n")
        self.root.update_idletasks()
        try:
            code, out = run_command(args)
        except Exception as exc:  # defensive; run_command already guards
            code, out = 1, f"Error: {exc}"
        status = "OK" if code == 0 else f"exited with code {code}"
        self._append_output(out or "(no output)\n")
        self._append_output(f"\n--- {heading}: {status} ---\n")
        return code, out

    # -- button handlers -----------------------------------------------------
    def on_dashboard(self):
        try:
            if dashboard_supports_html():
                self._run_and_show(["dashboard", "--html"], "Dashboard")
                # Look for a produced HTML file and open it in a browser.
                html = REPO_ROOT / "dashboard" / "index.html"
                if html.is_file():
                    import webbrowser
                    webbrowser.open(html.as_uri())
                    self._append_output(f"\nOpened {html} in your browser.\n")
            else:
                self._run_and_show(["dashboard"], "Dashboard")
        except Exception as exc:
            self._append_output(f"\nError: {exc}\n")

    def on_jobs(self):
        self._run_and_show(["jobs"], "Find jobs")

    def on_followups(self):
        self._run_and_show(["follow-ups"], "Follow-ups")

    def on_sync_email(self):
        # Email sync is driven by the gmail tracker script, not job_cli. Run it
        # directly and surface output; never crash the window on failure.
        self._set_output("Syncing email (gmail tracker)...\n\n")
        self.root.update_idletasks()
        tracker = REPO_ROOT / "mcp-servers" / "gmail-server" / "gmail_tracker.py"
        if not tracker.is_file():
            self._append_output(
                f"Email sync script not found at:\n{tracker}\n\n"
                "See the README for email setup.\n")
            return
        try:
            proc = subprocess.run(
                [sys.executable or "python3", str(tracker), "--sync", "--days", "30"],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
            )
            self._append_output((proc.stdout or "") + (proc.stderr or ""))
            status = "OK" if proc.returncode == 0 else f"exited with code {proc.returncode}"
            self._append_output(f"\n--- Sync email: {status} ---\n")
        except Exception as exc:
            self._append_output(f"\nError running email sync: {exc}\n")

    def on_edit_profile(self):
        self.show_wizard(prefill=_profile_to_inputs(load_profile(self.profile_path)))

    def run(self):
        self.root.mainloop()


def launch_gui(profile_path=DEFAULT_PROFILE):
    """Import Tk lazily and start the application. Requires a display."""
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext

    app = LauncherApp(tk, ttk, messagebox, scrolledtext, profile_path=profile_path)
    app.run()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--check" in argv:
        report = self_check()
        print(_format_report(report))
        return 0 if report.get("ok") else 1

    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0

    try:
        launch_gui()
        return 0
    except Exception as exc:
        # Most common failure: no $DISPLAY. Give a useful, non-crashing message.
        print(f"Could not open the GUI: {exc}", file=sys.stderr)
        print(
            "A graphical display is required. On a headless machine, run "
            "`python3 launcher/ftt_launcher.py --check` instead.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
