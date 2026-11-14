/**
 * The proxy Chrome is started with. Chrome ignores `HTTPS_PROXY` and uses only the system proxy,
 * but the agent works in the environment it was started in, often a proxy that is the only route
 * into internal hosts. So `start` hands Chrome the agent's proxy as `--proxy-server` and `NO_PROXY`
 * as `--proxy-bypass-list`; the `proxy` setting overrides (`system`, `direct` or a proxy URL).
 */

/**
 * The proxy arguments for Chrome, and a line saying what they are.
 * @typedef {object} ProxyPlan
 * @property {string[]} args what Chrome is started with: the one place a credential of the proxy is kept
 * @property {string} describe what is printed and recorded: the proxy with its credentials replaced
 */

/**
 * A proxy server value is one or more segments (`;`-separated, Chrome's `http=a:1;https=b:2` per-scheme
 * form among them); a new segment starts where `;` is followed by `scheme=` or `scheme://`.
 */
const _SEGMENT_BREAK = /;(?=[a-z][a-z0-9+.-]*(?:=|:\/\/))/i;
/** What a segment starts with before its userinfo or host: `https=`, `http://`, or both. */
const _SEGMENT_HEAD = /^(?:[a-z][a-z0-9+.-]*=)?(?:[a-z][a-z0-9+.-]*:\/\/)?/i;

/**
 * Apply `change` to the userinfo of each segment of a proxy server value. The userinfo ends at the LAST
 * `@` of the segment, so a password holding an unencoded `/`, `#`, `?`, `@` or space is inside it; a segment
 * has no path, so what follows that `@` is the host.
 * @param {string} server
 * @param {(userinfo: string) => string} change
 * @returns {string}
 */
function _mapSegments(server, change) {
  return server
    .split(_SEGMENT_BREAK)
    .map((segment) => {
      const head = /** @type {RegExpMatchArray} */ (segment.match(_SEGMENT_HEAD))[0];
      const rest = segment.slice(head.length);
      const at = rest.lastIndexOf("@");
      return at < 0 ? segment : `${head}${change(rest.slice(0, at))}${rest.slice(at)}`;
    })
    .join(";");
}

/**
 * A proxy server value with its credentials replaced, so it can be printed and recorded.
 * @param {string} server
 * @returns {string}
 */
export function stripCredentials(server) {
  return _mapSegments(server, () => "***");
}

/**
 * Whether a proxy server value carries credentials.
 * @param {string} server
 * @returns {boolean}
 */
export function hasCredentials(server) {
  let found = false;
  _mapSegments(server, (userinfo) => {
    found = true;
    return userinfo;
  });
  return found;
}

/** The Chrome argument that carries the proxy server. */
const _SERVER_FLAG = "--proxy-server=";

/**
 * Chrome arguments as they may be recorded: the proxy server's credentials replaced.
 * @param {readonly string[]} args
 * @returns {string[]}
 */
export function recordableArguments(args) {
  return args.map((arg) =>
    arg.startsWith(_SERVER_FLAG) ? `${_SERVER_FLAG}${stripCredentials(arg.slice(_SERVER_FLAG.length))}` : arg,
  );
}

/**
 * Whether the proxy arguments of a start carry credentials.
 * @param {readonly string[]} args
 * @returns {boolean}
 */
export function argumentsHaveCredentials(args) {
  return args.some((arg) => arg.startsWith(_SERVER_FLAG) && hasCredentials(arg.slice(_SERVER_FLAG.length)));
}

/**
 * The first non-empty value of `names` in `env`.
 * @param {Record<string, string | undefined>} env
 * @param {string[]} names
 * @returns {string | undefined}
 */
function _pick(env, names) {
  return names.map((name) => env[name]).find(Boolean);
}

/**
 * `NO_PROXY` as Chrome bypass rules: `.domain` becomes `*.domain`; hosts, IPs and CIDRs pass as is.
 * @param {string} noProxy
 * @returns {string[]}
 */
function _bypassRules(noProxy) {
  return noProxy
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (item.startsWith(".") ? `*${item}` : item));
}

/**
 * The proxy plan for a Chrome start. A proxy URL may carry credentials (`http://user:pw@proxy:3128`):
 * Chrome gets them, but `describe` never holds them.
 * @param {Record<string, string | undefined>} env the agent's environment
 * @param {string | null} override the `proxy` setting: `system`, `direct`, a URL, or `null`
 * @returns {ProxyPlan}
 */
export function proxyPlan(env, override) {
  if (override === "system") {
    return { args: [], describe: "system proxy (proxy setting: system)" };
  }
  if (override === "direct") {
    return { args: ["--no-proxy-server"], describe: "no proxy (proxy setting: direct)" };
  }
  const server =
    override ?? _pick(env, ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"]);
  if (!server) {
    return { args: [], describe: "system proxy (none in the environment)" };
  }
  const bypass = _bypassRules(_pick(env, ["NO_PROXY", "no_proxy"]) ?? "");
  const args = [`--proxy-server=${server}`];
  if (bypass.length > 0) {
    args.push(`--proxy-bypass-list=${bypass.join(";")}`);
  }
  const suffix = bypass.length > 0 ? ` (bypass: ${bypass.length} rule(s) from NO_PROXY)` : "";
  return { args, describe: `${stripCredentials(server)}${suffix}` };
}
