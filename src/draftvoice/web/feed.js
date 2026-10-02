// Mock feed: opens the shared review panel as a drawer and hands it the one post you are looking at.
// It behaves like the LinkedIn extension: nothing runs until the tab is clicked.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const panel = $("panel");
  let posts = [];
  let selected = null;
  let panelReady = false;
  let pending = null;

  const send = (message) => {
    if (panelReady) panel.contentWindow.postMessage(message, location.origin);
    else pending = message;
  };

  function render(feed) {
    posts = feed.posts;
    $("feed").innerHTML = "";
    for (const p of posts) {
      const el = document.createElement("article");
      el.className = "post";
      el.dataset.id = p.id;
      const initials = p.author.split(/\s+/).map((w) => w[0]).slice(0, 2).join("");
      el.innerHTML = `
        <div class="post-head"><div class="avatar"></div>
          <div><div class="author"></div><div class="headline"></div></div></div>
        <div class="text"></div>
        <span class="tag ${p.kind === "real" ? "real" : "synthetic"}"></span>`;
      el.querySelector(".avatar").textContent = initials;
      el.querySelector(".author").textContent = p.author;
      el.querySelector(".headline").textContent = `${p.headline} · ${p.time}`;
      el.querySelector(".text").textContent = p.text;
      el.querySelector(".tag").textContent = p.tag;
      $("feed").append(el);
    }
  }

  // The post with the largest visible area in the viewport.
  function mostVisible() {
    let best = null;
    let bestArea = 0;
    for (const el of document.querySelectorAll(".post")) {
      const r = el.getBoundingClientRect();
      const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
      if (h * r.width > bestArea) { bestArea = h * r.width; best = el; }
    }
    return best;
  }

  function select(el) {
    document.querySelectorAll(".post.selected").forEach((p) => p.classList.remove("selected"));
    selected = el;
    el.classList.add("selected");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const p = posts.find((x) => x.id === el.dataset.id);
    send({ type: "draftvoice:post", post: { author: p.author, headline: p.headline, text: p.text }, pickable: true });
  }

  function open() {
    document.body.classList.add("open");
    $("drawer").setAttribute("aria-hidden", "false");
    $("edgeTab").setAttribute("aria-expanded", "true");
    const el = mostVisible();
    if (el) {
      send({ type: "draftvoice:reading" });
      select(el);
    }
  }

  function close() {
    document.body.classList.remove("open");
    $("drawer").setAttribute("aria-hidden", "true");
    $("edgeTab").setAttribute("aria-expanded", "false");
    document.querySelectorAll(".post.selected").forEach((p) => p.classList.remove("selected"));
    stopPicking();
  }

  function startPicking() {
    document.body.classList.add("picking");
    $("pickBanner").hidden = false;
  }

  function stopPicking() {
    document.body.classList.remove("picking");
    $("pickBanner").hidden = true;
  }

  $("edgeTab").addEventListener("click", () => (document.body.classList.contains("open") ? close() : open()));
  $("pickCancel").addEventListener("click", stopPicking);
  $("feed").addEventListener("click", (e) => {
    if (!document.body.classList.contains("picking")) return;
    const el = e.target.closest(".post");
    if (!el) return;
    stopPicking();
    send({ type: "draftvoice:reading" });
    select(el);
  });

  window.addEventListener("message", (e) => {
    if (e.source !== panel.contentWindow) return;
    const m = e.data || {};
    if (m.type === "draftvoice:ready") {
      panelReady = true;
      if (pending) { panel.contentWindow.postMessage(pending, location.origin); pending = null; }
    } else if (m.type === "draftvoice:close") {
      close();
    } else if (m.type === "draftvoice:pick") {
      startPicking();
    } else if (m.type === "draftvoice:reviewed" && m.text && selected) {
      // In LinkedIn you would paste it yourself. Here we only show where it would go.
      selected.querySelector(".comment")?.remove();
      const c = document.createElement("div");
      c.className = "comment";
      c.textContent = m.text;
      const note = document.createElement("small");
      note.textContent = "Copied to your clipboard. On LinkedIn you would paste it here yourself.";
      c.append(note);
      selected.append(c);
    }
  });

  fetch("/api/feed").then((r) => r.json()).then(render)
    .catch(() => { $("feed").textContent = "Could not load the feed. Is DraftVoice running?"; });
})();
