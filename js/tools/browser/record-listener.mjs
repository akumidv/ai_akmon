/**
 * The listener a recording injects into every document of the page it records (`Page.addScriptToEvaluateOnNewDocument`,
 * and `Runtime.evaluate` into the document that is open): it watches what the user does and reports it
 * through a CDP binding, one JSON text per event, shaped as `record-events.mjs` reads them. It reports where
 * an action happened (the element, found again by a role, a test id, a label or a CSS path) and never what a
 * field holds: for a typed field only the length, and for a secret field (a password, a one-time code, a name
 * on the redact list) not even that.
 *
 * `recorderListener` is one self-contained function, because its source text is what is injected: it may use
 * nothing outside itself. A test runs it against a small fake document. Pure, with no import.
 */

/**
 * What the injected listener is told.
 * @typedef {object} ListenerConfig
 * @property {string} binding the name of the CDP binding the page calls with each event
 * @property {string[]} keys the redact keys: a field whose name, id or label holds one is a secret
 * @property {string} flag the window property that marks the listener as installed and holds its `dispose`
 * @property {number} debounceMs how long typing must pause before an `input` event is reported
 */

/**
 * Install the listener on a window. A second call on the same window does nothing.
 * The helpers are nested because the function is injected as text and so closes over nothing.
 * @param {any} win the window (`window` in the page)
 * @param {ListenerConfig} config
 * @returns {void}
 */
