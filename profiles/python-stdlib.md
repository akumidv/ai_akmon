# Profile: python-stdlib (environment)

An **environment** profile for Python that must run on a bare interpreter — before a virtual
environment exists, or outside one: a harness hook, a bootstrap or install script, a CLI that
sets the environment up. It layers on the [Python profile](python.md) and applies to the paths a
project names where it imports this profile in `AGENTS.md`.

## Rules

- **The standard library only** — no third-party import, not even one guarded by `try`: code
  here runs exactly where nothing else is installed. No linter checks this; it is a review
  point, and a test that imports the module under a bare interpreter is the usual carrier.
- **The floor is the project's declared `requires-python`,** and the code runs on it: no syntax
  and no standard-library API newer than the floor.
- **Nothing happens at import time.** Importing a module does no I/O, spawns no process and
  reads no environment variable; the work starts in `main()`.
- **Run by path, with the interpreter named** — `python3 tools/bootstrap/setup.py` — never
  through an environment manager that may not exist yet.
- **Fail in one line.** A failure prints one line saying what failed and exits non-zero; it does
  not leave a half-written file behind.
