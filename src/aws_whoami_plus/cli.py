"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence

import boto3
import botocore.session
from botocore.exceptions import BotoCoreError, ClientError

from . import __version__, prod
from .identity import credential_expiry, fetch_identity, load_identity_file, parse_arn
from .prompt import SNIPPETS
from .render import describe_expiry, render_text
from .settings import resolve_profile, resolve_region, role_chain

EXIT_ERROR = 1
EXIT_PRODUCTION = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aws-whoami-plus",
        description="Show which AWS identity, account, region and role chain this shell is using.",
    )
    parser.add_argument("--profile", help="profile to inspect (default: AWS_PROFILE, then 'default')")
    parser.add_argument("--region", help="region to report (default: environment, then config file)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--prod",
        action="append",
        default=[],
        metavar="ID_OR_ALIAS",
        help="treat this account ID or alias glob as production (repeatable)",
    )
    parser.add_argument(
        "--fail-on-prod",
        action="store_true",
        help=f"exit with status {EXIT_PRODUCTION} when the account is on the production list",
    )
    parser.add_argument(
        "--from-file",
        metavar="JSON",
        help="read a saved `aws sts get-caller-identity` JSON document instead of calling AWS",
    )
    parser.add_argument("--prompt", choices=sorted(SNIPPETS), help="print a shell prompt snippet and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def build_report(
    identity: dict,
    *,
    profile,
    region,
    chain: list[dict],
    method: str,
    expires_at: Optional[datetime],
    prod_entries: Sequence[str],
    now: datetime,
) -> dict:
    report = dict(identity)
    report["identity"] = parse_arn(identity["arn"])
    report["profile"] = {"value": profile.value, "source": profile.source}
    report["region"] = {"value": region.value, "source": region.source}
    report["credentials"] = method
    report["role_chain"] = chain
    report["expires_at"] = expires_at.astimezone(timezone.utc).isoformat() if expires_at else None
    report["expires_in_seconds"] = int((expires_at - now).total_seconds()) if expires_at else None
    report["expires_text"] = describe_expiry(expires_at.astimezone(timezone.utc), now) if expires_at else None
    report["production"] = prod.match(identity["account"], identity["aliases"], prod_entries)
    return report


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    session=None,
    env: Optional[Mapping[str, str]] = None,
    now: Optional[datetime] = None,
) -> int:
    """Run the tool. `session` (a boto3.Session), `env` and `now` exist so tests can replace them."""
    args = build_parser().parse_args(argv)
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)

    if args.prompt:
        sys.stdout.write(SNIPPETS[args.prompt])
        return 0

    profile = resolve_profile(args.profile, env)
    try:
        # Parsed ~/.aws/config (or AWS_CONFIG_FILE); reading it makes no AWS call.
        profiles = botocore.session.Session().full_config.get("profiles", {})
        if args.from_file:
            identity = load_identity_file(args.from_file)
            method, expires_at = "file", None
        else:
            if session is None:
                core = botocore.session.Session(profile=args.profile)
                session = boto3.Session(botocore_session=core, region_name=args.region)
            credentials = session.get_credentials()
            if credentials is None:
                print(
                    f"aws-whoami-plus: no AWS credentials found for profile '{profile.value}'.",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            identity = fetch_identity(session)
            method = credentials.method or "unknown"
            expires_at = credential_expiry(credentials, env)
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        print(f"aws-whoami-plus: {exc}", file=sys.stderr)
        return EXIT_ERROR

    report = build_report(
        identity,
        profile=profile,
        region=resolve_region(args.region, env, profile.value, profiles),
        # The config-file chain only applies when botocore actually used it;
        # environment credentials, for example, take precedence over AWS_PROFILE.
        chain=role_chain(profile.value, profiles) if method == "assume-role" else [],
        method=method,
        expires_at=expires_at,
        prod_entries=prod.load_entries(args.prod, env),
        now=now,
    )
    if args.json:
        report.pop("expires_text")
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(report))
    if report["production"] and args.fail_on_prod:
        return EXIT_PRODUCTION
    return 0


if __name__ == "__main__":
    sys.exit(main())
