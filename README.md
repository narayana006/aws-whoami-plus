# aws-whoami-plus

Show exactly which AWS identity, account, region and role chain your shell is using, and when the session expires.

**Status: first working version (0.1.0).** All five planned features work today: identity with account alias, profile and region with their sources, role chain and expiry, production warning, and prompt snippets for bash and zsh. It has been tested against [moto](https://github.com/getmoto/moto) (a local fake of AWS) and botocore stubs, not yet against a wide range of real account setups, so please report anything it gets wrong.

## Why

`aws sts get-caller-identity` gives you an account number and an ARN. It does not tell you the account's name, which profile and region are in effect or why, how you got to that role, or how long the session has left. Running a command in the wrong account is an expensive way to find out.

## Install

```bash
pip install git+https://github.com/narayana006/aws-whoami-plus
```

Python 3.10 or newer. The only runtime dependency is `boto3`.

## Try it without an AWS account

`--from-file` reads a saved `aws sts get-caller-identity` JSON document instead of calling AWS. From a clone of this repository:

```bash
AWS_PROFILE=prod-readonly AWS_REGION=eu-west-1 \
  aws-whoami-plus --from-file examples/identity-sso.json --prod '*-prod'
```

Real output of that command (run with an empty AWS config; no AWS call is made):

```text
Account      123456789012 (acme-prod)
Identity     role AWSReservedSSO_ReadOnly_0123456789abcdef, session alice@example.com (SSO permission set ReadOnly)
ARN          arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_ReadOnly_0123456789abcdef/alice@example.com
User ID      AROAEXAMPLEEXAMPLEXYZ:alice@example.com
Profile      prod-readonly  <- AWS_PROFILE environment variable
Region       eu-west-1  <- AWS_REGION environment variable
Credentials  identity file (no AWS call made)

WARNING: this is a PRODUCTION account (matched '*-prod' in your production list)
```

## What a live run looks like

`examples/moto_demo.py` runs the real code path (credential chain, STS, IAM) against moto. It writes a throwaway config with a `base` profile and a `prod-admin` profile that assumes a role, then runs `aws-whoami-plus --profile prod-admin --prod '*-prod'`. Nothing touches a real account or your `~/.aws` files.

```bash
pip install "moto[sts,iam]"
python examples/moto_demo.py
```

Real output of that script (against moto, not real AWS):

```text
Account      123456789012 (acme-prod)
Identity     role Admin, session alice
ARN          arn:aws:sts::123456789012:assumed-role/Admin/alice
User ID      AROA3X42LBCD6NG8X8ICR:alice
Profile      prod-admin  <- --profile option
Region       eu-west-1  <- config file, profile prod-admin
Credentials  assume-role via config file
Role chain   profile base -> arn:aws:iam::123456789012:role/Admin [profile prod-admin]
Expires      2026-11-10 15:21:16 UTC (in 1h 00m)

WARNING: this is a PRODUCTION account (matched '*-prod' in your production list)
```

## Usage

```bash
aws-whoami-plus                      # whatever your shell would use right now
aws-whoami-plus --profile staging    # a specific profile
aws-whoami-plus --json               # machine-readable
aws-whoami-plus --fail-on-prod       # exit 3 if the account is on your production list
```

| Option | Meaning |
| --- | --- |
| `--profile NAME` | Inspect this profile instead of `AWS_PROFILE` / `default`. |
| `--region NAME` | Report this region instead of the one from the environment or config file. |
| `--json` | Print the report as JSON. |
| `--prod ID_OR_ALIAS` | Add an account ID or alias glob to the production list for this run. Repeatable. |
| `--fail-on-prod` | Exit with status 3 when the account is on the production list. |
| `--from-file JSON` | Read a saved identity instead of calling AWS (see below). |
| `--prompt bash\|zsh` | Print a prompt snippet and exit. |

Exit status: `0` success, `1` no credentials or the STS call failed, `3` production account with `--fail-on-prod`.

### What each line means

- **Account**: the 12-digit ID from STS, plus the account alias from IAM if one is set. If the alias lookup is denied the line says so and everything else still works.
- **Identity**: parsed from the caller ARN: IAM user, assumed role with its session name, federated user or root. Roles created by IAM Identity Center (`AWSReservedSSO_...`) also show the permission set name.
- **Profile** and **Region**: the value in effect and where it came from: a command-line option, a named environment variable (`AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION`), or the config file.
- **Credentials**: which provider botocore actually used (environment variables, shared credentials file, SSO, assume-role, instance metadata and so on). This matters because access keys in the environment take precedence over `AWS_PROFILE`.
- **Role chain**: for profiles that use `role_arn`, the `source_profile` hops from the base credentials to the role, read from your config file. Shown only when the assume-role provider was the one used.
- **Expires**: when temporary credentials stop working, and how long that is from now.

### Production accounts

List the accounts you consider production, by account ID or by a glob matched against the account alias. Entries are merged from:

1. `--prod` options,
2. the `AWS_WHOAMI_PROD_ACCOUNTS` environment variable (comma separated),
3. `~/.config/aws-whoami-plus/prod-accounts` (or `$XDG_CONFIG_HOME/aws-whoami-plus/prod-accounts`), one entry per line, `#` for comments. See [`examples/prod-accounts`](examples/prod-accounts).

A guard for scripts:

```bash
aws-whoami-plus --fail-on-prod >/dev/null || { echo "refusing to run in production"; exit 1; }
```

Note that this also stops the script when there are no credentials (exit 1), which is usually what you want.

### Saved identities

`--from-file` accepts the JSON printed by `aws sts get-caller-identity` (`UserId`, `Account`, `Arn`). You may add an `AccountAliases` list, the shape printed by `aws iam list-account-aliases`. Profile and region are still taken from your options, environment and config file. Expiry and role chain are not shown because they cannot be known from the file.

### Prompt snippet

```bash
eval "$(aws-whoami-plus --prompt bash)"   # in ~/.bashrc
eval "$(aws-whoami-plus --prompt zsh)"    # in ~/.zshrc
```

This prepends `[aws:<profile>@<region>]` to your prompt. It reads only environment variables (`AWS_PROFILE`, `AWS_REGION` and their `_DEFAULT_` forms), so it adds no delay and makes no AWS calls. The segment is cyan, and red when the profile name matches the glob in `AWS_WHOAMI_PROMPT_PROD` (default `*prod*`). With no profile set it shows nothing, or `[aws:env-keys]` if access keys are in the environment.

## IAM permissions

The tool is read-only and makes two calls:

- `sts:GetCallerIdentity`. AWS allows this for every identity; it needs no policy.
- `iam:ListAccountAliases`. Optional. Without it the alias is reported as unavailable.

## Features

- [x] Caller identity with the account alias, not just the account number
- [x] Active profile, region and where each setting came from (environment, config file, SSO)
- [x] Assumed-role chain and session expiry time
- [x] Warning when the account is on your list of production accounts
- [x] Shell prompt snippet for bash and zsh

## Limitations

- The role chain comes from `role_arn` / `source_profile` / `credential_source` in your config file. Roles assumed outside the config file (for example by hand with `aws sts assume-role`, or by another tool) show up as the final assumed role only; AWS does not report earlier hops.
- Expiry is known for temporary credentials that botocore loaded itself (assume-role, SSO, instance or container roles) and for environment credentials when `AWS_CREDENTIAL_EXPIRATION` is set. For other session tokens pasted into the environment, and for long-lived access keys, it prints "no expiry known". The expiry of botocore-loaded credentials is read from a botocore attribute that is not part of its documented interface, so a future botocore release could require a fix here.
- The prompt snippet shows the profile name, not the verified account. It is a reminder, not a check; run the command itself when it matters.
- The production warning is only as good as your list. An account that is not on the list gets no warning.
- No fish prompt snippet yet.

## Development

```bash
git clone https://github.com/narayana006/aws-whoami-plus
cd aws-whoami-plus
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The tests use moto and botocore's `Stubber` with dummy credentials and a temporary config directory. They never read `~/.aws` or contact AWS.

## Contributing

Issues and pull requests are welcome, especially reports of identity types or credential setups that are described wrongly. Please include the output of `aws-whoami-plus --json` with account IDs and names replaced.

## Author

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
