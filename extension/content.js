// DraftVoice on LinkedIn. Scope (Fathin's written permission, 2 Oct 2026 19:32): read the ONE post the
// founder chooses, only when they click. Until the tab is clicked, this script only adds the tab.
// It never scrolls, never reads the feed in the background, never stores LinkedIn content,
// never types into LinkedIn, and never posts. Approve in the panel only copies to the clipboard.
(() => {
  "use strict";
  if (window.top !== window || document.getElementById("draftvoice-tab")) return;

  const adapter = window.DraftVoiceLinkedIn;
  const PANEL = chrome.runtime.getURL("panel.html");
  const PANEL_ORIGIN = new URL(PANEL).origin;

  let drawer = null;
  let frame = null;
  let ready = false;
  let queued = [];
  let selected = null;
  let picking = false;

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

  function readAndSend(el) {
    send({ type: "draftvoice:reading" });
    const post = adapter.readPost(el);
    if (!post) {
      outline(null);
      send({ type: "draftvoice:error", message: "Couldn't read this post. Try scrolling it into view." });
      return;
    }
    outline(el);
    send({ type: "draftvoice:post", post, pickable: true });
  }

  function open() {
    ensureDrawer();
    document.documentElement.classList.add("draftvoice-open");
    tab.setAttribute("aria-expanded", "true");
    readAndSend(adapter.mostVisiblePost());
  }

  function close() {
    document.documentElement.classList.remove("draftvoice-open");
    tab.setAttribute("aria-expanded", "false");
    outline(null);
    stopPicking();
  }

  function stopPicking() {
    picking = false;
    document.documentElement.classList.remove("draftvoice-picking");
  }

  tab.addEventListener("click", () =>
    document.documentElement.classList.contains("draftvoice-open") ? close() : open());

  // "Not this post?": the founder's next click on a post selects it instead (and does nothing else).
  document.addEventListener("click", (e) => {
    if (!picking || e.target === tab || drawer?.contains(e.target)) return;
    const el = adapter.postAt(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    stopPicking();
    readAndSend(el);
  }, true);

  window.addEventListener("message", (e) => {
    if (!frame || e.source !== frame.contentWindow || e.origin !== PANEL_ORIGIN) return;
    const m = e.data || {};
    if (m.type === "draftvoice:ready") {
      ready = true;
      queued.forEach((q) => frame.contentWindow.postMessage(q, PANEL_ORIGIN));
      queued = [];
    } else if (m.type === "draftvoice:close") {
      close();
    } else if (m.type === "draftvoice:pick") {
      picking = true;
      document.documentElement.classList.add("draftvoice-picking");
    }
  });
})();
