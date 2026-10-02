"""Static guarantees for the browser extension: the scope Fathin approved, enforced in the code."""

import json
import re

from draftvoice.store import ROOT

EXT = ROOT / "extension"
MANIFEST = json.loads((EXT / "manifest.json").read_text())
CONTENT = (EXT / "content.js").read_text()
ADAPTER = (EXT / "linkedin_adapter.js").read_text()
PANEL = (EXT / "panel.js").read_text()


def strip_comments(js: str) -> str:
    return re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", "", js, flags=re.S))


def test_host_access_is_linkedin_and_localhost_only():
    assert MANIFEST["manifest_version"] == 3
    assert MANIFEST["host_permissions"] == ["https://www.linkedin.com/*", "http://127.0.0.1:8765/*"]
    assert MANIFEST["permissions"] == ["clipboardWrite"]  # no storage, tabs, scripting, or cookies
    (script,) = MANIFEST["content_scripts"]
    assert script["matches"] == ["https://www.linkedin.com/*"]
    assert script["js"] == ["linkedin_adapter.js", "content.js"]


def test_only_the_adapter_knows_linkedin_markup():
    linkedin_markup = re.compile(r"feed-shared|update-components|urn:li")
    assert linkedin_markup.search(ADAPTER)
    assert not linkedin_markup.search(strip_comments(CONTENT))
    assert not linkedin_markup.search(strip_comments(PANEL))


def test_content_script_never_scrolls_watches_stores_types_or_posts():
    code = strip_comments(CONTENT + ADAPTER)
    forbidden = {
        "scrolling": r"scrollTo|scrollBy|scrollIntoView|scrollTop\s*=",
        "background reading": r"MutationObserver|setInterval|IntersectionObserver",
        "storing": r"localStorage|sessionStorage|indexedDB|chrome\.storage|document\.cookie",
        "typing": r"\.value\s*=|execCommand|insertText|dispatchEvent|contentEditable|\.innerText\s*=",
        "network": r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket",
        "submitting": r"\.submit\(|\.click\(\)",
    }
    for what, pattern in forbidden.items():
        assert not re.search(pattern, code), what


def test_nothing_runs_before_the_tab_is_clicked():
    # At load the script only creates the tab and listeners. Reading happens in choose(), which only
    # open() (the tab), the panel's method switch, and a click while picking can reach.
    top_level = CONTENT.split("function send(")[0]
    assert "readPost" not in top_level and "mostVisiblePost" not in top_level and "getSelection" not in top_level
    assert re.search(r"function open\(\) \{[^}]*choose\(\);", CONTENT)
    # Highlighted text is read only when the tab is pressed.
    (line,) = re.findall(r".*getSelection.*", CONTENT)
    handler = CONTENT[CONTENT.index('tab.addEventListener("mousedown"'):CONTENT.index('tab.addEventListener("click"')]
    assert line.strip() in handler
    # Hover and click handlers do nothing unless the founder started picking.
    assert CONTENT.count("if (!picking") == 2


def test_auto_tries_the_methods_in_the_agreed_order():
    assert "if (byPage(false) || bySelection(false) || byVisible(false)) return;\n    byClick();" in CONTENT
    panel = (EXT / "panel.html").read_text()
    for value in ("auto", "page", "click", "select", "visible"):
        assert f'value="{value}"' in panel


def test_panel_messages_never_hand_the_comment_to_linkedin():
    assert 'IN_EXTENSION = location.protocol === "chrome-extension:"' in PANEL
    assert "approved && !IN_EXTENSION ? text : null" in PANEL
    assert "e.source !== window.parent" in PANEL
    assert "e.origin !== PANEL_ORIGIN" in CONTENT


def test_panel_files_are_shared_with_the_mock_feed():
    from draftvoice.api import STATIC
    for name in ("panel.html", "panel.css", "panel.js"):
        folder, _ = STATIC[name]
        assert folder == EXT and (EXT / name).exists()
        assert name in MANIFEST["web_accessible_resources"][0]["resources"]


def test_scroll_only_offers_a_button_and_reads_nothing():
    # The scroll listener does nothing unless the sidebar is open, and only positions "Draft this post".
    listener = CONTENT[CONTENT.index('window.addEventListener("scroll"'):]
    listener = listener[:listener.index("}, { passive: true });")]
    assert 'if (!root.classList.contains("draftvoice-open")' in listener
    update = CONTENT[CONTENT.index("function updateHint()"):CONTENT.index('window.addEventListener("scroll"')]
    before_click = update[:update.index('hint.addEventListener("click"')] + update[update.index("hintFor = el;"):]
    assert "readPost" not in before_click and "useElement" not in before_click and "send(" not in before_click
    # Reading happens only inside the button's click handler.
    assert 'useElement(target, "Couldn\'t read this post. Try another one.")' in update
