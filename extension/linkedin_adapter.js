// Everything that knows LinkedIn's page lives here, so a LinkedIn redesign touches one file.
// It only reads, and only when content.js asks: after the founder clicks the DraftVoice tab or a post.
//
// Two ways to find a post:
//   1. Known LinkedIn class names (fast, but LinkedIn renames them).
//   2. Structure: the nearest block that has an author link (/in/ or /company/) and a Like button.
//      This does not depend on class names.
// Saved posts (/my-items/saved-posts/) are a list of results, not feed posts: no Like button, but each
// item links to the post. So the structure fallback also accepts an author link plus a link to a post.
(() => {
  "use strict";

  const POST = [
    "div.feed-shared-update-v2",
    "div[data-urn^='urn:li:activity']",
    "div[data-id^='urn:li:activity']",
    "[data-view-name='feed-full-update']",
    // Saved posts and other result lists
    "[data-chameleon-result-urn^='urn:li:activity']",
    "li.reusable-search__result-container",
    "div.entity-result",
  ];
  const AUTHOR = [
    ".update-components-actor__title span[aria-hidden='true']",
    ".update-components-actor__name span[aria-hidden='true']",
    ".update-components-actor__title",
    ".entity-result__title-text a span[aria-hidden='true']",
    ".entity-result__title-text a",
  ];
  const HEADLINE = [
    ".update-components-actor__description span[aria-hidden='true']",
    ".update-components-actor__description",
    ".entity-result__primary-subtitle",
  ];
  const TEXT = [
    ".update-components-text",
    ".feed-shared-inline-show-more-text",
    ".feed-shared-update-v2__description",
    ".entity-result__content-summary",
    ".entity-result__summary",
  ];
  const AUTHOR_LINK = "a[href*='/in/'], a[href*='/company/']";
  const LIKE = "button[aria-label*='Like' i], button[aria-label*='React' i]";
  const POST_LINK = "a[href*='/feed/update/'], a[href*='/posts/']";
  const SINGLE_POST_PATH = /^\/(feed\/update|posts)\//;

  const clean = (s) => (s || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const firstLine = (s) => clean(s).split("\n").map((l) => l.trim()).find(Boolean) || "";

  function first(root, selectors) {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (el && clean(el.innerText)) return clean(el.innerText);
    }
    return "";
  }

  // Structure-based: from any element, walk up to the smallest block with an author link and a Like button.
  function containerFrom(el) {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (n.querySelector?.(AUTHOR_LINK) && n.querySelector(LIKE) && clean(n.innerText).length > 40) return n;
    }
    return null;
  }

  // Saved posts: from a link to a post, walk up to the smallest block with an author link and real text.
  // Text is required so the block is the whole item, not just its header.
  function savedContainerFrom(el) {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (n.querySelector?.(AUTHOR_LINK) && longestText(n).length >= 40) return n;
    }
    return null;
  }

  function innermost(found) {
    return [...found].filter((c) => ![...found].some((o) => o !== c && c.contains(o)));
  }

  function posts() {
    for (const sel of POST) {
      const found = [...document.querySelectorAll(sel)].filter((el) => !el.parentElement?.closest(sel));
      if (found.length) return found;
    }
    // Structure fallback: one container per Like button, outermost duplicates removed.
    const seen = new Set();
    for (const like of document.querySelectorAll(LIKE)) {
      const c = containerFrom(like);
      if (c) seen.add(c);
    }
    if (seen.size) return innermost(seen);
    // No Like buttons, as on saved posts: one container per post link.
    for (const link of document.querySelectorAll(POST_LINK)) {
      const c = savedContainerFrom(link);
      if (c) seen.add(c);
    }
    return innermost(seen);
  }

  function visibleArea(el) {
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)) * Math.max(0, r.width);
  }

  // A: the post with the largest visible area on screen.
  function mostVisiblePost() {
    let best = null;
    for (const el of posts()) if (visibleArea(el) > (best ? visibleArea(best) : 0)) best = el;
    return best;
  }

  // B: the post that contains a clicked element.
  function postAt(target) {
    for (const sel of POST) {
      const el = target.closest?.(sel);
      if (el) return el;
    }
    return containerFrom(target) || posts().find((p) => p.contains(target)) || null;
  }

  // D: on a single post page there is one main post.
  function isSinglePostPage() {
    return SINGLE_POST_PATH.test(location.pathname);
  }

  function singlePagePost() {
    const all = posts();
    return all.find((el) => visibleArea(el) > 0) || all[0] || null;
  }

  // The longest block of text in the post that is not a link or a button.
  function longestText(el) {
    let best = "";
    for (const n of el.querySelectorAll("span[dir='ltr'], p, div, span")) {
      if (n.closest("button, a, [role='button']")) continue;
      const t = clean(n.innerText);
      if (t.length <= best.length || t.length > 5000) continue;
      // Skip wrappers whose text is mostly one child's text; that child will be considered on its own.
      if ([...n.children].some((c) => clean(c.innerText).length > t.length * 0.9)) continue;
      best = t;
    }
    return best;
  }

  // The author's name. The first profile link is often the photo, which has no text, so try each link,
  // then the "View <name>'s profile" label LinkedIn puts on them.
  function authorOf(el) {
    const named = firstLine(first(el, AUTHOR));
    if (named) return named;
    const links = [...el.querySelectorAll(AUTHOR_LINK)];
    for (const a of links) {
      const name = firstLine(a.innerText);
      if (name && !/^(•|·|\d+(st|nd|rd|th)\b|follow)/i.test(name)) return name;
    }
    for (const a of links) {
      const m = (a.getAttribute("aria-label") || "").match(/^view\s+(.+?)[’']s\b/i);
      if (m) return m[1].trim();
    }
    return "";
  }

  // {author, headline} of the post that contains a node, e.g. highlighted text.
  function describe(node) {
    const el = node && postAt(node.nodeType === 1 ? node : node.parentElement);
    return el ? { author: authorOf(el), headline: firstLine(first(el, HEADLINE)), element: el } : null;
  }

  // {author, headline, text}, or null when no text can be found.
  // Text cut off by LinkedIn's "...see more" is read as shown; DraftVoice does not click anything.
  function readPost(el) {
    if (!el) return null;
    let text = first(el, TEXT) || longestText(el);
    text = text.replace(/(…|\.\.\.)\s*see more$/i, "").trim();
    if (text.length < 20) return null;
    return { author: authorOf(el), headline: firstLine(first(el, HEADLINE)), text };
  }

  window.DraftVoiceLinkedIn = { posts, mostVisiblePost, postAt, isSinglePostPage, singlePagePost, readPost, describe };
})();
