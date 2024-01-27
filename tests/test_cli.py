import json
from datetime import datetime, timezone

import boto3
import pytest
from botocore.credentials import Credentials
from botocore.stub import Stubber
from moto import mock_aws

from aws_whoami_plus.cli import EXIT_ERROR, EXIT_PRODUCTION, main

NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ROLE_ARN = "arn:aws:iam::123456789012:role/Admin"


def write_role_profiles(aws_dir):
    (aws_dir / "credentials").write_text(
        "[base]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
    )
    (aws_dir / "config").write_text(
        "[profile base]\nregion = us-east-1\n\n"
        f"[profile prod-admin]\nrole_arn = {ROLE_ARN}\nsource_profile = base\nregion = eu-west-1\n"
    )


@mock_aws
def test_env_credentials_with_account_alias(capsys):
    boto3.client("iam").create_account_alias(AccountAlias="acme-dev")
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "123456789012 (acme-dev)" in out
    assert "default  <- default (no profile selected)" in out
    assert "us-east-1  <- AWS_DEFAULT_REGION environment variable" in out
    assert "environment variables" in out
    assert "Role chain" not in out
    assert "WARNING" not in out


@mock_aws
def test_assume_role_profile_shows_chain_and_expiry(capsys, monkeypatch, isolated_aws):
    write_role_profiles(isolated_aws)
    monkeypatch.delenv("AWS_DEFAULT_REGION")
    assert main(["--profile", "prod-admin", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["account"] == "123456789012"
    assert report["identity"]["type"] == "assumed-role"
    assert report["identity"]["name"] == "Admin"
    assert report["credentials"] == "assume-role"
    assert report["profile"] == {"value": "prod-admin", "source": "--profile option"}
    assert report["region"] == {"value": "eu-west-1", "source": "config file, profile prod-admin"}
    assert report["role_chain"] == [{"profile": "base"}, {"profile": "prod-admin", "role_arn": ROLE_ARN}]
    assert report["expires_at"] is not None
    assert report["expires_in_seconds"] > 0
    assert "expires_text" not in report


@mock_aws
def test_env_keys_take_precedence_over_aws_profile(capsys, monkeypatch, isolated_aws):
    # AWS_PROFILE names a role profile, but static keys in the environment win,
    # so the report must not claim the role chain was used.
    write_role_profiles(isolated_aws)
    monkeypatch.setenv("AWS_PROFILE", "prod-admin")
    assert main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["credentials"] == "env"
    assert report["role_chain"] == []
    assert report["identity"]["type"] == "user"
    assert report["profile"]["source"] == "AWS_PROFILE environment variable"


@mock_aws
def test_production_warning_and_exit_code(capsys, monkeypatch):
    boto3.client("iam").create_account_alias(AccountAlias="acme-prod")
    assert main(["--prod", "*-prod"]) == 0
    assert "WARNING: this is a PRODUCTION account (matched '*-prod'" in capsys.readouterr().out
    monkeypatch.setenv("AWS_WHOAMI_PROD_ACCOUNTS", "123456789012")
    assert main(["--fail-on-prod"]) == EXIT_PRODUCTION
    monkeypatch.setenv("AWS_WHOAMI_PROD_ACCOUNTS", "999999999999")
    assert main(["--fail-on-prod"]) == 0


class StubbedSession:
    """A stand-in for boto3.Session whose clients answer from botocore Stubbers."""

    def __init__(self, credentials):
        self.credentials = credentials
        self.clients = {name: boto3.client(name, region_name="us-east-1") for name in ("sts", "iam")}
        self.stubs = {name: Stubber(client) for name, client in self.clients.items()}

    def client(self, name):
        return self.clients[name]

    def get_credentials(self):
        return self.credentials


def test_alias_access_denied_is_reported_not_fatal(capsys):
    session = StubbedSession(Credentials("a", "b", "token", method="env"))
    session.stubs["sts"].add_response(
        "get_caller_identity",
        {
            "Account": "123456789012",
            "Arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_ReadOnly_0123456789abcdef/alice",
            "UserId": "AROAEXAMPLEEXAMPLE:alice",
        },
    )
    session.stubs["iam"].add_client_error("list_account_aliases", service_error_code="AccessDenied")
    for stub in session.stubs.values():
        stub.activate()
    env = {"AWS_CREDENTIAL_EXPIRATION": "2030-01-01T12:30:00Z", "XDG_CONFIG_HOME": "/nonexistent"}
    assert main([], session=session, env=env, now=NOW) == 0
    out = capsys.readouterr().out
    assert "123456789012 (alias unavailable: AccessDenied)" in out
    assert "SSO permission set ReadOnly" in out
    assert "2030-01-01 12:30:00 UTC (in 30m)" in out


def test_sts_failure_exits_with_error(capsys):
    session = StubbedSession(Credentials("a", "b", "token", method="env"))
    session.stubs["sts"].add_client_error(
        "get_caller_identity", service_error_code="ExpiredToken", service_message="token expired"
    )
    session.stubs["sts"].activate()
    assert main([], session=session, env={}, now=NOW) == EXIT_ERROR
    assert "ExpiredToken" in capsys.readouterr().err


def test_no_credentials(capsys, monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    assert main([]) == EXIT_ERROR
    assert "no AWS credentials found for profile 'default'" in capsys.readouterr().err


def test_unknown_profile(capsys):
    assert main(["--profile", "nope"]) == EXIT_ERROR
    assert "nope" in capsys.readouterr().err


def test_from_file_makes_no_aws_call(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    saved = tmp_path / "id.json"
    saved.write_text(json.dumps({
        "UserId": "AIDAEXAMPLEEXAMPLE",
        "Account": "123456789012",
        "Arn": "arn:aws:iam::123456789012:user/alice",
        "AccountAliases": ["acme-prod"],
    }))
    code = main(["--from-file", str(saved), "--prod", "acme-prod", "--fail-on-prod", "--region", "ap-south-1"])
    assert code == EXIT_PRODUCTION
    out = capsys.readouterr().out
    assert "IAM user alice" in out
    assert "ap-south-1  <- --region option" in out
    assert "identity file (no AWS call made)" in out
    assert "PRODUCTION" in out


def test_from_file_errors(capsys, tmp_path):
    assert main(["--from-file", str(tmp_path / "missing.json")]) == EXIT_ERROR
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert main(["--from-file", str(broken)]) == EXIT_ERROR


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_prompt_option_prints_snippet(capsys, shell):
    assert main(["--prompt", shell]) == 0
    assert "__aws_whoami_segment" in capsys.readouterr().out
