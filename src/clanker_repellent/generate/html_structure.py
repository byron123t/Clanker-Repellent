"""Parse generated static HTML without rendering it or fetching resources.

This intentionally supports a subset of HTML for inert annotations. It is not a
general-purpose sanitizer or a full HTML conformance checker.
"""

from typing import Dict


_TAGS = set("""
html head title meta body main section article aside nav header footer div span
h1 h2 h3 h4 h5 h6 p ul ol li dl dt dd table caption colgroup col thead tbody tfoot
tr th td figure figcaption blockquote address pre code em strong b i u s small
sub sup mark abbr cite q time samp kbd var br hr a
""".split())
_CONTAINERS = set("main section article aside nav header footer div ul ol dl table figure blockquote".split())
_BLOCKS = set("h1 h2 h3 h4 h5 h6 p li dt dd th td caption figcaption address blockquote".split())
_GLOBAL_ATTRIBUTES = {"id", "class", "lang", "dir", "title", "role"}
_TAG_ATTRIBUTES = {
    "html": set(), "meta": {"charset", "name", "content"},
    "a": {"href"}, "time": {"datetime"}, "ol": {"start", "reversed", "type"},
    "li": {"value"}, "th": {"colspan", "rowspan", "headers", "scope", "abbr"},
    "td": {"colspan", "rowspan", "headers"}, "col": {"span"}, "colgroup": {"span"},
}


def html_metrics(source: str) -> Dict[str, int]:
    """Return counts only; parse/policy errors never include candidate text."""
    import html5lib
    from html5lib.html5parser import ParseError

    # A document needs its HTML5 doctype; ordinary fragments are parsed in a div.
    # Strict mode rejects parse errors instead of accepting browser repairs.
    try:
        root = html5lib.HTMLParser(strict=True, namespaceHTMLElements=False).parse(source)
    except ParseError:
        try:
            root = html5lib.HTMLParser(strict=True, namespaceHTMLElements=False).parseFragment(source)
        except ParseError:
            raise ValueError("HTML parse error; use a valid fragment or an HTML5 document with a doctype.") from None

    elements = list(root.iter())
    identifiers = set()
    for element in elements:
        tag = element.tag
        if not isinstance(tag, str) or tag == "DOCUMENT_FRAGMENT":
            continue  # Comments contribute neither markup structure nor text.
        if tag not in _TAGS:
            raise ValueError("HTML requires static semantic elements; active, embedded, and template content is unsupported.")
        for name, value in element.attrib.items():
            allowed = (name in _GLOBAL_ATTRIBUTES or name in _TAG_ATTRIBUTES.get(tag, set())
                       or name.startswith("aria-") or name.startswith("data-"))
            if not allowed or (name == "aria-hidden" and value.strip().casefold() == "true"):
                raise ValueError("HTML attributes must be static metadata; event handlers, styles, and hidden content are unsupported.")
            if name == "href" and not value.startswith("#"):
                raise ValueError("HTML links must use local fragment identifiers.")
            if name == "id":
                if not value or any(character.isspace() for character in value) or value in identifiers:
                    raise ValueError("HTML identifiers must be nonempty, unique, and contain no whitespace.")
                identifiers.add(value)
        if tag == "meta":
            attrs = element.attrib
            charset = attrs.get("charset", "").casefold()
            named = attrs.get("name", "").casefold()
            if not ((charset == "utf-8" and not named)
                    or (not charset and named in {"description", "viewport"} and "content" in attrs)):
                raise ValueError("HTML metadata supports UTF-8 charset, description, and viewport declarations only.")

    # Count populated leaf blocks, avoiding double-counting a paragraph inside a
    # list item. Comment text, metadata, and empty wrappers never supply content.
    populated = {}
    blocks = {}
    maximum = 0
    for element in reversed(elements):
        tag = element.tag
        if not isinstance(tag, str) or tag in {"head", "title", "meta"}:
            populated[element] = False
            blocks[element] = 0
            continue
        has_text = bool((element.text or "").strip()) or any(
            populated[child] or bool((child.tail or "").strip()) for child in element
        )
        count = sum(blocks[child] for child in element)
        if tag in _BLOCKS and has_text:
            count = max(1, count)
        populated[element] = has_text
        blocks[element] = count
        if tag in _CONTAINERS and element.attrib.get("id"):
            maximum = max(maximum, count)
    return {"fields": maximum, "initialized_fields": maximum,
            "elements": sum(isinstance(element.tag, str) and element.tag != "DOCUMENT_FRAGMENT" for element in elements),
            "populated_blocks": blocks[root]}
