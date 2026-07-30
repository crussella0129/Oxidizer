"""HTML -> Markdown extraction for the Rust canon.

Stdlib only, on purpose. Oxidizer is meant to be agent-agnostic and drop-in;
requiring a pip install before the corpus can be built would undercut that.

Two page shapes matter:

* mdBook  (The Book, Rust By Example, the Reference, the Nomicon, the Cargo
  book, the edition guide, the style guide, the error index) puts the prose in
  ``<main>``.
* rustdoc (std, core, alloc) puts it in ``<section id="main-content">`` and
  encodes each item's signature in ``<section id="method.foo">`` anchors.

Both reduce to the same markdown emitter below.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# Tags whose entire subtree is noise for our purposes.
_DROP = {"script", "style", "svg", "nav", "head", "button", "rustdoc-toolbar",
         "noscript", "form", "template"}

_BLOCK = {"p", "div", "section", "article", "main", "header", "footer",
          "blockquote", "details", "summary", "tr", "figure", "figcaption"}

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _Converter(HTMLParser):
    """Streaming HTML -> Markdown converter.

    Deliberately forgiving: rustdoc output is machine-generated and well formed,
    but the error index embeds hand-written HTML that is not always balanced.
    Anything unrecognised degrades to its text content rather than raising.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self._drop_depth = 0
        self._pre_depth = 0
        self._heading: int | None = None
        self._heading_buf: list[str] = []
        self._list_stack: list[dict] = []
        self._code_lang = ""
        self._in_code = False

    # -- helpers -----------------------------------------------------------
    def _emit(self, text: str) -> None:
        if self._heading is not None:
            self._heading_buf.append(text)
        else:
            self.out.append(text)

    def _newline(self, count: int = 1) -> None:
        if self._pre_depth:
            return
        # Collapse: never stack more blank lines than asked for.
        while self.out and self.out[-1] == "\n":
            self.out.pop()
            count = max(count, 1)
        if self.out:
            self.out.append("\n" * count)

    # -- parser callbacks --------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = dict(attrs_list)
        if self._drop_depth:
            if tag in _DROP:
                self._drop_depth += 1
            return
        if tag in _DROP:
            self._drop_depth = 1
            return

        cls = attrs.get("class", "") or ""
        # rustdoc sidebars, mdBook chrome, "copy to clipboard" affordances.
        if any(k in cls for k in ("sidebar", "nav-", "mobile-topbar", "toggle-",
                                 "help-button", "search-form", "out-of-band")):
            self._drop_depth = 1
            return

        if tag in _HEADINGS:
            self._newline(2)
            self._heading = _HEADINGS[tag]
            self._heading_buf = []
        elif tag == "pre":
            self._newline(2)
            self._pre_depth += 1
            self.out.append("```" + self._code_lang + "\n")
        elif tag == "code":
            if self._pre_depth:
                # Language hint lives on the inner <code class="language-rust ...">.
                m = re.search(r"language-(\w+)", cls)
                if m and self.out and self.out[-1].startswith("```"):
                    self.out[-1] = "```" + m.group(1) + "\n"
                self._in_code = True
            else:
                self._emit("`")
        elif tag in ("ul", "ol"):
            self._newline(1)
            self._list_stack.append({"ordered": tag == "ol", "n": 0})
        elif tag == "li":
            self._newline(1)
            if self._list_stack:
                lvl = self._list_stack[-1]
                lvl["n"] += 1
                indent = "  " * (len(self._list_stack) - 1)
                marker = f"{lvl['n']}. " if lvl["ordered"] else "- "
                self.out.append(indent + marker)
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "blockquote":
            self._newline(2)
            self.out.append("> ")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "hr":
            self._newline(2)
            self.out.append("---")
            self._newline(2)
        elif tag in _BLOCK:
            self._newline(2)

    def handle_endtag(self, tag: str) -> None:
        if self._drop_depth:
            if tag in _DROP or self._drop_depth:
                self._drop_depth -= 1
            return

        if tag in _HEADINGS and self._heading is not None:
            # rustdoc prefixes section headings with a "§" anchor glyph.
            text = re.sub(r"\s+", " ", "".join(self._heading_buf)).strip()
            text = text.lstrip("§").strip()
            level = self._heading
            self._heading = None
            self._heading_buf = []
            if text:
                self.headings.append((level, text))
                self.out.append("#" * level + " " + text)
                self._newline(2)
        elif tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
            if self.out and not self.out[-1].endswith("\n"):
                self.out.append("\n")
            self.out.append("```")
            self._newline(2)
        elif tag == "code":
            if self._pre_depth:
                self._in_code = False
            else:
                self._emit("`")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._newline(2)
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in _BLOCK:
            self._newline(2)

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        if self._pre_depth:
            self.out.append(data)
            return
        if not data.strip():
            # Preserve a single inter-word space, drop pure layout whitespace.
            if self.out and not self.out[-1].endswith((" ", "\n")):
                self._emit(" ")
            return
        self._emit(re.sub(r"\s+", " ", data))

    def result(self) -> str:
        text = "".join(self.out)
        # rustdoc likes zero-width joiners and non-breaking spaces in signatures.
        text = text.replace(" ", " ").replace("​", "")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # An empty fenced block is noise left over from a dropped subtree.
        text = re.sub(r"```\w*\n\s*```\n?", "", text)
        return text.strip() + "\n"


def _slice_main(raw: str) -> str:
    """Return just the content region of a canon page.

    Falls back to the whole document so a layout change upstream degrades to
    noisier output rather than to an empty file.
    """
    for pattern in (
        r'<section id="main-content"[^>]*>(.*?)</section>\s*</div>',
        r'<section id="main-content"[^>]*>(.*)',
        r"<main[^>]*>(.*?)</main>",
        r'<div id="content"[^>]*>(.*?)</div>\s*</main>',
    ):
        m = re.search(pattern, raw, re.S)
        if m:
            return m.group(1)
    return raw


def html_to_markdown(raw: str) -> tuple[str, list[tuple[int, str]]]:
    """Convert one canon HTML page to (markdown, headings)."""
    conv = _Converter()
    conv.feed(_slice_main(raw))
    conv.close()
    return conv.result(), conv.headings


# -- rustdoc-specific ------------------------------------------------------

_SIG_CHROME_RE = re.compile(
    r"^(?:\s*(?:\d[\d.]*"          # "1.63.0"
    r"|\(const[^)]*\)"             # "(const: unstable)"
    r"|·|Source|Read\s+more"
    r"))+\s*"
)

_SIG_RE = re.compile(
    r'<section id="(?P<anchor>(?:method|tymethod|associatedconstant|structfield|variant)\.'
    r'(?P<name>[A-Za-z0-9_]+))"[^>]*>(?P<sig>.*?)</section>',
    re.S,
)


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    text = text.replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def rustdoc_members(raw: str) -> list[dict]:
    """Extract per-member signatures + doc summaries from a rustdoc page.

    This is what makes ``oxidize api std::vec::Vec::retain`` land on a single
    method instead of dumping a 900 KB page describing all 236 of them.
    """
    members: list[dict] = []
    for m in _SIG_RE.finditer(raw):
        sig = strip_tags(m.group("sig"))
        # Signatures are preceded by stability chrome that varies per item:
        # "1.0.0 · Source", "(const: unstable) · Source", "Source" alone, and
        # any of those with the trailing space eaten by tag concatenation.
        sig = _SIG_CHROME_RE.sub("", sig).strip()
        if not sig:
            continue
        tail = raw[m.end():m.end() + 6000]
        doc = ""
        dm = re.search(r'<div class="docblock">(.*?)</div>', tail, re.S)
        if dm and tail[: dm.start()].count("<section id=") == 0:
            doc, _ = html_to_markdown(dm.group(1))
        members.append({
            "name": m.group("name"),
            "anchor": m.group("anchor"),
            "signature": sig,
            "doc": doc.strip(),
        })
    return members


def rustdoc_kind_and_path(rel: str) -> tuple[str, str] | None:
    """Map a rustdoc file path to (kind, ``std::path::Item``).

    ``std/vec/struct.Vec.html``  -> ("struct", "std::vec::Vec")
    ``std/vec/index.html``       -> ("module", "std::vec")
    """
    parts = rel.replace("\\", "/").split("/")
    if not parts or not parts[-1].endswith(".html"):
        return None
    leaf = parts[-1][: -len(".html")]
    mods = parts[:-1]
    if leaf == "index":
        # No mods means the crate root page; caller prefixes the crate name.
        return "module", "::".join(mods)
    if "." not in leaf:
        return None
    kind, _, name = leaf.partition(".")
    known = {"struct", "enum", "trait", "fn", "macro", "type", "constant",
             "static", "union", "primitive", "keyword", "derive", "attr"}
    if kind not in known:
        return None
    return kind, "::".join(mods + [name])


# -- Rust source ----------------------------------------------------------
#
# Worked-example corpora are `.rs` files, not HTML. What matters in a source
# file is different from what matters in a doc page: the public signatures, the
# doc comments, and the tests (which double as usage examples).

_ITEM_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<vis>pub(?:\s*\([^)]*\))?\s+)?"
    r"(?P<mods>(?:default\s+|const\s+|async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*)"
    r"(?P<kind>fn|struct|enum|trait|type|union|macro_rules!|impl)\s+"
    r"(?P<rest>[^{;=]*)",
    re.M,
)

_TEST_MOD_RE = re.compile(
    r"\n#\[cfg\(test\)\]\s*\nmod\s+\w+\s*\{", re.M)


def _balanced_block(text: str, open_idx: int) -> int:
    """Index just past the `}` matching the `{` at `open_idx`.

    Brace counting is not a Rust parser: it can be fooled by braces inside
    string or char literals. It is skipped over those below, which is enough
    for splitting a test module off the end of a file.
    """
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif ch == "'":
            # Could be a lifetime (`'a`) or a char literal (`'x'`).
            if i + 2 < n and (text[i + 1] == "\\" or text[i + 2] == "'"):
                i += 1
                while i < n and text[i] != "'":
                    i += 2 if text[i] == "\\" else 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def split_test_module(source: str) -> tuple[str, str]:
    """Separate `#[cfg(test)] mod tests { .. }` from the implementation."""
    m = _TEST_MOD_RE.search(source)
    if not m:
        return source, ""
    brace = source.index("{", m.start())
    end = _balanced_block(source, brace)
    return (source[: m.start()].rstrip() + "\n", source[m.start(): end].strip())


def rust_items(source: str) -> list[dict]:
    """Public items declared in a Rust source file, with their doc comments."""
    lines = source.splitlines()
    starts = {}
    offset = 0
    for idx, line in enumerate(lines):
        starts[offset] = idx
        offset += len(line) + 1

    items: list[dict] = []
    for m in _ITEM_RE.finditer(source):
        if m.group("indent"):
            continue  # nested item; only top-level ones are the public surface
        kind = m.group("kind")
        vis = (m.group("vis") or "").strip()
        if kind != "impl" and not vis.startswith("pub"):
            continue
        signature = re.sub(r"\s+", " ", m.group(0).strip()).rstrip(",")
        name_m = re.match(r"[A-Za-z_][A-Za-z_0-9]*", m.group("rest").lstrip())
        name = name_m.group(0) if name_m else ""
        if kind == "impl":
            name = m.group("rest").strip()

        # Doc comments and attributes immediately above the item.
        doc: list[str] = []
        line_no = starts.get(m.start(), None)
        if line_no is None:
            line_no = source[: m.start()].count("\n")
        i = line_no - 1
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("///"):
                doc.append(stripped[3:].strip())
            elif stripped.startswith("#[") or stripped.startswith("//"):
                pass
            else:
                break
            i -= 1
        items.append({
            "kind": kind, "name": name, "signature": signature,
            "doc": "\n".join(reversed(doc)).strip(),
        })
    return items


def rust_source_to_markdown(source: str, title: str) -> tuple[str, list[str], list[dict]]:
    """Render one Rust source file as a retrievable document.

    Returns (markdown, headings, items). Tests are kept and labelled: in an
    algorithms corpus they are the clearest statement of how the thing is meant
    to be called.
    """
    module_doc = "\n".join(
        line.strip()[3:].strip()
        for line in source.splitlines()
        if line.strip().startswith("//!")
    ).strip()

    impl_src, test_src = split_test_module(source)
    items = rust_items(impl_src)

    parts = [f"# {title}\n"]
    headings = [title]
    if module_doc:
        parts.append(module_doc + "\n")

    public = [i for i in items if i["kind"] != "impl"]
    if public:
        parts.append("## Public items\n")
        headings.append("Public items")
        for item in public:
            parts.append(f"- `{item['signature']}`")
            if item["doc"]:
                first = item["doc"].splitlines()[0]
                parts.append(f"  - {first}")
        parts.append("")

    documented = [i for i in items if i["doc"]]
    if documented:
        parts.append("## Documentation\n")
        headings.append("Documentation")
        for item in documented:
            parts.append(f"### {item['name']}\n")
            headings.append(item["name"])
            parts.append(f"```rust\n{item['signature']}\n```\n")
            parts.append(item["doc"] + "\n")

    parts.append("## Implementation\n")
    headings.append("Implementation")
    parts.append(f"```rust\n{impl_src.strip()}\n```\n")

    if test_src:
        parts.append("## Tests (usage examples)\n")
        headings.append("Tests (usage examples)")
        parts.append(f"```rust\n{test_src}\n```\n")

    return "\n".join(parts), headings, items


# -- tokenisation ---------------------------------------------------------
#
# Indexing and querying must tokenise identically or terms silently fail to
# match, so both sides call this. Identifiers are also split on `_` and at
# camelCase boundaries, and the parts indexed alongside the whole: a search for
# "capacity" should find `with_capacity`, and "sort key" should find
# `sort_by_key`.

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def tokenize(text: str, split_identifiers: bool = True) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        low = raw.lower()
        if len(low) > 1:
            out.append(low)
        if not split_identifiers:
            continue
        if "_" in raw:
            out.extend(p for p in low.split("_") if len(p) > 1)
        elif not raw.islower() and not raw.isupper():
            parts = _CAMEL_RE.findall(raw)
            if len(parts) > 1:
                out.extend(p.lower() for p in parts if len(p) > 1)
    return out


def estimate_tokens(text: str) -> int:
    """~4 chars per token. Deliberately cheap: this runs over 5k+ documents.

    Only used for budgeting, where being within ~15% is entirely sufficient.
    """
    return max(1, len(text) // 4)
