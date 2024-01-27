import pytest

AWS_VARS = [
    "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN",
    "AWS_CREDENTIAL_EXPIRATION", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_WHOAMI_PROD_ACCOUNTS", "AWS_WHOAMI_PROMPT_PROD", "AWS_ENDPOINT_URL",
]


@pytest.fixture(autouse=True)
def isolated_aws(monkeypatch, tmp_path):
    """Point every AWS lookup at throwaway files and dummy credentials.

    Nothing in the test suite can read the real ~/.aws directory or reach a
    real account: config paths live in tmp_path, the keys are fake, and the
    instance metadata service is disabled.
    """
    for var in AWS_VARS:
        monkeypatch.delenv(var, raising=False)
    aws_dir = tmp_path / "aws"
    aws_dir.mkdir()
    (aws_dir / "config").write_text("")
    (aws_dir / "credentials").write_text("")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(aws_dir / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(aws_dir / "credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    return aws_dir
