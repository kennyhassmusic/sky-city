"""A small YAML reader for skyline.yaml and grammar.yaml.

Those files use mappings, lists, numbers, booleans, comments and inline [a, b] lists.
This reads that subset. Sky City does not take PyYAML as a dependency (see AGENTS.md:
new dependencies wait for an issue), and the Map Designer can replace this with a
proper parser later without changing the files.
"""


def loads(text):
    lines = _prepare(text)
    if not lines:
        return None
    value, i = _read(lines, 0)
    if i < len(lines):
        raise ValueError("YAML has trailing lines the reader did not understand: %s" % lines[i][1])
    return value


def _prepare(text):
    out = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        if line.startswith("\t"):
            raise ValueError("tabs are not allowed in city YAML; use spaces")
        indent = len(line) - len(line.lstrip(" "))
        out.append((indent, line.strip()))
    return out


def _strip_comment(s):
    quote = ""
    for i, ch in enumerate(s):
        if ch in ("'", '"'):
            if quote == ch:
                quote = ""
            elif not quote:
                quote = ch
        elif ch == "#" and not quote:
            return s[:i]
    return s


def _read(lines, i):
    if i >= len(lines):
        return None, i
    if lines[i][1].startswith("- "):
        return _read_list(lines, i, lines[i][0])
    return _read_map(lines, i, lines[i][0])


def _read_map(lines, i, indent):
    data = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, rest = _split_key(lines[i][1])
        i += 1
        if rest == "":
            if i < len(lines) and lines[i][0] > indent:
                val, i = _read(lines, i)
            else:
                val = None
        else:
            val = _scalar(rest)
        data[key] = val
    return data, i


def _read_list(lines, i, indent):
    items = []
    while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
        rest = lines[i][1][2:].strip()
        i += 1
        if rest == "":
            val, i = _read(lines, i)
            items.append(val)
        elif _starts_nested_item(rest, lines, i, indent):
            key, rval = _split_key(rest)
            item = {}
            if rval == "":
                child, i = _read(lines, i)
                item[key] = child
            else:
                item[key] = _scalar(rval)
            if i < len(lines) and lines[i][0] > indent and not lines[i][1].startswith("- "):
                extra, i = _read_map(lines, i, lines[i][0])
                item.update(extra)
            items.append(item)
        else:
            items.append(_scalar(rest))
    return items, i


def _starts_nested_item(rest, lines, i, indent):
    if ":" not in rest:
        return False
    key, rval = _split_key(rest)
    if not key:
        return False
    # "a: b" on a list item is a one-key map. A URL or a sentence may also contain a colon;
    # those are scalars, and they do not continue as an indented map.
    if i < len(lines) and lines[i][0] > indent and not lines[i][1].startswith("- "):
        return True
    return rval != "" and " " not in key


def _split_key(s):
    # first colon that isn't inside quotes
    quote = ""
    for i, ch in enumerate(s):
        if ch in ("'", '"'):
            quote = "" if quote == ch else (quote or ch)
        elif ch == ":" and not quote:
            return s[:i].strip(), s[i + 1:].strip()
    raise ValueError("expected 'key:' in %r" % s)


def _scalar(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_scalar(p.strip()) for p in _split_top(inner)]
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", "none"):
        return None
    try:
        if s.startswith("0") and len(s) > 1 and s[1] != ".":
            raise ValueError
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _split_top(s):
    parts = []
    buf = []
    depth = 0
    quote = ""
    for ch in s:
        if ch in ("'", '"'):
            quote = "" if quote == ch else (quote or ch)
            buf.append(ch)
        elif quote:
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts
