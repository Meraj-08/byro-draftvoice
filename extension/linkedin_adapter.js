// Everything that knows LinkedIn's page structure lives here, so a LinkedIn redesign touches one file.
// It only reads, and only when content.js asks: after the founder clicks the DraftVoice tab or a post.
(() => {
  "use strict";

  // Tried in order; LinkedIn renames classes from time to time.
  const POST = [
    "div.feed-shared-update-v2",
    "div[data-urn^='urn:li:activity']",
    "div[data-id^='urn:li:activity']",
    "article",
  ];
  const AUTHOR = [
    ".update-components-actor__title span[aria-hidden='true']",
    ".update-components-actor__name span[aria-hidden='true']",
    ".update-components-actor__title",
    ".feed-shared-actor__name",
  ];
  const HEADLINE = [
    ".update-components-actor__description span[aria-hidden='true']",
    ".update-components-actor__description",
    ".feed-shared-actor__description",
  ];
  const TEXT = [
    ".update-components-text",
    ".feed-shared-inline-show-more-text",
    ".feed-shared-update-v2__description",
    ".feed-shared-text",
  ];

  const clean = (s) => (s || "").replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();

  function first(root, selectors) {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      if (el && clean(el.innerText)) return clean(el.innerText);
    }
    return "";
  }

  function posts() {
    for (const sel of POST) {
      const found = [...document.querySelectorAll(sel)].filter((el) => !el.parentElement?.closest(sel));
      if (found.length) return found;
    }
    return [];
  }

  // The post with the largest visible area on screen.
  function mostVisiblePost() {
    let best = null;
    let bestArea = 0;
    for (const el of posts()) {
      const r = el.getBoundingClientRect();
      const visible = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
      const area = visible * Math.max(0, r.width);
      if (area > bestArea) { bestArea = area; best = el; }
    }
    return best;
  }

  // The post that contains a clicked element, if any.
  function postAt(target) {
    for (const sel of POST) {
      const el = target.closest?.(sel);
      if (el) return el;
    }
    return null;
  }

  // {author, headline, text}, or null when the text cannot be found.
  // Text cut off by LinkedIn's "...see more" is read as shown; DraftVoice does not click anything.
  function readPost(el) {
    if (!el) return null;
    const text = first(el, TEXT).replace(/(…|\.\.\.)\s*see more$/i, "").trim();
    if (!text) return null;
    return { author: first(el, AUTHOR).split("\n")[0], headline: first(el, HEADLINE).split("\n")[0], text };
  }

  window.DraftVoiceLinkedIn = { posts, mostVisiblePost, postAt, readPost };
})();
