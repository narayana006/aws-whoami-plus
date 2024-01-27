"""Work out which profile and region are active, and where each came from.

Nothing in this module talks to AWS. It only looks at command-line values,
environment variables and the already-parsed AWS config file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Setting:
    value: Optional[str]
    source: str


def resolve_profile(cli_profile: Optional[str], env: Mapping[str, str]) -> Setting:
    if cli_profile:
        return Setting(cli_profile, "--profile option")
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        if env.get(var):
            return Setting(env[var], f"{var} environment variable")
    return Setting("default", "default (no profile selected)")


def resolve_region(
    cli_region: Optional[str],
    env: Mapping[str, str],
    profile: str,
    profiles: Mapping[str, Mapping[str, object]],
) -> Setting:
    if cli_region:
        return Setting(cli_region, "--region option")
    for var in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if env.get(var):
            return Setting(env[var], f"{var} environment variable")
    configured = profiles.get(profile, {}).get("region")
    if configured:
        return Setting(str(configured), f"config file, profile {profile}")
    return Setting(None, "not set")


def role_chain(profile: str, profiles: Mapping[str, Mapping[str, object]]) -> list[dict]:
    """Follow role_arn/source_profile links in the config file.

    Returns the chain from the base credentials to the selected profile, e.g.
    [{"profile": "base"}, {"profile": "prod", "role_arn": "arn:..."}].
    A profile without role_arn yields an empty list (there is no chain).
    """
    hops: list[dict] = []
    seen: set[str] = set()
    current: Optional[str] = profile
    while current and current not in seen:
        seen.add(current)
        cfg = profiles.get(current)
        if cfg is None:
            hops.append({"profile": current, "missing": True})
            break
        if not cfg.get("role_arn"):
            hops.append({"profile": current})
            break
        hop = {"profile": current, "role_arn": str(cfg["role_arn"])}
        if cfg.get("credential_source"):
            hop["credential_source"] = str(cfg["credential_source"])
            hops.append(hop)
            break
        hops.append(hop)
        current = str(cfg["source_profile"]) if cfg.get("source_profile") else None
    hops.reverse()
    return hops if any("role_arn" in h for h in hops) else []
