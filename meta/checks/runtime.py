"""The runtime-declaration checker (C57, design §7 / F16).

The declaration in ``bin/runtime.py`` says what akmon needs on a host. This joins it to what
akmon actually invokes — and the shape of that join is the whole design:

* the **generated-wiring** population is derived from the command strings ``sync`` emits, not
  from a scan of the source tree. A binary reaches a consumer's host because akmon *wrote it
  into their hook wiring*, so the emitted commands are the only honest source;
* the **own-tooling** population is read from the harness-command map, the single owner of every
  optional-harness executable name and operation.

Neither join inventories the source tree, so a tool akmon runs during its own development is
never promoted into a consumer requirement. The cost is that a binary invoked outside both joins
is invisible here — an open question tracked as A20, recorded rather than papered over.

Modality is *derived*, not restated: a binary present in every vendor's wiring is `required`, one
present in a single vendor's wiring is `required-on:<that vendor>`. The declaration is then
checked against that derivation, so wiring that stops using `git` makes the declaration fail
instead of quietly outliving the fact it describes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from findings import Finding, line_safe
from runtime import (
    GENERATED_WIRING,
    OPTIONAL,
    OWN_TOOLING,
    POSIX_SHELL,
    REQUIRED,
    REQUIRED_ON,
)

#: What a ``$(...)`` substitution is replaced by once it has been read out of a command string.
#: It must survive tokenization as one ordinary word, so it carries no shell metacharacters. A
#: *head* that contains it is refused: the substitution, not the string, names the binary.
_SUBSTITUTION_MARKER = "__akmon_substitution__"

#: An unread expansion in a head position. ``$RUNNER hook.py`` used to declare a binary literally
#: named ``$RUNNER``; the command string does not say what runs, so it is refused.
_EXPANSION_RE = re.compile(r"\$")

#: Operators that end one executable segment and begin another. `_tokenize` emits an operator
#: only where the text is unquoted, so `python3 a.py "&&" evil.py` keeps `&&` as an argument.
#: A newline is a command separator too, but it arrives as whitespace, so it never reaches this
#: set — `_split_substitutions` rewrites an *unquoted* newline to `;` instead. Listing it here
#: without that rewrite was dead code: `python3 a.py\njq .` read only `python3`.
_SEPARATORS = frozenset({"&&", "||", "|", "|&", ";", ";;", "&", "(", ")"})

#: Redirections consume their target, which is a path and never an executable.
_REDIRECTIONS = frozenset({"<", ">", ">>", "<<<", "<>", ">|", ">&", "<&"})

#: A here-document is not a redirection to a path: its *body* follows, and what that body means
#: depends on the command being fed. `sh <<EOF … EOF` runs a whole script this parser never
#: sees, so the binaries in it went unreported. Refused rather than half-read. `<<<` stays a
#: redirection: a here-string is one word, not a body. `<<-` is deliberately absent rather than
#: listed and dead: `<<-EOF` tokenizes as `<<` and `-EOF`, so the one entry catches both.
_HEREDOCS = frozenset({"<<"})

#: Wrappers that run the command *after* them. Reading the wrapper as the invoked binary loses
#: the real one: `command git status` needs `git` on the host, not a binary called `command`.
#:
#: Each wrapper has its own option grammar — `env -i`, `sudo -u NAME`, `timeout DURATION`,
#: `nice -n N`, `xargs -n1` — and skipping the wrapper name alone reports the *option* as the
#: binary. Rather than encode five option grammars and be wrong about the sixth, a wrapper is
#: read only when the very next token is a plain word; anything else is refused.
#: Wrappers the shell itself provides: declaring the shell already covers them.
_SHELL_WRAPPERS = frozenset({"command", "exec", "builtin"})

#: Wrappers that are themselves external programs. The host needs *both* the wrapper and the
#: command it runs, so the wrapper is recorded as a binary and the walk continues past it.
#: `time` is deliberately absent: see `_REFUSED_TOKENS`.
_EXTERNAL_WRAPPERS = frozenset({
    "nohup", "env", "sudo", "doas", "nice", "ionice", "setsid", "stdbuf", "xargs",
})

_WRAPPERS = _SHELL_WRAPPERS | _EXTERNAL_WRAPPERS

#: Wrappers whose grammar puts a mandatory *positional* argument before the command, so the
#: "next plain word is the binary" rule reads that argument instead: `timeout 5 python3 a.py`
#: would report a binary named `5`. Refused rather than special-cased one wrapper at a time.
_POSITIONAL_WRAPPERS = frozenset({"timeout"})

#: Keywords that introduce a *word list* rather than a command list — loop variables, `case`
#: subjects and their patterns. Reading them as commands invents binaries out of variable names
#: (`for f in *.py` reported `f`). akmon emits none of these, so they are refused rather than
#: half-parsed. `if`/`then`/`else`/`while`/`until`/`do` are absent on purpose: each *is* followed
#: by a command, so the ordinary segment walk is correct for them.
_UNSUPPORTED_KEYWORDS = frozenset({"for", "select", "case", "esac", "in", "function"})


#: Tokens that open a grammar of their own rather than a command list. Walking one invents
#: binaries out of its operands: `(( x = 1 ))` reported `x`, and `[[ -f a && -f b ]]` reported
#: `-f`, because the `&&` *inside* the brackets restarted the segment walk. `time` is here for a
#: different reason — it is a shell reserved word in some shells and `/usr/bin/time` in others,
#: so whether it is a host requirement cannot be read from the command string at all. Refused in
#: *head* position only: as an argument (`--sort time`, `--pattern "[["`) a word opens no
#: grammar, and refusing there was a false failure bought with nothing.
_REFUSED_TOKENS = {
    "[[": "a '[[ ... ]]' conditional is outside the supported grammar",
    "((": "an arithmetic command is outside the supported grammar",
    "coproc": "'coproc' is outside the supported grammar",
    "time": "'time' is a shell keyword in some shells and an external program in others, so "
            "whether it names a host requirement cannot be read from the command string",
}

#: A function *definition* is not an invocation. `foo() { ... ; }` put `foo` in the binary set,
#: naming a host requirement that the command string itself defines. The empty parameter list
#: arrives as the operator pair `(` `)` directly after a word, which nothing else produces.
#: The name may be any word, `echo() { ... ; }` included, so every head is a candidate.

#: Utilities POSIX requires the shell itself to provide. They are already covered by declaring
#: the shell, so counting them again would demand host declarations for `cd` and `echo`.
_SHELL_BUILTINS = frozenset({
    ":", ".", "[", "alias", "bg", "break", "cd", "continue", "echo", "eval", "exit", "export",
    "false", "fg", "getopts", "hash", "jobs", "kill", "local", "printf", "pwd", "read",
    "readonly", "return", "set", "shift", "source", "test", "times", "trap", "true", "type",
    "ulimit", "umask", "unalias", "unset", "wait",
})

#: Shell keywords a command genuinely follows, so the segment walk resumes after them.
_SHELL_KEYWORDS = frozenset({
    "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "{", "}", "!",
})

#: What must precede an unquoted ``#`` for it to open a comment. Anywhere else it is an ordinary
#: character, which is why the comment is stripped here rather than by the tokenizer.
_WORD_BREAK = " \t\n;&|()<>"

#: A ``NAME=value`` prefix assigns an environment variable for one command; the binary follows.
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class UnparsedCommand(Exception):
    """A command string this parser will not claim to have read completely."""


#: Operator runs, longest first: `<<` must be tried before `<`, `&&` before `&`.
#: `((` and `))` are listed so an arithmetic command stays one token and can be refused; with a
#: space between them, `( ( … ) )` is ordinary nested grouping and tokenizes as such.
_OPERATORS = (
    "<<<", "<<", ">>", ">&", "<&", ">|", "<>", "&&", "||", "|&", ";;", "((", "))", "|", ";", "&",
    "(", ")", "<", ">",
)

_WHITESPACE = " \t\r\n"


def _tokenize(text: str) -> list:
    """``(operator, value)`` per token; ``operator`` is ``None`` for an ordinary word.

    This replaced a pair of `shlex` passes — one quoted, one not — that were run together so
    structure could be read from the quoted form and names from the unquoted one. They disagree
    on any word that *mixes* the two, which is ordinary shell: `"$DIR"/hook.py` is one word to a
    shell, two to the raw pass. The guard against that disagreement then refused a legitimate
    command and blamed a backslash for it.

    Reading the text directly removes the reconciliation instead of tightening it. What arrives
    here has already been through `_split_substitutions`, so substitutions, comments, backticks
    and unbalanced quotes are gone: the remaining grammar is words, quotes, escapes and operator
    runs. A quoted operator can no longer *become* an operator, because quoting is resolved here
    rather than one pass earlier.
    """
    tokens = []
    word = []
    in_word = False
    index = 0

    def flush():
        nonlocal in_word
        if in_word:
            tokens.append((None, "".join(word)))
            word.clear()
            in_word = False

    while index < len(text):
        character = text[index]
        if character in _WHITESPACE:
            flush()
            index += 1
            continue
        if character == "\\":
            word.append(text[index + 1:index + 2])
            in_word = True
            index += 2
            continue
        if character == "'":
            closing = text.index("'", index + 1)      # balance guaranteed by the scanner
            word.append(text[index + 1:closing])
            in_word = True
            index = closing + 1
            continue
        if character == '"':
            index += 1
            in_word = True
            while index < len(text) and text[index] != '"':
                if text[index] == "\\":
                    word.append(text[index + 1:index + 2])
                    index += 2
                    continue
                word.append(text[index])
                index += 1
            index += 1
            continue
        for operator in _OPERATORS:
            if text.startswith(operator, index):
                flush()
                tokens.append((operator, operator))
                index += len(operator)
                break
        else:
            word.append(character)
            in_word = True
            index += 1
    flush()
    return tokens


def _heads(text: str) -> set:
    """The binary each executable segment of ``text`` invokes.

    Raises ``UnparsedCommand`` for any construct outside the supported grammar, so a caller
    never receives a partial reading that looks complete.
    """
    binaries = set()
    expect_head = True
    skip_target = False
    pending_wrapper = None
    last_head = None
    tokens = _tokenize(text)
    for index, (operator, token) in enumerate(tokens):
        # `foo()` reaches this as two operator tokens, and `(` would otherwise reset `last_head`
        # as an ordinary segment break, so the pair is recognised before that happens.
        if (
            operator == "("
            and last_head is not None
            and index + 1 < len(tokens)
            and tokens[index + 1][0] == ")"
        ):
            raise UnparsedCommand(
                f"{last_head!r} is a function definition, not an invocation of a host binary"
            )
        if pending_wrapper is not None:
            wrapper, pending_wrapper = pending_wrapper, None
            if operator is None and token.startswith("-"):
                raise UnparsedCommand(
                    f"{wrapper!r} is followed by the option {token!r}; this parser does not "
                    f"read wrapper option grammars"
                )
            if operator in _SEPARATORS:
                raise UnparsedCommand(f"{wrapper!r} is not followed by a command")
        if skip_target:
            skip_target = False
            continue
        if expect_head and token in _REFUSED_TOKENS:
            raise UnparsedCommand(_REFUSED_TOKENS[token])
        if operator in _HEREDOCS:
            raise UnparsedCommand(
                "a here-document body is data, not a command list; this parser does not read it"
            )
        if operator in _REDIRECTIONS:
            skip_target = True
            continue
        if operator is not None:
            expect_head = True
            last_head = None
            continue
        if not expect_head:
            last_head = None          # only a word *immediately* followed by `()` defines one
            continue
        if not token:
            raise UnparsedCommand("an empty word is not a command name")
        if token in _UNSUPPORTED_KEYWORDS:
            raise UnparsedCommand(f"the {token!r} construct is outside the supported grammar")
        if token in _POSITIONAL_WRAPPERS:
            raise UnparsedCommand(
                f"{token!r} takes a positional argument before the command it runs; this parser "
                f"does not read wrapper option grammars"
            )
        if _ASSIGNMENT_RE.match(token) or token in _SHELL_KEYWORDS:
            continue
        if _SUBSTITUTION_MARKER in token:
            raise UnparsedCommand(
                "a command substitution supplies the binary name; the command string does not "
                "say what runs"
            )
        if _EXPANSION_RE.search(token):
            raise UnparsedCommand(
                f"the head {token!r} is an expansion; the command string does not say what runs"
            )
        # A function may be *named* after a builtin or a wrapper — `echo() { jq .; }` is valid
        # shell — so every word consumed in head position is a candidate definition name, not
        # only the ones that end up in `binaries`.
        if token in _WRAPPERS:
            if token in _EXTERNAL_WRAPPERS:
                binaries.add(token)
            pending_wrapper = token
            last_head = token
            continue
        if token in _SHELL_BUILTINS:
            last_head = token
            expect_head = False
            continue
        binaries.add(token)
        last_head = token
        expect_head = False
    if pending_wrapper is not None:
        raise UnparsedCommand(f"{pending_wrapper!r} is not followed by a command")
    return binaries


#: The operative Python surface the duplicate-owner scan covers. Tests are excluded: a fixture
#: naming a harness is describing the map, not bypassing it.
_OWN_TOOL_SOURCE_DIRS = ("bin", "hooks", "tools", "src/akmon")


def _read_substitution(text: str, start: int) -> tuple:
    """The body of a ``$(`` opened at ``start``, and the index just past its closing ``)``.

    Parentheses are *counted* and quotes are tracked, because `$(a $(b))` and `$(echo ")")` both
    end at a `)` that a first-closing-paren rule reads as the end of the outer substitution.
    """
    depth = 1
    index = start
    quote = None
    while index < len(text):
        character = text[index]
        if quote == "'":
            if character == "'":
                quote = None
        elif character == "\\":
            index += 2
            continue
        elif quote == '"':
            if character == '"':
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    raise UnparsedCommand("an unterminated $( ... ) substitution")


def _split_substitutions(text: str) -> tuple:
    """``(bodies, text)`` with every command substitution lifted out and marked.

    Quoting decides what a `$(` *is*: inside single quotes it is data, inside double quotes it
    still substitutes. A regex over the raw string could not tell those apart — `printf %s
    '$(jq .)'` declared `jq` from a literal string — and stopped at the first `)`, so the outer
    command of a nested substitution went unread. Backticks and `$((` are refused here rather
    than by a raw-text search, for the same reason: inside single quotes they are data.
    """
    bodies = []
    out = []
    index = 0
    quote = None
    while index < len(text):
        character = text[index]
        if quote == "'":
            out.append(character)
            if character == "'":
                quote = None
            index += 1
            continue
        if character == "\\":
            out.append(text[index:index + 2])
            index += 2
            continue
        if character == "`":
            raise UnparsedCommand("backtick command substitution is not read by this parser")
        if text.startswith("$((", index):
            raise UnparsedCommand("arithmetic expansion is not read by this parser")
        if text.startswith("$(", index):
            body, index = _read_substitution(text, index + 2)
            bodies.append(body)
            out.append(_SUBSTITUTION_MARKER)
            continue
        if quote == '"':
            if character == '"':
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "\n":
            # an unquoted newline separates two commands exactly as `;` does
            out.append(";")
            index += 1
            continue
        elif character == "#" and (not out or out[-1][-1] in _WORD_BREAK):
            # a comment, but only at a word start: `a.py#x` is a literal argument
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        out.append(character)
        index += 1
    if quote is not None:
        raise UnparsedCommand("an unbalanced quote: the token stream is not trustworthy")
    return bodies, "".join(out)


def _binaries_in_command(command) -> set:
    """Every executable a generated command entry invokes, plus the shell that carries it.

    The string is tokenized as a shell would, then read segment by segment. Taking the head of
    the whole string closed the join over one binary per entry; splitting the raw string with a
    regex instead mistook operators inside quoted arguments for segment boundaries. Raises
    ``UnparsedCommand`` for a construct this parser does not read, so the caller reports the
    refusal rather than returning a confident under-count.
    """
    if not isinstance(command, str):
        # An argv list is executed directly: no shell parses it, so no shell carrier.
        return {command[0]} if command else set()
    binaries = {POSIX_SHELL}
    pending, outer = _split_substitutions(command)
    binaries |= _heads(outer)
    while pending:                       # a substitution may itself contain substitutions
        nested, inner = _split_substitutions(pending.pop())
        pending.extend(nested)
        binaries |= _heads(inner)
    return binaries


def derive_generated_population(wiring) -> dict:
    """``vendor -> binaries`` invoked by that vendor's generated command entries.

    Commands the parser refuses are excluded from the derivation and reported separately; a
    refusal must not silently shrink the population the declaration is checked against.
    """
    population, _ = derive_generated_population_with_refusals(wiring)
    return population


def derive_generated_population_with_refusals(wiring) -> tuple:
    """The population, plus the ``(vendor, command, reason)`` entries that could not be read."""
    population: dict = {}
    refusals: list = []
    for vendor, commands in wiring.items():
        binaries: set = set()
        for command in commands:
            try:
                binaries |= _binaries_in_command(command)
            except UnparsedCommand as exc:
                refusals.append((vendor, command, str(exc)))
        population[vendor] = binaries
    return population, refusals


def _expected_generated_modality(binary: str, per_vendor: dict) -> str:
    vendors = sorted(vendor for vendor, binaries in per_vendor.items() if binary in binaries)
    if len(vendors) == len(per_vendor) and vendors:
        return REQUIRED
    if len(vendors) == 1:
        return REQUIRED_ON + vendors[0]
    return REQUIRED


def own_tool_literals(root: Path, binaries) -> list:
    """Sources outside the map that spell a harness binary as a bare string constant."""
    wanted = set(binaries)
    owner = (root / "bin" / "runtime.py").resolve()
    offenders = []
    for directory in _OWN_TOOL_SOURCE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.resolve() == owner:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in wanted:
                    offenders.append((path.relative_to(root).as_posix(), node.lineno, node.value))
    return offenders


def generated_wiring(root: Path) -> dict:
    """``vendor -> command entries`` as ``sync`` would emit them for ``root``.

    Read from the generators rather than from a written tree, so the join holds for a checkout
    that has never been synced and cannot be satisfied by a stale file on disk.
    """
    import sync

    def entries(hooks: dict) -> list:
        commands = []
        for group in hooks.get("hooks", hooks).values():
            for entry in group:
                commands.extend(hook["command"] for hook in entry.get("hooks", []))
        return commands

    return {"claude": entries(sync._claude_hooks(root)), "codex": entries(sync._codex_hooks(root))}


def check_declared_runtimes(root: Path) -> list:
    """The join over akmon's own declaration, map and wiring — what ``self_ci`` calls."""
    import runtime as runtime_declaration

    return check_runtime(
        declarations=runtime_declaration.DECLARED_RUNTIMES,
        harness_commands=runtime_declaration.HARNESS_COMMANDS,
        wiring=generated_wiring(root),
        root=root,
    )


