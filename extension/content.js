// DraftVoice on LinkedIn. Scope (Fathin's written permission, 2 Oct 2026 19:32): read the ONE post the
// founder chooses, only when they click. Until the tab is clicked, this script only adds the tab.
// It never scrolls, never reads the feed in the background, never stores LinkedIn content,
// never types into LinkedIn, and never posts. Approve in the panel only copies to the clipboard.
//
// How the post is chosen (the founder can switch this in the panel):
//   auto       D, then C, then A, and B if none of them finds a post
//   page    D  on a single post page, its one post
//   click   B  the founder clicks the post they want
//   select  C  the text the founder highlighted before clicking the tab
//   visible A  the post with the largest visible area
(() => {
  "use strict";
  if (window.top !== window || document.getElementById("draftvoice-tab")) return;

  const adapter = window.DraftVoiceLinkedIn;
  const PANEL = chrome.runtime.getURL("panel.html");
  const PANEL_ORIGIN = new URL(PANEL).origin;
  const root = document.documentElement;

  let drawer = null;
  let frame = null;
  let ready = false;
  let queued = [];
  let selected = null;
  let hovered = null;
  let picking = false;
  let method = "auto";
  let highlighted = "";
  let hint = null;
  let hintFor = null;
  let ticking = false;

  const tab = document.createElement("button");
  tab.id = "draftvoice-tab";
  tab.type = "button";
  tab.setAttribute("aria-label", "Open DraftVoice");
  tab.textContent = "DraftVoice";
  document.body.append(tab);

  function send(message) {
    if (ready) frame.contentWindow.postMessage(message, PANEL_ORIGIN);
    else queued.push(message);
  }

  function ensureDrawer() {
    if (drawer) return;
    drawer = document.createElement("div");
    drawer.id = "draftvoice-drawer";
    frame = document.createElement("iframe");
    frame.src = PANEL;
    frame.title = "DraftVoice";
    frame.allow = "clipboard-write";
    drawer.append(frame);
    document.body.append(drawer);
  }

  function outline(el) {
    selected?.classList.remove("draftvoice-selected");
    selected = el;
    el?.classList.add("draftvoice-selected");
  }

  function sendPost(post, el) {
    hideHint();
    outline(el);
    send({ type: "draftvoice:post", post, pickable: true });
  }

  function fail(message) {
    outline(null);
    send({ type: "draftvoice:error", message });
  }

  function useElement(el, failure) {
    const post = adapter.readPost(el);
    if (!post) {
      if (failure) fail(failure);
      return false;
    }
    sendPost(post, el);
    return true;
  }

  // D
  function byPage(strict) {
    if (!adapter.isSinglePostPage()) {
      if (strict) fail("Open a single post first (click its timestamp), then click the tab.");
      return false;
    }
    return useElement(adapter.singlePagePost(), strict && "Couldn't read this post. Try scrolling it into view.");
  }

  // C
  function bySelection(strict) {
    if (highlighted.length < 20) {
      if (strict) fail("Highlight the post's text first, then click the tab.");
      return false;
    }
    sendPost({ author: "", headline: "Highlighted text", text: highlighted }, null);
    return true;
  }

  // A
  function byVisible(strict) {
    return useElement(adapter.mostVisiblePost(), strict && "Couldn't read this post. Try scrolling it into view.");
  }

  // B
  function byClick() {
    outline(null);
    picking = true;
    root.classList.add("draftvoice-picking");
    send({ type: "draftvoice:prompt", message: "Click the post you want to draft for." });
  }

  function choose() {
    stopPicking();
    send({ type: "draftvoice:reading" });
    if (method === "page") return byPage(true);
    if (method === "select") return bySelection(true);
    if (method === "visible") return byVisible(true);
    if (method === "click") return byClick();
    if (byPage(false) || bySelection(false) || byVisible(false)) return;
    byClick();
  }

  function open() {
    ensureDrawer();
    root.classList.add("draftvoice-open");
    tab.setAttribute("aria-expanded", "true");
    choose();
  }

  function close() {
    root.classList.remove("draftvoice-open");
    tab.setAttribute("aria-expanded", "false");
    outline(null);
    stopPicking();
    hideHint();
  }

  // ↻ in the panel: use the post that is on screen now.
  function refresh() {
    stopPicking();
    hideHint();
    send({ type: "draftvoice:reading" });
    if (method === "select") return bySelection(true);
    if (method === "page") return byPage(true);
    if (!byVisible(false)) byClick();
  }

  // While the sidebar is open and the founder scrolls, offer "Draft this post" on the post now most
  // visible. This only looks at where posts are on screen; nothing is read until the button is clicked.
  function hideHint() {
    hint?.remove();
    hint = null;
    hintFor = null;
  }

  function updateHint() {
    ticking = false;
    if (!root.classList.contains("draftvoice-open") || picking) return hideHint();
    const el = adapter.mostVisiblePost();
    if (!el || el === selected) return hideHint();
    if (!hint) {
      hint = document.createElement("button");
      hint.id = "draftvoice-hint";
      hint.type = "button";
      hint.textContent = "Draft this post";
      hint.addEventListener("click", () => {
        const target = hintFor;
        hideHint();
        send({ type: "draftvoice:reading" });
        useElement(target, "Couldn't read this post. Try another one.");
      });
      document.body.append(hint);
    }
    hintFor = el;
    const r = el.getBoundingClientRect();
    const right = Math.min(r.right, innerWidth - 380) - 12;
    hint.style.top = `${Math.max(r.top, 0) + 12}px`;
    hint.style.left = `${Math.max(right - hint.offsetWidth, r.left + 12)}px`;
  }

  window.addEventListener("scroll", () => {
    if (!root.classList.contains("draftvoice-open") || ticking) return;
    ticking = true;
    requestAnimationFrame(updateHint);
  }, { passive: true });

  function stopPicking() {
    picking = false;
    root.classList.remove("draftvoice-picking");
    hovered?.classList.remove("draftvoice-hover");
    hovered = null;
  }

  // C: remember the highlighted text at the moment the founder presses the tab.
  tab.addEventListener("mousedown", () => { highlighted = String(window.getSelection() || "").trim(); });
  tab.addEventListener("click", () => (root.classList.contains("draftvoice-open") ? close() : open()));

  // B: only while picking. Hover shows which post a click would choose; the click selects it and does nothing else.
  document.addEventListener("mouseover", (e) => {
    if (!picking) return;
    const el = adapter.postAt(e.target);
    if (el === hovered) return;
    hovered?.classList.remove("draftvoice-hover");
    hovered = el;
    el?.classList.add("draftvoice-hover");
  }, true);

  document.addEventListener("click", (e) => {
    if (!picking || e.target === tab || drawer?.contains(e.target)) return;
    const el = adapter.postAt(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    stopPicking();
    send({ type: "draftvoice:reading" });
    useElement(el, "Couldn't read this post. Try another one.");
  }, true);

  window.addEventListener("message", (e) => {
    if (!frame || e.source !== frame.contentWindow || e.origin !== PANEL_ORIGIN) return;
    const m = e.data || {};
    if (m.type === "draftvoice:ready") {
      ready = true;
      frame.contentWindow.postMessage({ type: "draftvoice:host", methods: true, method }, PANEL_ORIGIN);
      queued.forEach((q) => frame.contentWindow.postMessage(q, PANEL_ORIGIN));
      queued = [];
    } else if (m.type === "draftvoice:close") {
      close();
    } else if (m.type === "draftvoice:pick") {
      byClick();
    } else if (m.type === "draftvoice:refresh") {
      refresh();
    } else if (m.type === "draftvoice:method" && ["auto", "page", "click", "select", "visible"].includes(m.method)) {
      method = m.method;
      choose();
    }
  });
})();
