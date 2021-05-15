# aws-whoami-plus

Show exactly which AWS identity, account, region and role chain your shell is using, and when the session expires.

> **Project status: planning. There is no working code in this repository yet.**
> This README describes what the project will do. Nothing below can be installed or run today.
> Features are ticked off in the checklist as they are built.

## What it is

A command-line tool.

**The problem it solves:** Running a command against the wrong AWS account is a classic and expensive mistake, and `aws sts get-caller-identity` shows only part of the picture.

## Who it is for

Anyone who works across several AWS accounts or profiles.

## How it will work

1. You run one command in your shell.
2. It reads your credentials chain and asks AWS who you are.
3. It prints the account, role, region and expiry, with a warning if you are in production.

## Planned features

Unticked items are not built yet.

- [ ] Caller identity with the account alias, not just the account number
- [ ] Active profile, region and where each setting came from (environment, config file, SSO)
- [ ] Assumed-role chain and session expiry time
- [ ] Warning when the account is on your list of production accounts
- [ ] Shell prompt snippet for bash and zsh

## Planned usage

This is the intended interface, shown so you can judge the design. **It does not work yet**, and names may change before the first release.

```bash
aws-whoami-plus
```

## Contributing

Feedback on the design is the most useful contribution right now. Open an issue to suggest a feature, question an approach or describe your use case. Code contributions are welcome once the first version lands.

## Author

Built and maintained by [Narayana Vemburaj](https://github.com/narayana006).

## License

[MIT](LICENSE)
