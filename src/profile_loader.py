#!/usr/bin/env python3
"""
Profile loader for forget-the-thunderdome (ftt).

All personal data (identity, search criteria, narrative, screening answers)
lives in profile.yaml at the repo root — never in code. See
profile.yaml.example for the template.

Usage:
    from profile_loader import load_profile
    profile = load_profile()
    name = profile["identity"]["name"]
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class ProfileNotFoundError(FileNotFoundError):
    """Raised when no profile.yaml can be located."""


def _profile_path(path=None) -> Path:
    """Resolve the profile path: explicit arg > FTT_PROFILE env > repo root."""
    if path:
        return Path(path)
    env = os.environ.get("FTT_PROFILE")
    if env:
        return Path(env)
    return REPO_ROOT / "profile.yaml"


def load_profile(path=None) -> dict:
    """
    Load the user profile as a dict.

    Looks for profile.yaml at the repo root, or wherever the FTT_PROFILE
    environment variable points. Raises a friendly error if missing.
    """
    profile_file = _profile_path(path)
    if not profile_file.exists():
        raise ProfileNotFoundError(
            f"No profile found at {profile_file}.\n"
            f"Copy {REPO_ROOT / 'profile.yaml.example'} to "
            f"{REPO_ROOT / 'profile.yaml'} and fill in your details, "
            "or set FTT_PROFILE to your profile's path."
        )
    try:
        import yaml
    except ImportError as e:
        raise ImportError(
            "PyYAML is required to read profile.yaml. "
            "Install it with: pip install pyyaml"
        ) from e
    with open(profile_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Profile at {profile_file} did not parse to a mapping.")
    return data


def default_db_path() -> str:
    """
    Default SQLite database location: <repo_root>/data/job_tracker.db.
    Creates the data/ directory if needed.
    """
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "job_tracker.db")
