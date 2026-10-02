// DraftVoice review panel. Shared by the mock feed and the browser extension.
//
// It gets a post in one of two ways:
//   - window.postMessage({type: "draftvoice:post", post: {author, headline, text}, pickable}) from the page
//     that embeds it (the mock feed, or the extension's LinkedIn drawer);
//   - URL parameters (?author=&headline=&text=) when opened on its own.
// It only shows what the local API returns. The steps are the API's real results, played back one by one.

(() => {
  "use strict";

  const API = /^https?:$/.test(location.protocol) && /^(127\.0\.0\.1|localhost)$/.test(location.hostname)
    ? "" : "http://127.0.0.1:8765";
  const STEP_DELAY = 160; // ms between revealing each real step result
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const ICON = {
    done: '<svg viewBox="0 0 10 10"><path d="M2 5.2l2 2L8 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    stopped: '<svg viewBox="0 0 10 10"><path d="M3 3l4 4M7 3L3 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  };

  const state = { founders: [], founder: null, post: null, proposal: null, editing: false, reviewed: false, run: 0 };

  // ---------- helpers ----------

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (_) { /* storage can be unavailable; the panel works without it */ }
    return null;
  }

  async function api(path, body) {
    const res = await fetch(API + path, body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `DraftVoice returned ${res.status}`);
    return data;
  }

  function toast(text) {
    const el = $("toast");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.append(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  // Inside the extension the parent is LinkedIn's page, so messages to it never carry the comment text.
  const IN_EXTENSION = location.protocol === "chrome-extension:";
  const tell = (message) => { if (window.parent !== window) window.parent.postMessage(message, "*"); };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---------- founders ----------

  function renderFounders() {
    $("founders").innerHTML = state.founders.map((f) =>
      `<button role="radio" aria-checked="${f.id === state.founder}" data-id="${esc(f.id)}">${esc(f.name)}</button>`).join("");
  }

  $("founders").addEventListener("click", (e) => {
    const id = e.target.closest("button")?.dataset.id;
    if (!id || id === state.founder) return;
    state.founder = id;
    store("draftvoice.founder", id);
    renderFounders();
    if (state.post) propose();
  });

  // ---------- post ----------

  function showPost(post, pickable) {
    state.post = post;
    $("empty").hidden = true;
    $("post").hidden = false;
    const name = post.author || "Unknown author";
    $("avatar").textContent = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    $("author").textContent = name;
    $("headline").textContent = post.headline || "";
    $("postText").textContent = post.text;
    $("postText").classList.add("clamp");
    $("pick").hidden = !pickable;
    requestAnimationFrame(() => {
      const el = $("postText");
      $("more").hidden = el.scrollHeight <= el.clientHeight + 1;
      $("more").textContent = "Show more";
    });
  }

  $("more").addEventListener("click", () => {
    const clamped = $("postText").classList.toggle("clamp");
    $("more").textContent = clamped ? "Show more" : "Show less";
  });
  $("pick").addEventListener("click", () => tell({ type: "draftvoice:pick" }));
  $("pickAgain").addEventListener("click", () => tell({ type: "draftvoice:pick" }));
  $("close").addEventListener("click", () => tell({ type: "draftvoice:close" }));
  $("refresh").addEventListener("click", () => tell({ type: "draftvoice:refresh" }));

  function showMessage(text) {
    state.post = null;
    $("post").hidden = $("stepsCard").hidden = $("result").hidden = $("actions").hidden = true;
    $("empty").hidden = false;
    $("emptyText").textContent = text;
    $("pickAgain").hidden = window.parent === window;
  }

  // ---------- run ----------

  function stepRow(step, status) {
    return `<li class="step ${status}">
      <span class="mark ${status}">${ICON[status] || ""}</span>
      <div><div class="title">${esc(step.label)}</div>${step.detail && status !== "running"
        ? `<div class="detail">${esc(step.detail)}</div>` : ""}</div></li>`;
  }

  function loading() {
    $("stepsCard").hidden = false;
    $("steps").innerHTML = stepRow({ label: "Reading the post" }, "running");
    $("result").hidden = false;
    $("result").innerHTML = '<div class="skeleton"><div></div><div></div><div></div></div>';
    $("actions").hidden = true;
  }

  async function propose(override = false) {
    if (!state.post || !state.founder) return;
    const run = ++state.run;
    state.proposal = null;
    state.editing = false;
    state.edited = null;
    state.reviewed = false;
    loading();
    let p;
    try {
      p = await api("/api/propose", {
        founder: state.founder, text: state.post.text, author: state.post.author,
        headline: state.post.headline, drafter: $("live").checked ? "gemini" : "stub", override,
      });
    } catch (err) {
      if (run !== state.run) return;
      $("stepsCard").hidden = true;
      $("result").innerHTML = `<div class="reason">Could not reach DraftVoice. Is it running? (${esc(err.message)})</div>`;
      return;
    }
    if (run !== state.run) return; // a newer run started; drop this one
    // Play back the real steps, one at a time.
    const rows = [];
    for (const step of p.steps) {
      rows.push(stepRow(step, step.status === "not_reached" ? "not_reached" : "running"));
      $("steps").innerHTML = rows.join("");
      if (step.status !== "not_reached") {
        await sleep(STEP_DELAY);
        if (run !== state.run) return;
        rows[rows.length - 1] = stepRow(step, step.status);
        $("steps").innerHTML = rows.join("");
      }
    }
    state.proposal = p;
    renderResult();
  }

  // ---------- result ----------

  function renderResult() {
    const p = state.proposal;
    const box = $("result");
    box.hidden = false;
    if (p.decision !== "draft") {
      const blocked = p.reason_code === "check_failed";
      const fails = p.checks.filter((c) => !c.passed)
        .map((c) => `<div>${esc(c.check)}: ${esc(c.detail)}</div>`).join("");
      box.innerHTML = `
        <div class="verdict"><span class="badge ${blocked ? "blocked" : "nothing"}">${blocked ? "Blocked" : "Do nothing"}</span>
          <span class="meta">${esc(p.founder.name)} · profile v${p.founder.version}</span></div>
        <div class="reason">${esc(p.reason)}</div>
        ${fails ? `<div class="fail">${fails}</div>` : ""}
        <div class="row">
          ${p.can_override ? '<button class="btn" data-act="anyway">Draft anyway</button>' : ""}
          <button class="btn ghost" data-act="skip">OK, skip</button>
        </div>`;
      $("actions").hidden = true;
      return;
    }
    const evidence = Object.fromEntries(p.evidence.map((e) => [e.id, e]));
    const sentences = p.sentences.map((s) => `<span class="sentence">${esc(s.text)}</span>${s.evidence_ids.map((id) =>
      `<span class="chip" tabindex="0" data-tip="${esc((evidence[id]?.text || "") + " (" + (evidence[id]?.source || "") + ")")}">${esc(id)}</span>`
    ).join("")}`).join(" ");
    const edited = state.edited != null && state.edited.trim() !== p.draft.trim();
    const notes = p.warnings.map((w) => `<div class="note">${esc(w.detail)}. Your call.</div>`).join("");
    box.innerHTML = `
      <div class="verdict"><span class="badge draft">Comment</span>
        <span class="meta">${esc(p.founder.name)} · profile v${p.founder.version}</span></div>
      <div id="draftBody">${state.editing
        ? `<textarea class="editor" id="editor" aria-label="Edit the draft">${esc(state.edited ?? p.draft)}</textarea>`
        : edited
          ? `<div class="draft-text">${esc(state.edited)}</div><div class="meta">Your edit. The checks ran on the original draft.</div>`
          : `<div class="draft-text">${sentences}</div>`}</div>
      ${notes ? `<div class="notes">${notes}</div>` : ""}`;
    $("actions").hidden = state.reviewed;
    $("edit").innerHTML = state.editing ? "Done" : $("edit").dataset.label;
  }

  $("result").addEventListener("click", async (e) => {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "anyway") propose(true);
    if (act === "skip") review("skip");
    if (act === "apply" || act === "ignore") {
      const id = e.target.closest("[data-rule]").dataset.rule;
      try {
        const r = await api(`/api/rules/${act === "apply" ? "approve" : "reject"}`, { id });
        e.target.closest(".suggest").innerHTML = act === "apply"
          ? `Applied. ${esc(state.founder)} is now on profile v${r.version}.` : "Ignored. Nothing changed.";
        if (act === "apply") loadFounders();
      } catch (err) { toast(err.message); }
    }
  });

  $("edit").dataset.label = $("edit").innerHTML;
  $("edit").addEventListener("click", () => {
    if (!state.proposal) return;
    if (state.editing) state.edited = $("editor").value;
    else state.edited = state.edited ?? state.proposal.draft;
    state.editing = !state.editing;
    renderResult();
    if (state.editing) $("editor").focus();
  });

  $("approve").addEventListener("click", async () => {
    const p = state.proposal;
    if (!p) return;
    const text = (state.editing ? $("editor").value : state.edited ?? p.draft).trim();
    const action = text === p.draft.trim() ? "accept" : "edit";
    if (!text) return toast("The comment is empty.");
    await review(action, text);
    if (await copy(text)) toast("Copied. Paste it and post it yourself.");
    else toast("Could not copy. Select the text and copy it yourself.");
  });
  $("skip").addEventListener("click", () => review("skip"));
  $("reject").addEventListener("click", () => review("reject"));

  async function review(action, text) {
    const p = state.proposal;
    if (!p || state.reviewed) return;
    try {
      const r = await api("/api/review", { proposal_id: p.id, action, edited_text: action === "edit" ? text : null });
      state.reviewed = true;
      state.editing = false;
      if (action === "edit") state.edited = text;
      const msg = { accept: "Approved as drafted.", edit: "Approved with your edit.", skip: "Skipped.", reject: "Rejected." }[action];
      renderResult();
      $("actions").hidden = true;
      const done = document.createElement("div");
      done.className = "done-msg";
      done.textContent = msg;
      $("result").append(done);
      if (r.suggestion) {
        const s = document.createElement("div");
        s.className = "suggest";
        s.dataset.rule = r.suggestion.id;
        s.innerHTML = `<div><strong>You made this change twice.</strong> Suggested voice rule: ${esc(r.suggestion.rule)}</div>
          <div class="row"><button class="btn primary" data-act="apply">Apply rule</button><button class="btn" data-act="ignore">Ignore</button></div>`;
        $("result").append(s);
      }
      const approved = action === "accept" || action === "edit";
      tell({ type: "draftvoice:reviewed", action, text: approved && !IN_EXTENSION ? text : null });
    } catch (err) {
      toast(err.message);
    }
  }

  // ---------- incoming posts ----------

  window.addEventListener("message", (e) => {
    if (e.source !== window.parent) return; // only the page that embeds the panel may hand it a post
    const m = e.data || {};
    if (m.type === "draftvoice:post" && m.post?.text) {
      showPost(m.post, !!m.pickable);
      propose();
    } else if (m.type === "draftvoice:reading") {
      $("empty").hidden = true;
      loading();
    } else if (m.type === "draftvoice:error") {
      showMessage(m.message || "Couldn't read this post. Try scrolling it into view.");
    } else if (m.type === "draftvoice:host" && m.methods) {
      $("methodRow").hidden = false;
      if (m.method) $("method").value = m.method;
    } else if (m.type === "draftvoice:prompt") {
      showMessage(m.message);
      $("pickAgain").hidden = true; // already waiting for a click on a post
    }
  });

  async function loadFounders() {
    state.founders = (await api("/api/founders")).founders;
    const saved = store("draftvoice.founder");
    if (!state.founder) state.founder = state.founders.some((f) => f.id === saved) ? saved : state.founders[0]?.id;
    renderFounders();
  }

  // On LinkedIn the content script says so, and the founder can choose how the post is picked.
  $("method").addEventListener("change", () => tell({ type: "draftvoice:method", method: $("method").value }));

  $("live").checked = store("draftvoice.live") === "1";
  $("live").addEventListener("change", () => store("draftvoice.live", $("live").checked ? "1" : "0"));

  (async () => {
    try {
      await loadFounders();
    } catch (err) {
      showMessage("DraftVoice isn't running. Start it with: draftvoice serve");
      return;
    }
    const q = new URLSearchParams(location.search);
    if (q.get("text")) {
      showPost({ author: q.get("author"), headline: q.get("headline"), text: q.get("text") }, false);
      propose();
    }
    $("refresh").hidden = window.parent === window; // only when a page embeds the panel
    tell({ type: "draftvoice:ready" });
  })();
})();