def check_runtime(*, declarations, harness_commands, wiring, root: Path) -> list:
    """The F16 join, as one pure function over its four inputs."""
    findings: list = []
    per_vendor, refusals = derive_generated_population_with_refusals(wiring)
    for vendor, command, reason in refusals:
        findings.append(
            Finding(
                "error", "runtime.unparsed-command",
                f"{vendor} wiring carries a command this checker will not claim to have read "
                f"({reason}): {line_safe(command)}",
                f"generated-wiring:{vendor}",
                "Rewrite the generated command in the supported grammar — quoted arguments, "
                "$(...) substitutions, and operators between plain segments — so every binary "
                "it invokes is visible to the declaration join.",
            )
        )
    generated = {binary for binaries in per_vendor.values() for binary in binaries}
    own = {spec.binary for spec in harness_commands.values()}
    declared = {declaration.binary: declaration for declaration in declarations}

    for binary in sorted(generated - set(declared)):
        findings.append(
            Finding(
                "error", "runtime.undeclared-binary",
                f"generated wiring invokes {binary!r}, which no runtime declaration names",
                "bin/runtime.py",
                f"Declare {binary} in the {GENERATED_WIRING} population, or stop emitting it.",
            )
        )
    for binary in sorted(own - set(declared)):
        findings.append(
            Finding(
                "error", "runtime.undeclared-binary",
                f"the harness-command map invokes {binary!r}, which no runtime declaration names",
                "bin/runtime.py",
                f"Declare {binary} in the {OWN_TOOLING} population, or drop it from the map.",
            )
        )

    for declaration in declarations:
        binary = declaration.binary
        found = GENERATED_WIRING if binary in generated else OWN_TOOLING if binary in own else None
        if found is None:
            findings.append(
                Finding(
                    "warn", "runtime.unused-binary",
                    f"{binary!r} is declared in {declaration.population or '(no population)'} "
                    f"but nothing in that population invokes it",
                    "bin/runtime.py",
                    f"Drop the {binary} declaration, or restore the call that needed it.",
                )
            )
            continue
        if declaration.population != found:
            findings.append(
                Finding(
                    "error", "runtime.wrong-population",
                    f"{binary!r} is declared in {declaration.population or '(no population)'} "
                    f"but is invoked by {found}",
                    "bin/runtime.py",
                    f"Declare {binary} in the {found} population.",
                )
            )
            continue
        expected = (
            _expected_generated_modality(binary, per_vendor)
            if found == GENERATED_WIRING
            else OPTIONAL
        )
        if declaration.modality != expected:
            findings.append(
                Finding(
                    "error", "runtime.wrong-modality",
                    f"{binary!r} is declared {declaration.modality!r} but its "
                    f"{found} use is {expected!r}",
                    "bin/runtime.py",
                    f"Declare {binary} as {expected}.",
                )
            )

    for relative, line, binary in own_tool_literals(root, own):
        findings.append(
            Finding(
                "error", "runtime.duplicate-query-owner",
                f"{binary!r} is spelled outside the harness-command map",
                f"{relative}:{line}",
                "Reach this harness through runtime.harness_command instead.",
            )
        )
    return findings