export function recorderListener(win, config) {
  if (win[config.flag]) {
    return;
  }
  const doc = win.document;
  const wanted = config.keys
    .map((key) =>
      String(key)
        .toLowerCase()
        .replace(/[^a-z0-9]/g, ""),
    )
    .filter(Boolean);
  const fieldTags = ["input", "textarea", "select"];
  const interactiveTags = ["a", "button", "input", "select", "textarea", "label", "summary", "option"];
  const interactiveRoles = ["button", "link", "checkbox", "radio", "tab", "menuitem", "switch", "option", "combobox"];
  const keyNames = ["Enter", "Escape", "Tab"];

  /** @type {(...args: any[]) => any} */
  const clip = (text, limit) => {
    const flat = String(text === undefined || text === null ? "" : text)
      .replace(/\s+/g, " ")
      .trim();
    return flat.length > limit ? flat.slice(0, limit) : flat;
  };
  /** @type {(...args: any[]) => any} */
  const attr = (el, name) => {
    const value = el && el.getAttribute ? el.getAttribute(name) : null;
    return value === null || value === undefined ? "" : String(value);
  };
  /** @type {(...args: any[]) => any} */
  const tagOf = (el) => String((el && el.tagName) || "").toLowerCase();
  /** @type {(...args: any[]) => any} */
  const namesSecret = (texts) =>
    texts.some((/** @type {any} */ text) => {
      const name = String(text || "")
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");
      return name !== "" && wanted.some((key) => name.includes(key));
    });
  /** @type {(...args: any[]) => any} */
  const labelOf = (el) => {
    const labels = el.labels && el.labels.length > 0 ? Array.from(el.labels) : [];
    if (labels.length > 0) {
      return clip(labels[0].textContent, 80);
    }
    for (let node = el.parentElement, depth = 0; node && depth < 3; node = node.parentElement, depth += 1) {
      if (tagOf(node) === "label") {
        return clip(node.textContent, 80);
      }
    }
    return clip(attr(el, "aria-label"), 80);
  };
  /** @type {(...args: any[]) => any} */
  const isField = (el) => fieldTags.includes(tagOf(el));
  /** @type {(...args: any[]) => any} */
  const typeOf = (el) => (tagOf(el) === "input" ? attr(el, "type").toLowerCase() || "text" : "");
  /** @type {(...args: any[]) => any} */
  const isSecretField = (el) => {
    if (!isField(el)) {
      return false;
    }
    const autocomplete = attr(el, "autocomplete").toLowerCase();
    return (
      typeOf(el) === "password" ||
      autocomplete.includes("password") ||
      autocomplete.includes("one-time-code") ||
      namesSecret([attr(el, "id"), attr(el, "name"), labelOf(el), attr(el, "aria-label"), attr(el, "placeholder")])
    );
  };
  /** @type {(...args: any[]) => any} */
  const roleOf = (el) => {
    const explicit = attr(el, "role");
    if (explicit !== "") {
      return explicit.split(" ")[0];
    }
    const tag = tagOf(el);
    const type = typeOf(el);
    /** @type {Record<string, string>} */
    const byType = {
      checkbox: "checkbox",
      radio: "radio",
      submit: "button",
      button: "button",
      reset: "button",
      image: "button",
      range: "slider",
      search: "searchbox",
      number: "spinbutton",
      password: "",
      hidden: "",
      file: "",
      color: "",
      date: "",
    };
    if (tag === "input") {
      return Object.prototype.hasOwnProperty.call(byType, type) ? byType[type] : "textbox";
    }
    if (tag === "a") {
      return attr(el, "href") === "" ? "" : "link";
    }
    /** @type {Record<string, string>} */
    const byTag = { button: "button", textarea: "textbox", select: "combobox", summary: "button", option: "option" };
    if (/^h[1-6]$/.test(tag)) {
      return "heading";
    }
    return Object.prototype.hasOwnProperty.call(byTag, tag) ? byTag[tag] : "";
  };
  /** @type {(...args: any[]) => any} */
  const testIdOf = (el) => attr(el, "data-testid") || attr(el, "data-test") || attr(el, "data-qa");
  /** @type {(...args: any[]) => any} */
  const cssPathOf = (el) => {
    const parts = [];
    let node = el;
    for (let depth = 0; node && tagOf(node) !== "" && depth < 6; depth += 1) {
      const id = attr(node, "id");
      if (id !== "") {
        parts.unshift(/^[A-Za-z][\w-]*$/.test(id) ? `#${id}` : `${tagOf(node)}[id="${id.replace(/["\\]/g, "")}"]`);
        break;
      }
      const tag = tagOf(node);
      const siblings = node.parentElement
        ? Array.from(node.parentElement.children).filter((other) => tagOf(other) === tag)
        : [];
      parts.unshift(siblings.length > 1 ? `${tag}:nth-of-type(${siblings.indexOf(node) + 1})` : tag);
      node = node.parentElement;
    }
    return parts.join(" > ");
  };
  /** @type {(...args: any[]) => any} */
  const snippetOf = (el) => {
    if (isField(el) || el.isContentEditable === true) {
      return "";
    }
    return clip(el.innerText !== undefined ? el.innerText : el.textContent, 60);
  };
  /** @type {(...args: any[]) => any} */
  const nameOf = (el, text) => {
    const aria = attr(el, "aria-label");
    if (aria !== "") {
      return clip(aria, 80);
    }
    if (isField(el)) {
      const type = typeOf(el);
      const label = labelOf(el);
      if (label !== "") {
        return label;
      }
      return type === "submit" || type === "button" || type === "reset" ? clip(attr(el, "value"), 80) : "";
    }
    return clip(attr(el, "alt") || text || attr(el, "title"), 80);
  };
  /** @type {(...args: any[]) => any} */
  const describe = (el) => {
    const secret = isSecretField(el);
    const text = secret ? "" : snippetOf(el);
    return {
      tag: tagOf(el),
      role: roleOf(el),
      name: secret && !attr(el, "aria-label") ? labelOf(el) : nameOf(el, text),
      testid: testIdOf(el),
      id: attr(el, "id"),
      nameAttr: attr(el, "name"),
      label: isField(el) ? labelOf(el) : "",
      text,
      css: cssPathOf(el),
      type: typeOf(el),
      sensitive: secret,
    };
  };
  /** @type {(...args: any[]) => any} */
  const targetOf = (el) => {
    let node = el;
    for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
      if (
        interactiveTags.includes(tagOf(node)) ||
        interactiveRoles.includes(attr(node, "role")) ||
        testIdOf(node) !== ""
      ) {
        return node;
      }
    }
    return el;
  };
  /** @type {(...args: any[]) => any} */
  const report = (event) => {
    try {
      win[config.binding](JSON.stringify(event));
    } catch {
      // The binding is gone (the recording ended): there is nobody to tell.
    }
  };
  /** @type {(...args: any[]) => any} */
  const valueEvent = (kind, el) => {
    const secret = isSecretField(el);
    const type = typeOf(el);
    const toggle = type === "checkbox" || type === "radio";
    /** @type {Record<string, any>} */
    const event = { kind, target: describe(el), length: secret || toggle ? null : String(el.value || "").length };
    if (toggle) {
      event.checked = el.checked === true;
    }
    return event;
  };

  /** @type {any} */
  let pending = null;
  /** @type {any} */
  let timer = null;
  const flush = () => {
    if (timer !== null) {
      win.clearTimeout(timer);
      timer = null;
    }
    if (pending !== null) {
      const el = pending;
      pending = null;
      report(valueEvent("input", el));
    }
  };
  /** @type {(...args: any[]) => any} */
  const onInput = (event) => {
    const el = event.target;
    if (!isField(el)) {
      return;
    }
    if (pending !== null && pending !== el) {
      flush();
    }
    pending = el;
    if (timer !== null) {
      win.clearTimeout(timer);
    }
    timer = win.setTimeout(flush, config.debounceMs);
  };
  /** @type {(...args: any[]) => any} */
  const onChange = (event) => {
    const el = event.target;
    if (!isField(el)) {
      return;
    }
    flush();
    report(valueEvent("change", el));
  };
  /** @type {(...args: any[]) => any} */
  const onClick = (event) => {
    if (event.isTrusted === false) {
      return;
    }
    flush();
    report({ kind: "click", target: describe(targetOf(event.target)) });
  };
  /** @type {(...args: any[]) => any} */
  const onSubmit = (event) => {
    flush();
    const form = event.target;
    report({
      kind: "submit",
      method: attr(form, "method"),
      target: {
        tag: "form",
        id: attr(form, "id"),
        nameAttr: attr(form, "name"),
        testid: testIdOf(form),
        css: cssPathOf(form),
      },
    });
  };
  /** @type {(...args: any[]) => any} */
  const onKeydown = (event) => {
    if (!keyNames.includes(event.key)) {
      return;
    }
    flush();
    report({ kind: "keydown", key: event.key, target: describe(event.target) });
  };

  /** @type {Record<string, (event: any) => void>} */
  const handlers = { click: onClick, input: onInput, change: onChange, submit: onSubmit, keydown: onKeydown };
  for (const name of Object.keys(handlers)) {
    doc.addEventListener(name, handlers[name], true);
  }
  win[config.flag] = {
    dispose: () => {
      flush();
      for (const name of Object.keys(handlers)) {
        doc.removeEventListener(name, handlers[name], true);
      }
      delete win[config.flag];
    },
  };
}

/**
 * The source text of the listener installed with `config`, ready for `Page.addScriptToEvaluateOnNewDocument`.
 * @param {ListenerConfig} config
 * @returns {string}
 */
export function listenerSource(config) {
  return `(${recorderListener.toString()})(window, ${JSON.stringify(config)});`;
}

/**
 * The source text that removes an installed listener, for the document that is open when a recording ends.
 * @param {string} flag the window property of the listener
 * @returns {string}
 */
export function disposeSource(flag) {
  const name = JSON.stringify(flag);
  return `(() => { const held = window[${name}]; if (held) { held.dispose(); } })();`;
}
