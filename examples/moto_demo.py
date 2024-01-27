"""Run aws-whoami-plus end to end against moto, a local fake of AWS.

No real AWS account is contacted and your ~/.aws files are not read: the
script writes a throwaway config with a base profile and a role profile, fakes
STS and IAM with moto, then runs the CLI against the role profile.

    pip install "moto[sts,iam]"
    python examples/moto_demo.py
"""

import os
import sys
import tempfile
from pathlib import Path

import boto3
from moto import mock_aws

from aws_whoami_plus.cli import main

CONFIG = """\
[profile base]
region = us-east-1

[profile prod-admin]
role_arn = arn:aws:iam::123456789012:role/Admin
role_session_name = alice
source_profile = base
region = eu-west-1
"""

CREDENTIALS = """\
[base]
aws_access_key_id = testing
aws_secret_access_key = testing
"""


def run() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "config").write_text(CONFIG)
        (Path(tmp) / "credentials").write_text(CREDENTIALS)
        for var in list(os.environ):
            if var.startswith("AWS_"):
                del os.environ[var]
        os.environ.update(
            AWS_CONFIG_FILE=str(Path(tmp) / "config"),
            AWS_SHARED_CREDENTIALS_FILE=str(Path(tmp) / "credentials"),
            AWS_EC2_METADATA_DISABLED="true",
            XDG_CONFIG_HOME=tmp,
        )
        with mock_aws():
            boto3.Session(profile_name="base").client("iam").create_account_alias(AccountAlias="acme-prod")
            return main(["--profile", "prod-admin", "--prod", "*-prod", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(run())
