# The shared window — scaffold for the shared-Chrome scenario

Reference of [`akmon-browser`](../SKILL.md) for the shared-window scenario: a web resource with no
API (or no token) that the user is signed in to, which the agent reads through the user's session.
akmon owns the mechanics; the project owns the words below.

## The project's settings

`[browser]` in `<dev root>/.akmon.toml`; each key is overridden by its environment variable. A relative
path is relative to the project root.

| Key | Environment | Default | Meaning |
|---|---|---|---|
| `chrome` | `AKMON_BROWSER_CHROME` | the lookup below | The Chrome executable to run |
| `port` | `AKMON_BROWSER_PORT` | `9300 + sha1(realpath of the project root) % 600` | The DevTools port, on 127.0.0.1 only |
| `profile` | `AKMON_BROWSER_PROFILE` | `<dev root>/.local/.browser/chrome-profile` (`-cft` for a Chrome for Testing) | The Chrome profile folder |
| `proxy` | `AKMON_BROWSER_PROXY` | the agent's `HTTPS_PROXY`, `HTTP_PROXY` or `ALL_PROXY`, with `NO_PROXY` as the bypass list | `system`, `direct`, or a proxy URL |
| `extensions` | `AKMON_BROWSER_EXTENSIONS` (paths joined by the OS path delimiter) | none | Unpacked extensions to load, each a folder with a `manifest.json`; see [`extension.md`](extension.md) |

```toml
[browser]
port = 9333
proxy = "direct"
```

A consumer that is not an akmon project (a folder with no `_aitna/akmon`, `.akmon.toml` or `.aitna-root`) sets
`AKMON_BROWSER_ROOT` to the absolute path of that folder. It wins over discovery from the working directory:
the project is that folder, its state is `<root>/.local/.browser/` (there is no `<dev root>`), no `[browser]`
table is read (the other `AKMON_BROWSER_*` variables still apply), and the derived port is the same formula over
the folder's real path. A relative or missing path is refused. `init` refuses under it: the MCP server the host
starts would not carry the variable.

The Chrome lookup order (with `extensions` configured it is only the `chrome` setting, then the Chrome for
Testing below: a branded Chrome from 137 on ignores `--load-extension`): the `chrome` setting; a Chrome or Chromium on `PATH`; the platform's usual
install path; under WSL the Windows Chrome (then the MCP server runs on the Windows side); a Chrome for
Testing that `install` put under `<dev root>/.local/.browser/chrome/`. The launch record of the last
`start` is `<dev root>/.local/.browser/launch.json`. Everything under `.local/` is git-ignored: the
profile holds the user's sign-ins and never leaves the machine.

## The MCP server and the shared window

The MCP server (Claude Code, through `.mcp.json`) attaches to the project's Chrome, so the order is:
`akmon tool browser start`, then `/mcp` reconnect. With nothing on the project's port the launcher
refuses to start, because a Chrome that took the port later would be driven without the ownership
check; a Chrome that is another project's, or that akmon did not start, is refused the same way. Codex
does not read `.mcp.json` (it reads its own `config.toml`, which `init` does not write): there, use the
`akmon tool browser` verbs.

## Resource hosts

A project that reads internal resources through the browser keeps, in its **own** skill (not here), one
note per host: the address, how the user signs in, what the pages are called, and which route a plain
web request takes (it returns the login page, which is why the browser is the route). akmon ships no
host list. The note says, per host, that a web fetch of it is the wrong tool and the browser the right
one, so the agent does not report "the page was empty" for a login page.

## The consent wording

The agent asks before any step that changes something, in one sentence naming the step and the page, and
waits for the user's answer while the user watches the window:

> I am about to click **Save** on *<page title>* (<host>), which will <what changes>. Go ahead?

- One yes covers that one step. A second step, or the same step on another record, asks again.
- Reading, navigating, expanding, searching and filtering do not ask.
- The agent never asks the user to type a secret into the conversation: it asks them to type it in the
  window themselves.
- After the step the agent reads the result back from the page and reports what it saw, not what it
  expected.
