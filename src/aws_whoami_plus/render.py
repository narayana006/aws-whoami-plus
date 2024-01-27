"""Turn a report dict into text."""

from __future__ import annotations

from datetime import datetime

METHOD_LABELS = {
    "env": "environment variables",
    "shared-credentials-file": "shared credentials file",
    "config-file": "config file",
    "sso": "IAM Identity Center (SSO)",
    "assume-role": "assume-role via config file",
    "assume-role-with-web-identity": "assume-role with web identity",
    "custom-process": "credential_process",
    "iam-role": "instance metadata (IAM role)",
    "container-role": "container credentials",
    "file": "identity file (no AWS call made)",
}


def humanize_seconds(seconds: float) -> str:
    seconds = int(abs(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def describe_expiry(expires_at: datetime, now: datetime) -> str:
    stamp = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    delta = (expires_at - now).total_seconds()
    if delta <= 0:
        return f"EXPIRED {humanize_seconds(delta)} ago ({stamp})"
    return f"{stamp} (in {humanize_seconds(delta)})"


def describe_identity(identity: dict) -> str:
    kind, name = identity["type"], identity["name"]
    if kind == "assumed-role":
        text = f"role {name}, session {identity.get('session_name') or '?'}"
        if identity.get("sso_permission_set"):
            text += f" (SSO permission set {identity['sso_permission_set']})"
        return text
    if kind == "root":
        return "account root user"
    if kind == "user":
        return f"IAM user {name}"
    if kind == "federated-user":
        return f"federated user {name}"
    return f"{kind} {name}"


def describe_chain(chain: list[dict]) -> str:
    steps = []
    for hop in chain:
        if "role_arn" in hop:
            step = f"{hop['role_arn']} [profile {hop['profile']}]"
            if hop.get("credential_source"):
                step = f"{hop['credential_source']} -> {step}"
            steps.append(step)
        elif hop.get("missing"):
            steps.append(f"profile {hop['profile']} (not found in config)")
        else:
            steps.append(f"profile {hop['profile']}")
    return " -> ".join(steps)


def render_text(report: dict) -> str:
    account = report["account"]
    if report["aliases"]:
        account += f" ({', '.join(report['aliases'])})"
    elif report.get("alias_error"):
        account += f" (alias unavailable: {report['alias_error']})"
    region = report["region"]
    rows = [
        ("Account", account),
        ("Identity", describe_identity(report["identity"])),
        ("ARN", report["arn"]),
        ("User ID", report["user_id"]),
        ("Profile", f"{report['profile']['value']}  <- {report['profile']['source']}"),
        ("Region", f"{region['value'] or '(none)'}  <- {region['source']}"),
        ("Credentials", METHOD_LABELS.get(report["credentials"], report["credentials"])),
    ]
    if report["role_chain"]:
        rows.append(("Role chain", describe_chain(report["role_chain"])))
    if report["credentials"] != "file":
        rows.append(("Expires", report.get("expires_text") or "no expiry known (long-lived keys, or not reported)"))
    width = max(len(label) for label, _ in rows)
    lines = [f"{label:<{width}}  {value}" for label, value in rows]
    if report.get("production"):
        lines.append("")
        lines.append(
            f"WARNING: this is a PRODUCTION account (matched '{report['production']}' in your production list)"
        )
    return "\n".join(lines) + "\n"
