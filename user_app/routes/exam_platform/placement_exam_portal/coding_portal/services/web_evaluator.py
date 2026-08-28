"""
Web section grading.

Assertions run against the composed HTML document. Parsing is done with the
stdlib HTMLParser so the platform needs no extra dependency; assertions cover
structure, text, attributes and simple CSS-property checks.
"""
import re
import logging
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}


class _Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []
        self.text_parts = []

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    def text(self):
        out = list(self.text_parts)
        for child in self.children:
            out.append(child.text())
        return " ".join(p for p in out if p).strip()

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class _DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {})
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID_ELEMENTS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(_Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data):
        if data.strip():
            self.current.text_parts.append(data.strip())


def parse_dom(html: str) -> _Node:
    builder = _DomBuilder()
    builder.feed(html or "")
    builder.close()
    return builder.root


# --- selector support: tag, .class, #id, and simple descendant chains ---

def _matches_simple(node, token):
    if token.startswith("#"):
        return node.attrs.get("id") == token[1:]
    if token.startswith("."):
        return token[1:] in node.classes
    if "." in token:
        tag, _, cls = token.partition(".")
        return node.tag == tag and cls in node.classes
    if "#" in token:
        tag, _, ident = token.partition("#")
        return node.tag == tag and node.attrs.get("id") == ident
    return node.tag == token.lower()


def select(root, selector: str):
    """Return nodes matching a descendant selector chain ('div .item')."""
    tokens = [t for t in re.split(r"\s+", selector.strip()) if t]
    if not tokens:
        return []

    matches = [n for n in root.walk() if _matches_simple(n, tokens[0])]
    for token in tokens[1:]:
        next_matches = []
        for m in matches:
            for desc in m.walk():
                if desc is not m and _matches_simple(desc, token):
                    next_matches.append(desc)
        matches = next_matches
    return matches


# --- CSS: flat declaration lookup, last rule wins ---

def parse_css_rules(css: str):
    rules = []
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.DOTALL)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [s.strip() for s in match.group(1).split(",") if s.strip()]
        decls = {}
        for decl in match.group(2).split(";"):
            if ":" in decl:
                prop, _, value = decl.partition(":")
                decls[prop.strip().lower()] = value.strip().rstrip("!important").strip()
        for sel in selectors:
            rules.append((sel, decls))
    return rules


def css_property_for(root, css_rules, selector, prop):
    """
    Resolve a property for the first node matching `selector`.

    Inline styles win, then the last matching rule -- a deliberate
    simplification of the cascade (no specificity ordering).
    """
    nodes = select(root, selector)
    if not nodes:
        return None
    node = nodes[0]

    inline = node.attrs.get("style") or ""
    for decl in inline.split(";"):
        if ":" in decl:
            p, _, v = decl.partition(":")
            if p.strip().lower() == prop.lower():
                return v.strip()

    found = None
    for sel, decls in css_rules:
        if select(root, sel) and node in select(root, sel):
            if prop.lower() in decls:
                found = decls[prop.lower()]
    return found


def _norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def evaluate(html_code, css_code, js_code, assertions):
    """
    Run assertions against the candidate's document.

    Returns (results, passed, total). Each result carries status and a message.
    """
    root = parse_dom(html_code)
    css_rules = parse_css_rules(css_code)
    results = []

    for a in assertions:
        kind = a.get("kind")
        selector = a.get("selector") or ""
        expected = a.get("expected_value")
        prop = a.get("property_name")
        label = a.get("message") or f"{kind} {selector}"

        try:
            nodes = select(root, selector)

            if kind == "element_exists":
                ok = len(nodes) > 0
                detail = "" if ok else f"No element matches '{selector}'."

            elif kind == "count_equals":
                ok = len(nodes) == int(expected or 0)
                detail = "" if ok else f"Expected {expected}, found {len(nodes)}."

            elif kind == "text_equals":
                actual = nodes[0].text() if nodes else None
                ok = actual is not None and _norm(actual) == _norm(expected)
                detail = "" if ok else f"Expected text '{expected}', got '{actual}'."

            elif kind == "text_contains":
                actual = nodes[0].text() if nodes else None
                ok = actual is not None and _norm(expected) in _norm(actual)
                detail = "" if ok else f"Text '{actual}' does not contain '{expected}'."

            elif kind == "attr_equals":
                actual = nodes[0].attrs.get(prop) if nodes else None
                ok = actual is not None and _norm(actual) == _norm(expected)
                detail = "" if ok else f"Expected {prop}='{expected}', got '{actual}'."

            elif kind == "css_property":
                actual = css_property_for(root, css_rules, selector, prop)
                ok = actual is not None and _norm(actual) == _norm(expected)
                detail = "" if ok else f"Expected {prop}: {expected}, got {actual}."

            else:
                ok, detail = False, f"Unknown assertion type '{kind}'."

        except Exception as e:
            logger.exception("Assertion failed to evaluate")
            ok, detail = False, f"Assertion error: {e}"

        results.append({
            "message": label,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
            "is_hidden": bool(a.get("is_hidden")),
        })

    passed = sum(1 for r in results if r["status"] == "PASS")
    return results, passed, len(results)


def compose_document(html_code, css_code, js_code):
    """Build the srcdoc for the live preview iframe."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{css_code or ''}</style></head><body>"
        f"{html_code or ''}"
        f"<script>{js_code or ''}<\\/script>"
        "</body></html>"
    )
