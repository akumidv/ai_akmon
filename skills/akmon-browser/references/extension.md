# Developing and checking a browser extension — scaffold for the extension bench

Reference of [`akmon-browser`](../SKILL.md) for a project that builds a Chrome extension (usually one
that works on a third-party site) and wants the agent to load it, reload it, read its logs and check the
selectors it depends on, in a real Chrome. akmon owns the verbs; the project owns the settings, the
selector registry, the sign-in test and the pacing limit. Every step is a Bash verb of
`akmon tool browser`, so it works in a script or a harness without the MCP server: the MCP server
attached to a running Chrome has no extension tools and no service-worker targets, so extension work is
done with these verbs.

## The settings

`[browser]` in `<dev root>/.akmon.toml`, beside the keys in [`shared-window.md`](shared-window.md):

```toml
[browser]
extensions = ["extension"]        # unpacked extensions to load, relative to the project root
```

- Each entry is a folder that holds a `manifest.json`; the tool refuses, in one line naming the entry,
  a folder that does not. `AKMON_BROWSER_EXTENSIONS` (paths joined by the OS path delimiter, `:` or `;`)
  replaces the list. A path may not hold a comma (Chrome's flag joins the paths with commas).
- **A project that loads extensions needs Chrome for Testing.** A branded Chrome from version 137 on
  ignores `--load-extension`, so the tool does not use one found on the machine: `start` refuses, in
  one line, when only a branded Chrome exists, and `akmon tool browser install` installs Chrome for
  Testing into the project **even though a branded Chrome is there** (`install --for-extensions` does
  the same before any extension is configured). Ask the user before `install --yes`, as in the rest of
  the skill. Chrome for Testing keeps its own profile, `chrome-profile-cft`, so the user signs in to the
  third-party site once in that window.
- `start` adds `--load-extension` and `--disable-extensions-except` for the configured folders (Windows
  paths for a Windows Chrome under WSL; the launch record, `<dev root>/.local/.browser/launch.json`,
  keeps them), then turns **developer mode** on through `chrome://extensions`' own API, which Chrome
  needs to keep an unpacked extension enabled, and reports each configured extension, with a warning
  for one that did not load.

## The verbs

- `ext list [--json]` — the extensions the Chrome holds: id, name, version, state (enabled or why not),
  folder, and whether it is a configured one.
- `ext reload [<id|name>] [--json]` — reloads the configured unpacked extensions (or the one named) **from
  disk**, the way the reload button of `chrome://extensions` does, then reports each one's state and any
  load error. A manifest error shows here. A `chrome.runtime.reload()` from the extension itself leaves a
  command-line-loaded extension disabled, which is why the reload goes through the browser. Exit 1 when an
  extension is not running afterwards. A manifest that is broken at the time of the reload can leave the
  extension unloaded; fix it and run `restart`, which loads it again from the folder.
- `ext action [<id|name>] [--page P]` — runs the extension's action (its toolbar button) on the selected
  page, as a click would. It asks the browser to do it over the DevTools port (`Extensions.triggerAction`,
  which gives the extension the page as the active tab). When this Chrome does not offer that method on the
  port, it **opens the action's popup page (`default_popup`) in a new tab** instead and says so plainly: that
  popup is a page of its own and **lacks the active-tab context**, so whatever it reads as "the current tab"
  is the popup tab. Work in it with `--target popup`. An action with no popup has no fallback: the
  verb says so, and the user clicks the button.
- `eval`, `logs` and `net` take **`--target page|sw|popup|<targetId>`** (the default is `page`, the
  `--page` one) and **`--ext <id|name>`**:
  - `sw` is the extension's service worker (`--ext` names the extension; the one configured, or the only one
    with a worker, by default). A Manifest V3 worker stops when idle and then has no target: use the
    extension (`ext action`, or its page) and run the verb again.
  - `popup` is an open `chrome-extension://…` page of the extension: its popup, else its options page.
  - a target id is any target of `pages --all`.
- `eval --world page|isolated` — `page` (the default) is the site's own JavaScript world, where the site's
  objects are probed; **`isolated` is the extension's content-script world** on the page, where its content
  script's variables live. Pass `--ext` when several extensions run on the page.
- `logs` tags each line by source: `[page]` (the site's own console), `[extension]` (an extension's
  content-script world on the page), `[sw]` (the service worker) and `[popup]` (an extension page). Wait for
  a line with `--until REGEX`, matched against the printed form: `--until '^\[sw\] console\.log: ready'`.
- `selectors <file> [--page P] [--json]` — the selector check, below.

## The develop loop

1. Edit the extension's source (or its build output, when the project builds).
2. `akmon tool browser ext reload` — fix a manifest error it reports, repeat until the extension is
   enabled.
3. A content script runs on a page when the page loads. **Reloading the page is the user's step or a
   navigation they asked for** — this tool reloads nothing; ask the user to reload it, or to do the step
   that makes the page run the content script.
4. Read what the extension said: `logs --target sw` for the service worker, `logs` for the page and its
   content scripts, `net --target sw` for the worker's requests.
5. Probe the state: `eval --world isolated '<expression>'` for the content script's world, `eval` for the
   site's, `eval --target sw '<expression>'` for the worker. Each reads; none clicks, types or calls the
   site's API.
6. Report what was seen, with the page, the line and the extension's version.

## The selector-drift check

The third-party site changes its DOM, and a selector the extension depends on stops matching. The
project keeps its selectors in a registry; akmon runs them against the live page and never supplies one.

The registry file for `selectors` is JSON, one entry per name, each a list whose **first element is the
primary selector** and whose others are fallbacks tried in order:

```json
{
  "buyButton": ["[data-testid='buy']", "button.buy", "form button[type=submit]"],
  "priceLabel": ["#price"]
}
```

A project whose registry is JavaScript exports this JSON itself (a small script that prints it) and
points `selectors` at the file. Per name the verb reports `matched`, `matched by fallback <n>` (the
n-th fallback found it and the primary did not: the site drifted, update the registry) or `missing`;
it exits 1 when any name is missing. Each selector is counted in the page's own world, in the document
**and in every open shadow root, recursively**; a closed shadow root is reached only by the extension's
own development build, not by this check. A selector the browser rejects is shown with its error. The
check reads the page: it queries, it never changes it.

## Sign-in and the user

The project says what a signed-in session looks like, in its own skill: for example the name of a
session cookie (read it by name only; never print the value), or an element of the registry that only a
signed-in page has. When the page is signed out, the agent asks the user to sign in in the window and
hands over 2FA and captchas; it never types a password or a code.

## Pacing on a live account

A third-party site may flag automated interaction and ban the account. Driving a signed-in page needs a
limit beyond consent:

- **Pace the steps** with a pause between page actions, and **do not loop** on a live account: no
  polling that reloads, clicks or navigates repeatedly. Reading what is already on the page (`eval`,
  `selectors`, `logs`) is not the concern; changing it or requesting more of the site is.
- The project states its own limit (a pause, a cap of actions per minute) in its specialization of this
  skill. Without one, act no faster than a person would.
- Account-visible actions (publish, order, create an alert) are one confirmed step each, as in the rest of
  the skill.

## Production builds

A production build usually strips the console and may close its shadow roots, so `logs` shows nothing and
`selectors` cannot see into a closed root. **Debug the unbundled load**: point `[browser] extensions` at the
development build for the session, and check a production build only for what it should still do.

## What to put in the project's own skill

The extension's folder and build command, the registry file and how it is exported, the sign-in test,
the pages worth walking, the pacing limit, and which service-worker or content-script variables are worth
probing with `eval`. It links this reference instead of copying it.
