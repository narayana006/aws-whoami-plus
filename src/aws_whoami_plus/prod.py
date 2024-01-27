"""The user's list of production accounts.

Entries are account IDs or account-alias patterns (shell-style globs such as
"*-prod"). They come from three places, all merged:

1. --prod options on the command line
2. the AWS_WHOAMI_PROD_ACCOUNTS environment variable (comma separated)
3. a text file, one entry per line, '#' starts a comment:
   $XDG_CONFIG_HOME/aws-whoami-plus/prod-accounts
   (~/.config/aws-whoami-plus/prod-accounts when XDG_CONFIG_HOME is unset)
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Mapping, Optional

ENV_VAR = "AWS_WHOAMI_PROD_ACCOUNTS"


def config_path(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")).expanduser() / ".config")
    return Path(base) / "aws-whoami-plus" / "prod-accounts"


def parse_entries(text: str) -> list[str]:
    entries = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def load_entries(cli_entries: Iterable[str], env: Mapping[str, str]) -> list[str]:
    entries = [e.strip() for e in cli_entries if e.strip()]
    entries += [e.strip() for e in env.get(ENV_VAR, "").split(",") if e.strip()]
    path = config_path(env)
    if path.is_file():
        entries += parse_entries(path.read_text(encoding="utf-8"))
    return entries


def match(account_id: str, aliases: Iterable[str], entries: Iterable[str]) -> Optional[str]:
    """Return the first entry that matches the account, or None."""
    aliases = list(aliases)
    for entry in entries:
        if entry == account_id:
            return entry
        if any(fnmatch.fnmatchcase(alias, entry) for alias in aliases):
            return entry
    return None
