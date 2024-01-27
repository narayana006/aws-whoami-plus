"""Ask AWS who the caller is and describe the answer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping, Optional

from botocore.exceptions import BotoCoreError, ClientError

SSO_ROLE_PREFIX = "AWSReservedSSO_"


def parse_arn(arn: str) -> dict:
    """Break a caller ARN into the parts people care about.

    Handles IAM users, assumed roles (including IAM Identity Center roles),
    federated users and the account root user.
    """
    parts = arn.split(":", 5)
    if len(parts) != 6 or parts[0] != "arn":
        return {"type": "unknown", "name": arn}
    resource = parts[5]
    if resource == "root":
        return {"type": "root", "name": "root"}
    kind, _, rest = resource.partition("/")
    if kind == "assumed-role":
        role, _, session = rest.partition("/")
        info = {"type": "assumed-role", "name": role, "session_name": session}
        if role.startswith(SSO_ROLE_PREFIX):
            # AWSReservedSSO_<PermissionSetName>_<16 hex chars>
            body = role[len(SSO_ROLE_PREFIX):]
            permission_set, _, _suffix = body.rpartition("_")
            info["sso_permission_set"] = permission_set or body
        return info
    if kind in ("user", "federated-user"):
        return {"type": kind, "name": rest.rsplit("/", 1)[-1]}
    return {"type": kind or "unknown", "name": rest or resource}


def parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def credential_expiry(credentials, env: Mapping[str, str]) -> Optional[datetime]:
    """When the current credentials stop working, if that can be known locally.

    Temporary credentials loaded by botocore (assume-role, SSO, instance role)
    carry an expiry time. Credentials pasted into the environment do not, but
    tools that export them (`aws configure export-credentials --format env`,
    aws-vault) also set AWS_CREDENTIAL_EXPIRATION, so that is honoured too.
    Long-lived access keys have no expiry and return None.
    """
    expiry = getattr(credentials, "_expiry_time", None)
    if isinstance(expiry, datetime):
        return expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
    if getattr(credentials, "method", None) == "env" and env.get("AWS_CREDENTIAL_EXPIRATION"):
        return parse_time(env["AWS_CREDENTIAL_EXPIRATION"])
    return None


def fetch_identity(session) -> dict:
    """Call sts:GetCallerIdentity and iam:ListAccountAliases.

    The alias lookup is optional: if it is denied, the alias list is empty and
    "alias_error" says why. Errors from STS propagate to the caller.
    """
    caller = session.client("sts").get_caller_identity()
    result = {
        "account": caller["Account"],
        "arn": caller["Arn"],
        "user_id": caller["UserId"],
        "aliases": [],
    }
    try:
        result["aliases"] = session.client("iam").list_account_aliases().get("AccountAliases", [])
    except ClientError as exc:
        result["alias_error"] = exc.response.get("Error", {}).get("Code", "ClientError")
    except BotoCoreError as exc:
        result["alias_error"] = type(exc).__name__
    return result


def load_identity_file(path: str) -> dict:
    """Read an identity saved as JSON instead of calling AWS.

    Accepts the output of `aws sts get-caller-identity` (keys UserId, Account,
    Arn), optionally with an "AccountAliases" list added (the shape returned by
    `aws iam list-account-aliases`).
    """
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object with Account, Arn and UserId")
    missing = [key for key in ("Account", "Arn", "UserId") if key not in data]
    if missing:
        raise ValueError(f"{path}: expected JSON with Account, Arn and UserId (missing: {', '.join(missing)})")
    return {
        "account": str(data["Account"]),
        "arn": data["Arn"],
        "user_id": data["UserId"],
        "aliases": list(data.get("AccountAliases", [])),
    }
