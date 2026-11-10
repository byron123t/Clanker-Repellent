"""Bounded, offline configuration, table, and XML document profiles.

Parsing never resolves external resources or evaluates configuration values.
The profiles intentionally accept subsets of the full format specifications.
"""
import configparser
import csv
import io
import math
from xml.parsers import expat


TARGETS = {"csv", "ini", "toml", "xml", "yaml"}
CONTRACT_HINTS = {
    "yaml": "Contract pointers address the parsed YAML mapping. Preserve the contracted scalar types; return YAML, not JSON wrappers.",
    "toml": "Contract pointers address the parsed TOML mapping. Preserve the contracted scalar types; return TOML, not JSON wrappers.",
    "ini": "Contract pointers address section names then case-sensitive keys. Values are literal strings. Arithmetic equations read canonical decimal integer strings. Return INI sections, not the logical mapping as JSON.",
    "csv": "The contract checks a logical object with columns (header strings in order) and records (one object per data row, keyed by header). All record values are strings. Arithmetic equations read canonical decimal integer strings. Return only CSV; do not emit this logical object as JSON.",
    "xml": "The contract checks the root element as an object with tag, attributes, text, tail, children. Child elements use the same shape; text/tail trim surrounding formatting whitespace, attributes remain strings. Arithmetic equations read canonical decimal integer text. Namespaced names use {namespace}local form. Return XML, not this logical tree as JSON.",
}
HINTS = {
    "csv": "Return a comma-separated table with a unique nonempty header of at least two columns and at least one populated data row. All rows have the same width. Quote commas, quotes, and embedded newlines with standard CSV quoting. No prose or Markdown table.",
    "ini": "Return INI with named sections and at least two populated key=value entries in total. Keys are case-sensitive. No DEFAULT section, duplicate sections/keys, interpolation, or bare keys. Values are literal strings.",
    "toml": "Return TOML configuration with at least two populated root keys or tables. Use strings, finite numbers, booleans, arrays, and tables. Quote dates as strings. No duplicate keys or nonfinite numbers.",
    "xml": "Return one well-formed XML document with at least two populated child elements. Use descriptive element names, escaped text, and quoted attributes. No DTD, entities, processing instructions, scripts, or external resources.",
    "yaml": "Return one YAML mapping with at least two populated root keys. Use string keys and ordinary strings, finite numbers, booleans, nulls, lists, and mappings. Quote dates and ambiguous strings. No duplicate keys, tags, anchors, aliases, or merge keys.",
}


def bounded_tree(value):
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 32 or count > 10000:
            raise ValueError("Document exceeds the depth or item limit.")
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ValueError("Mapping keys must be strings.")
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, bool, int, float, type(None)):
            raise ValueError("Use ordinary scalar values; quote dates as strings.")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Numbers must be finite.")
        elif type(item) is int and item.bit_length() > 512:
            raise ValueError("Integer exceeds the fixture size limit.")
        elif isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("Strings must contain valid Unicode scalar values.") from None
    return value


def parse_yaml(source):
    import yaml

    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if type(key) is not str or key in result or key == "<<":
                    raise ValueError("Use unique string mapping keys without merges.")
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        depth = count = 0
        # Bound nesting before SafeLoader constructs a tree; aliases cannot make cycles.
        for event in yaml.parse(source):
            count += 1
            if count > 20000 or getattr(event, "anchor", None) or getattr(event, "tag", None) or isinstance(event, yaml.AliasEvent):
                raise ValueError("YAML aliases, anchors, tags, or oversized documents are outside this profile.")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
                if depth > 32:
                    raise ValueError("YAML nesting exceeds the fixture limit.")
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
        return bounded_tree(yaml.load(source, Loader=UniqueLoader))
    except (yaml.YAMLError, ValueError, RecursionError, OverflowError):
        raise ValueError("Use one bounded YAML mapping with unique string keys and ordinary finite values; no tags or aliases.") from None


def parse_toml(source):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        return bounded_tree(tomllib.loads(source))
    except (ValueError, RecursionError, OverflowError):
        raise ValueError("Use bounded TOML with unique keys, finite values, and dates quoted as strings.") from None


def parse_ini(source):
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=("=",), empty_lines_in_values=False, default_section="")
    parser.optionxform = str
    try:
        parser.read_string(source)
        if "DEFAULT" in parser.sections():
            raise ValueError("DEFAULT inheritance is outside this INI profile.")
        value = {name: dict(parser.items(name, raw=True)) for name in parser.sections()}
        if not value or any(not name.strip() for name in value):
            raise ValueError("INI requires named sections.")
        return bounded_tree(value)
    except (configparser.Error, ValueError):
        raise ValueError("Use named INI sections with unique case-sensitive key=value entries and no DEFAULT section.") from None


