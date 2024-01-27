import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from botocore.credentials import Credentials

from aws_whoami_plus import prod
from aws_whoami_plus.identity import credential_expiry, load_identity_file, parse_arn
from aws_whoami_plus.prompt import SNIPPETS
from aws_whoami_plus.render import describe_expiry, humanize_seconds
from aws_whoami_plus.settings import resolve_profile, resolve_region, role_chain

NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "arn, expected",
    [
        ("arn:aws:iam::123456789012:user/alice", {"type": "user", "name": "alice"}),
        ("arn:aws:iam::123456789012:user/teams/ops/alice", {"type": "user", "name": "alice"}),
        ("arn:aws:iam::123456789012:root", {"type": "root", "name": "root"}),
        (
            "arn:aws:sts::123456789012:assumed-role/Admin/alice",
            {"type": "assumed-role", "name": "Admin", "session_name": "alice"},
        ),
        (
            "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_Read_Only_0123456789abcdef/alice@example.com",
            {
                "type": "assumed-role",
                "name": "AWSReservedSSO_Read_Only_0123456789abcdef",
                "session_name": "alice@example.com",
                "sso_permission_set": "Read_Only",
            },
        ),
        ("arn:aws:sts::123456789012:federated-user/bob", {"type": "federated-user", "name": "bob"}),
        ("not-an-arn", {"type": "unknown", "name": "not-an-arn"}),
    ],
)
def test_parse_arn(arn, expected):
    assert parse_arn(arn) == expected


def test_profile_precedence():
    env = {"AWS_PROFILE": "from-env", "AWS_DEFAULT_PROFILE": "older"}
    assert resolve_profile("cli", env).source == "--profile option"
    assert resolve_profile(None, env).value == "from-env"
    assert resolve_profile(None, {"AWS_DEFAULT_PROFILE": "older"}).value == "older"
    fallback = resolve_profile(None, {})
    assert (fallback.value, fallback.source) == ("default", "default (no profile selected)")


def test_region_precedence():
    profiles = {"dev": {"region": "eu-west-1"}}
    assert resolve_region("ap-south-1", {"AWS_REGION": "us-west-2"}, "dev", profiles).value == "ap-south-1"
    both = resolve_region(None, {"AWS_REGION": "us-west-2", "AWS_DEFAULT_REGION": "us-east-1"}, "dev", profiles)
    assert (both.value, both.source) == ("us-west-2", "AWS_REGION environment variable")
    from_config = resolve_region(None, {}, "dev", profiles)
    assert (from_config.value, from_config.source) == ("eu-west-1", "config file, profile dev")
    assert resolve_region(None, {}, "other", profiles).value is None


def test_role_chain_follows_source_profiles():
    profiles = {
        "base": {"region": "us-east-1"},
        "hub": {"role_arn": "arn:aws:iam::111111111111:role/Hub", "source_profile": "base"},
        "prod": {"role_arn": "arn:aws:iam::222222222222:role/Admin", "source_profile": "hub"},
    }
    chain = role_chain("prod", profiles)
    assert [hop["profile"] for hop in chain] == ["base", "hub", "prod"]
    assert chain[2]["role_arn"].endswith("role/Admin")
    assert role_chain("base", profiles) == []


def test_role_chain_survives_loops_and_credential_source():
    looped = {
        "a": {"role_arn": "arn:aws:iam::111111111111:role/A", "source_profile": "b"},
        "b": {"role_arn": "arn:aws:iam::111111111111:role/B", "source_profile": "a"},
    }
    assert [hop["profile"] for hop in role_chain("a", looped)] == ["b", "a"]
    ec2 = {"app": {"role_arn": "arn:aws:iam::111111111111:role/App", "credential_source": "Ec2InstanceMetadata"}}
    assert role_chain("app", ec2) == [
        {"profile": "app", "role_arn": "arn:aws:iam::111111111111:role/App", "credential_source": "Ec2InstanceMetadata"}
    ]


def test_prod_matching_by_id_and_alias_glob():
    assert prod.match("123456789012", [], ["123456789012"]) == "123456789012"
    assert prod.match("123456789012", ["acme-prod"], ["*-prod"]) == "*-prod"
    assert prod.match("123456789012", ["acme-dev"], ["*-prod", "999999999999"]) is None


def test_prod_entries_merge_cli_env_and_file(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path), prod.ENV_VAR: "111111111111, *-live"}
    path = prod.config_path(env)
    path.parent.mkdir(parents=True)
    path.write_text("# payments\n222222222222  # main prod\n\nacme-prod\n")
    assert prod.load_entries(["333333333333"], env) == [
        "333333333333", "111111111111", "*-live", "222222222222", "acme-prod",
    ]


def test_expiry_text():
    assert humanize_seconds(59) == "59s"
    assert humanize_seconds(3600 * 5 + 120) == "5h 02m"
    assert describe_expiry(NOW + timedelta(minutes=42), NOW) == "2030-01-01 12:42:00 UTC (in 42m)"
    assert describe_expiry(NOW - timedelta(minutes=5), NOW).startswith("EXPIRED 5m ago")


def test_credential_expiry_sources():
    static = Credentials("a", "b", method="shared-credentials-file")
    assert credential_expiry(static, {}) is None
    exported = Credentials("a", "b", "token", method="env")
    found = credential_expiry(exported, {"AWS_CREDENTIAL_EXPIRATION": "2030-01-01T13:00:00Z"})
    assert found == datetime(2030, 1, 1, 13, 0, tzinfo=timezone.utc)
    assert credential_expiry(exported, {"AWS_CREDENTIAL_EXPIRATION": "garbage"}) is None


def test_identity_file_validation(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"Account": "123456789012"}')
    with pytest.raises(ValueError, match="missing: Arn, UserId"):
        load_identity_file(str(bad))


def run_shell(shell, snippet, body, env):
    script = f"PS1='$ '\nPROMPT='%% '\n{snippet}\n{body}\n"
    flags = ["--norc", "--noprofile", "-c"] if shell == "bash" else ["-f", "-c"]
    done = subprocess.run([shell, *flags, script], env=env, capture_output=True, text=True, check=True)
    return done.stdout


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_prompt_snippet_runs_in_real_shell(shell):
    if not shutil.which(shell):
        pytest.skip(f"{shell} not installed")
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    snippet = SNIPPETS[shell]
    out = run_shell(shell, snippet, "__aws_whoami_segment", {**base, "AWS_PROFILE": "dev", "AWS_REGION": "eu-west-1"})
    assert "[aws:dev@eu-west-1]" in out
    assert ("36m" in out) if shell == "bash" else ("%F{cyan}" in out)
    out = run_shell(shell, snippet, "__aws_whoami_segment", {**base, "AWS_PROFILE": "acme-prod-admin"})
    assert "[aws:acme-prod-admin]" in out
    assert ("31m" in out) if shell == "bash" else ("%F{red}" in out)
    assert run_shell(shell, snippet, "__aws_whoami_segment", base) == ""
    keys_only = run_shell(shell, snippet, "__aws_whoami_segment", {**base, "AWS_ACCESS_KEY_ID": "testing"})
    assert "[aws:env-keys]" in keys_only
    var = "PS1" if shell == "bash" else "PROMPT"
    twice = run_shell(shell, snippet + "\n" + snippet, f'printf "%s" "${var}"', base)
    assert twice.count("__aws_whoami_segment") == 1
