"""stegoforge_ops.completion — shell completion scripts generated from the live command tree.

Typer >= 0.27 ships its own copy of click, so the command tree is walked by duck typing
(an option has ``opts``/``is_flag``, a group has ``commands``) instead of ``isinstance``
checks against ``click`` classes, which would silently match nothing.

The scripts used to hard-code a command list, which drifted (``doctor`` was missing)
and, for zsh, put ``#compdef`` below a comment so zsh never registered the file.
Everything here is derived from the Click command that Typer builds, so a new command
or option is completed the day it is added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PATH_FLAGS = {"-f", "--file", "-c", "--carrier", "-s", "--stego", "-p", "--payload", "-o", "--output", "--key-file",
              "--decoy", "--cover", "--save-heatmap", "--payload-file"}
DIR_FLAGS = {"-d", "--dir", "--output-dir"}
CHANNELS = ["ip_id", "tcp_seq", "ttl", "timing"]


@dataclass
class Opt:
    flags: list[str]
    help: str = ""
    kind: str = "value"          # flag | value | file | dir | choice
    choices: list[str] = field(default_factory=list)


@dataclass
class Cmd:
    name: str
    help: str
    opts: list[Opt]
    subcommands: list[Cmd] = field(default_factory=list)


def _choices() -> dict[str, list[str]]:
    from detect.survival import PROFILES
    from stegoforge_ops.registry import METHOD_ALIASES

    return {"--method": sorted(set(METHOD_ALIASES.values())), "--target": sorted(PROFILES), "--channel": CHANNELS}


def _opt(param: Any, choices: dict[str, list[str]]) -> Opt:
    flags = [*param.opts, *param.secondary_opts]
    help_text = " ".join((param.help or "").split())
    if param.is_flag:
        return Opt(flags, help_text, "flag")
    for flag in flags:
        if flag in choices:
            return Opt(flags, help_text, "choice", choices[flag])
    if any(f in PATH_FLAGS for f in flags):
        return Opt(flags, help_text, "file")
    if any(f in DIR_FLAGS for f in flags):
        return Opt(flags, help_text, "dir")
    return Opt(flags, help_text, "value")


def _is_option(param: Any) -> bool:
    return hasattr(param, "opts") and hasattr(param, "is_flag")


def _build(name: str, command: Any, choices: dict[str, list[str]]) -> Cmd:
    opts = [_opt(p, choices) for p in command.params if _is_option(p)]
    opts.append(Opt(["--help"], "Show help", "flag"))
    subs = []
    if isinstance(getattr(command, "commands", None), dict):
        subs = [_build(n, c, choices) for n, c in sorted(command.commands.items())]
    return Cmd(name, " ".join((command.help or "").split()).split(". ")[0], opts, subs)


def model(root: Any) -> list[Cmd]:
    choices = _choices()
    return [_build(n, c, choices) for n, c in sorted(root.commands.items())]


def _all_flags(cmd: Cmd) -> list[str]:
    return sorted({f for o in cmd.opts for f in o.flags})


# ── bash ──────────────────────────────────────────────────────────────────────

def bash(root: Any) -> str:
    cmds = model(root)
    lines = [
        "# StegoForge bash completion (generated: stegoforge completion bash)",
        "_stegoforge() {",
        '    local cur prev cmd',
        '    cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"',
        "    COMPREPLY=()",
        "    if [[ $COMP_CWORD -eq 1 ]]; then",
        f'        COMPREPLY=( $(compgen -W "{" ".join(c.name for c in cmds)} --offline --help" -- "$cur") ); return',
        "    fi",
        '    cmd="${COMP_WORDS[1]}"',
    ]
    # option values, wherever they appear
    value_cases: dict[str, str] = {}
    for c in cmds:
        for o in c.opts:
            if o.kind == "choice":
                value_cases.setdefault("|".join(sorted(o.flags)), f'compgen -W "{" ".join(o.choices)}" -- "$cur"')
            elif o.kind == "file":
                value_cases.setdefault("|".join(sorted(o.flags)), 'compgen -f -- "$cur"')
            elif o.kind == "dir":
                value_cases.setdefault("|".join(sorted(o.flags)), 'compgen -d -- "$cur"')
    lines.append('    case "$prev" in')
    for flags, action in sorted(value_cases.items()):
        lines.append(f"        {flags}) COMPREPLY=( $({action}) ); return ;;")
    lines.append("    esac")
    lines.append('    case "$cmd" in')
    for c in cmds:
        words = " ".join(_all_flags(c) + [s.name for s in c.subcommands])
        lines.append(f'        {c.name}) COMPREPLY=( $(compgen -W "{words}" -- "$cur") ) ;;')
    lines += ['        *) COMPREPLY=( $(compgen -W "--help" -- "$cur") ) ;;', "    esac", "}", "complete -F _stegoforge stegoforge", ""]
    return "\n".join(lines)


# ── zsh ───────────────────────────────────────────────────────────────────────

def _zsh_quote(text: str) -> str:
    return text.replace("'", "'\\''").replace("[", "\\[").replace("]", "\\]").replace(":", "\\:")


def _zsh_spec(o: Opt) -> list[str]:
    action = {"flag": "", "value": ":value: ", "file": ":file:_files", "dir": ":directory:_files -/",
              "choice": f":{o.flags[-1].lstrip('-')}:({' '.join(o.choices)})"}[o.kind]
    desc = f"[{_zsh_quote(o.help)}]" if o.help else ""
    return [f"'{flag}{desc}{action}'" for flag in o.flags]


def zsh(root: Any) -> str:
    cmds = model(root)
    # `#compdef` has to be the first line, or zsh does not register the file.
    out = ["#compdef stegoforge", "# StegoForge zsh completion (generated: stegoforge completion zsh)", "",
           "_stegoforge() {", "    local curcontext=\"$curcontext\" state line", "    typeset -A opt_args",
           "    local -a commands", "    commands=("]
    out += [f"        '{c.name}:{_zsh_quote(c.help)}'" for c in cmds]
    out += ["    )", "    _arguments -C \\", "        '--offline[Disable all network access]' \\", "        '1: :->cmd' \\", "        '*:: :->args'",
            "    case $state in", "        cmd) _describe -t commands 'stegoforge command' commands ;;", "        args)", "            case $line[1] in"]
    for c in cmds:
        out.append(f"                {c.name})")
        if c.subcommands:
            out.append("                    local -a subs; subs=(" + " ".join(f"'{s.name}:{_zsh_quote(s.help)}'" for s in c.subcommands) + ")")
            out.append("                    _describe -t commands 'subcommand' subs ;;")
            continue
        specs = [spec for o in c.opts for spec in _zsh_spec(o)]
        out.append("                    _arguments " + " ".join(specs) + " ;;")
    out += ["            esac", "            ;;", "    esac", "}", "", '_stegoforge "$@"', ""]
    return "\n".join(out)


# ── fish ──────────────────────────────────────────────────────────────────────

def _fish_quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def fish(root: Any) -> str:
    cmds = model(root)
    out = ["# StegoForge fish completion (generated: stegoforge completion fish)", "complete -c stegoforge -f",
           "complete -c stegoforge -l offline -d 'Disable all network access'"]
    for c in cmds:
        out.append(f"complete -c stegoforge -n '__fish_use_subcommand' -a {c.name} -d {_fish_quote(c.help)}")
    for c in cmds:
        cond = f"-n '__fish_seen_subcommand_from {c.name}'"
        for sub in c.subcommands:
            out.append(f"complete -c stegoforge {cond} -a {sub.name} -d {_fish_quote(sub.help)}")
        for o in c.opts:
            shorts = [f[1:] for f in o.flags if f.startswith("-") and not f.startswith("--")]
            longs = [f[2:] for f in o.flags if f.startswith("--")]
            parts = [f"complete -c stegoforge {cond}"]
            parts += [f"-s {s}" for s in shorts] + [f"-l {lng}" for lng in longs]
            if o.kind == "file":
                parts.append("-r -F")
            elif o.kind == "dir":
                parts.append("-r -a '(__fish_complete_directories)'")
            elif o.kind == "choice":
                parts.append(f"-r -a {_fish_quote(' '.join(o.choices))}")
            elif o.kind == "value":
                parts.append("-r")
            if o.help:
                parts.append(f"-d {_fish_quote(o.help)}")
            out.append(" ".join(parts))
    out.append("")
    return "\n".join(out)


GENERATORS = {"bash": bash, "zsh": zsh, "fish": fish}