def parse_csv(source):
    # csv.reader(strict=True) still accepts quote characters inside an unquoted
    # field. Require conventional quoting rather than silently interpreting it.
    state = "start"
    for char in source:
        if state == "quoted":
            if char == '"': state = "closed"
        elif state == "closed":
            if char == '"': state = "quoted"
            elif char in ",\r\n": state = "start"
            else: raise ValueError("CSV closing quotes must be followed by a delimiter or newline.")
        elif char in ",\r\n":
            state = "start"
        elif char == '"':
            if state != "start": raise ValueError("Quote CSV fields containing literal quotes.")
            state = "quoted"
        else:
            state = "unquoted"
    if state == "quoted":
        raise ValueError("CSV quoted field is not closed.")
    try:
        rows = list(csv.reader(io.StringIO(source, newline=""), strict=True))
    except csv.Error:
        raise ValueError("Use valid CSV quoting and bounded fields.") from None
    if (len(rows) < 2 or len(rows) > 10000 or len(rows[0]) < 2 or len(rows[0]) > 1000
            or any(not key.strip() for key in rows[0]) or len(set(rows[0])) != len(rows[0])
            or any(len(row) != len(rows[0]) for row in rows[1:]) or sum(map(len, rows)) > 10000
            or not any(cell.strip() for row in rows[1:] for cell in row)):
        raise ValueError("CSV requires a unique populated header and rectangular populated records within the item limit.")
    return rows


def xml_metrics(source):
    parser = expat.ParserCreate(namespace_separator="}")
    depth = count = fields = 0
    populated = []
    children = []

    def start(_name, attributes):
        nonlocal depth, count
        depth += 1
        count += 1 + len(attributes)
        if depth > 32 or count > 10000:
            raise ValueError("XML exceeds the depth or item limit.")
        if children:
            children[-1] += 1
        children.append(0)
        populated.append(any(value.strip() for value in attributes.values()))

    def end(_name):
        nonlocal depth, fields
        present = populated.pop()
        leaf = children.pop() == 0
        if present and depth > 1 and leaf:
            fields += 1
        depth -= 1
        if populated and present:
            populated[-1] = True

    def text(value):
        if populated and value.strip():
            populated[-1] = True

    def forbidden(*_args):
        raise ValueError("DTDs, entity declarations, and processing instructions are outside this XML profile.")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ProcessingInstructionHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    try:
        parser.Parse(source, True)
    except (expat.ExpatError, ValueError, RecursionError):
        raise ValueError("Use bounded, well-formed XML without DTDs, declared entities, or processing instructions.") from None
    return {"documents": 1, "elements": count, "fields": fields, "initialized_fields": fields}


def contract_document(language, source):
    """Explicit logical representations for bounded task contracts.

    XML text/tail values retain internal whitespace but trim formatting padding.
    This representation is only for checks; saved source bytes are untouched.
    """
    if language in {"yaml", "toml", "ini"}:
        return {"yaml": parse_yaml, "toml": parse_toml, "ini": parse_ini}[language](source)
    if language == "csv":
        rows = parse_csv(source)
        return {"columns": rows[0], "records": [dict(zip(rows[0], row)) for row in rows[1:]]}
    if language == "xml":
        import xml.etree.ElementTree as ET
        xml_metrics(source)  # Bounds and entity/DTD/PI rejection precede tree construction.
        def node(element):
            return {"tag": element.tag, "attributes": dict(element.attrib), "text": (element.text or "").strip(),
                    "tail": (element.tail or "").strip(), "children": [node(child) for child in element]}
        try:
            return node(ET.fromstring(source))
        except ET.ParseError:
            raise ValueError("XML cannot be represented as a bounded contract tree.") from None
    raise ValueError("Unsupported configuration or markup contract target.")


def metrics(language, source):
    from .document_formats import _populated
    if len(source.encode("utf-8")) > 2_000_000 or "\0" in source:
        raise ValueError("Document exceeds its byte limit or contains NUL.")
    if language == "xml":
        return xml_metrics(source)
    if language == "csv":
        rows = parse_csv(source)
        return {"documents": 1, "fields": len(rows[0]), "initialized_fields": len(rows[0]), "rows": len(rows) - 1}
    value = {"yaml": parse_yaml, "toml": parse_toml, "ini": parse_ini}[language](source)
    if not isinstance(value, dict):
        raise ValueError("Configuration fixtures require a root mapping.")
    fields = sum(bool(key.strip()) and _populated(child) for key, child in value.items())
    if language == "ini":
        fields = sum(bool(key.strip()) and _populated(child) for section in value.values() for key, child in section.items())
    return {"documents": 1, "fields": fields, "initialized_fields": fields}
