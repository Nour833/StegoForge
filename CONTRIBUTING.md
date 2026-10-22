# Contributing to StegoForge

Thank you for helping. Bug reports, fixes, documentation and new methods are all welcome. By contributing you agree that your work is released under the [MIT license](LICENSE).

By taking part you also agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Before you start

Open an issue first for anything larger than a small fix, so we can agree on the approach before you spend time on it. A few ground rules shape what fits:

- **Offline and self-contained.** StegoForge works without network services or special hardware, and it never downloads or runs code at start-up. A change that adds network behaviour, a service dependency or a hardware dependency to a core command is unlikely to be accepted.
- **Few, justified dependencies.** The project is packaged for PyPI, as a Debian package and as standalone binaries, so every new dependency has to be reviewable and available there. The version floors in `requirements*.txt` are the oldest releases that are tested; raise one only when the code needs it.
- **Honest claims.** The README and docs say what each method survives and what it does not. Do not describe a feature as stronger than it was tested to be.

## Set up

```bash
git clone https://github.com/Nour833/StegoForge && cd StegoForge
python -m venv venv && source venv/bin/activate
pip install -e ".[web]" pytest
```

Python 3.10 is the minimum, so do not use syntax or standard-library features newer than 3.10.

## Check your change

CI runs exactly these, so run them before you open a pull request:

```bash
python -m pytest tests/ -q
uvx ruff check core detect protocol web stegoforge.py stegoforge_ops scripts
uvx --with-requirements requirements.txt --with-requirements requirements-web.txt mypy core detect protocol stegoforge_ops --ignore-missing-imports
```

If you touch packaging, also run `python -m build && python scripts/check_dist.py dist/*` and `python scripts/build_deb.py --out dist-deb`. If you change the web UI, `scripts/ui_smoke.py` drives it in a real browser (see the README).

A few things have bitten before:

- **Typer parameters use `Optional[X]`, not `X | None`.** The `.deb` runs against the distribution's older Typer, which cannot parse the `|` form in a command signature. `tests/test_cli_signatures.py` checks this.
- **Output must survive a legacy console.** On Windows, redirected output is not UTF-8. Do not bypass `core/stdio.py`.

## Adding or changing a method

A method subclasses `core.base.BaseEncoder` and honours its error contract: parser failures become `CorruptedCarrierError`, an oversized payload becomes a capacity error, and nothing leaks a traceback or a server path. In the same pull request:

1. Add tests that round-trip a **real carrier** (a small generated file is fine), including a wrong key and a payload that is too large.
2. Document the capacity and what the method does *not* survive in [`docs/METHODS.md`](docs/METHODS.md).
3. Register it in `stegoforge_ops/registry.py` and, if it is a new carrier type, add a detector or say why none applies.
4. Add a line to the *Unreleased* section of the [changelog](CHANGELOG.md).

## Pull requests

- One logical change per pull request, with a short description of what and why.
- Commit messages in the form `type: summary` (`fix:`, `feat:`, `docs:`, `chore:`, `test:`), as in the existing history.
- Never commit passphrases, tokens, private keys or real people's files. Test fixtures must be generated or your own.
- Keep the diff free of unrelated reformatting.

## Reporting a bug

Use the bug report form. It asks for the output of `stegoforge doctor`, which prints the version and what your installation can do, and for the command you ran. Remove passphrases and any private files from what you paste.
