# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.5.x | Yes |
| 1.1.x and older | No. Several security fixes landed in 1.5.0 (see the [changelog](CHANGELOG.md)); please upgrade. |

Python 3.10 still works, but Pillow's fixes for its image-decoder advisories need Python 3.11 or newer. Use Python 3.11+ when you analyse files you do not trust.

## Reporting a vulnerability

Please report it privately, not in a public issue:

**[Report a vulnerability](https://github.com/Nour833/StegoForge/security/advisories/new)** (GitHub private vulnerability reporting)

Include what you can of:

- the affected version (`stegoforge doctor` prints it) and how you installed it,
- the steps or a small file that reproduces the problem,
- what an attacker gains from it.

StegoForge is maintained by one person, so I cannot promise a service level. I aim to acknowledge a report within 7 days, to tell you whether I consider it valid, and to publish a fix and an advisory together. You will be credited unless you prefer not to be. Please keep the details private until a fix is released.

## What counts

In scope:

- Flaws in the cryptography or key handling: the AES-256-GCM envelope, the Argon2id key derivation, decoy containers, key-exchange files.
- The local web UI: Host/Origin/CORS checks, token handling, path traversal, injection, leaking server paths or exception text.
- Network behaviour of the dead-drop client and the update check (request forgery, unbounded downloads).
- A crafted carrier file that makes StegoForge crash badly, hang, or run out of memory, instead of failing with a clean error.
- The build and release chain: the workflows, the published PyPI files, the binaries and the `.deb`.

Out of scope:

- A hidden payload being *detectable* by statistics. That is a documented limit of every embedding method ([`docs/METHODS.md`](docs/METHODS.md), [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md)).
- Payloads destroyed by recompression or editing, and weak passphrases chosen by the user.
- Vulnerabilities in a dependency that are already fixed upstream. Report those to the dependency; the project audits its requirements with `pip-audit` in CI.
- Using the tool for unlawful purposes. See *Responsible use* in the [README](README.md#responsible-use).

## Good-faith research

Test only against files, accounts and systems you own or are authorised to test, and do not access or keep other people's data. Research done that way in good faith will not be treated as hostile.

## Verifying a release

Releases are built and published by GitHub Actions from a version tag. PyPI files are uploaded with trusted publishing and carry provenance attestations, and GitHub shows a SHA-256 digest for every release asset. The standalone binaries are not code-signed, so Windows and macOS may warn when you first run them.
