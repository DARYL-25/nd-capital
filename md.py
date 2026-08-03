# -*- coding: utf-8 -*-
"""
Minimal, dependency-free Markdown -> HTML converter.

Deliberately not a general-purpose implementation. It handles exactly the subset
used by ND Capital research files — YAML-ish front matter, ATX headings, pipe
tables, blockquotes, ordered/unordered lists, horizontal rules, bold, italic,
inline code and links — so that `build.py` runs on a clean Python install with
nothing to `pip install`. That matters because Daryl rebuilds the site locally.
"""

import html
import re

# ---------------------------------------------------------------- front matter

def split_front_matter(text):
    """Return (metadata dict, body). Supports scalars, [a, b] lists and quoted strings."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4:]
    meta = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
        elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            meta[key] = val[1:-1]
        elif val in ("null", "None", ""):
            meta[key] = None
        else:
            meta[key] = val
    return meta, body.lstrip("\n")


# ---------------------------------------------------------------- inline

_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITAL = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)")


def inline(text):
    out = html.escape(text, quote=False)
    # placeholders keep code spans safe from later substitutions
    codes = []

    def _stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes)-1}\x00"

    out = _CODE.sub(_stash, out)
    out = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITAL.sub(r"<em>\1</em>", out)
    out = out.replace("--", "&ndash;")
    for i, c in enumerate(codes):
        out = out.replace(f"\x00{i}\x00", f"<code>{c}</code>")
    return out


# ---------------------------------------------------------------- block

def _is_table_sep(line):
    s = line.strip()
    return bool(s) and set(s) <= set("|-: ") and "-" in s and "|" in s


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render(text):
    """Markdown -> HTML for the supported subset."""
    lines = text.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # blank
        if not stripped:
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            out.append('<hr class="rule">')
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        # table
        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            head = _cells(lines[i])
            i += 2
            body = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body.append(_cells(lines[i]))
                i += 1
            out.append('<div class="tbl-wrap"><table>')
            out.append("<thead><tr>" + "".join(
                f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>")
            for row in body:
                row = (row + [""] * len(head))[:len(head)]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + render("\n".join(buf)) + "</blockquote>")
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", stripped):
            out.append("<ol>")
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                i += 1
                while i < n and lines[i].strip() and not re.match(
                        r"^(\d+\.|[-*+])\s+|^#{1,6}\s|^>|^-{3,}", lines[i].strip()):
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{inline(item)}</li>")
            out.append("</ol>")
            continue

        # unordered list (also handles "- [x] " checkboxes)
        if re.match(r"^[-*+]\s+", stripped):
            out.append("<ul>")
            while i < n and re.match(r"^[-*+]\s+", lines[i].strip()):
                item = re.sub(r"^[-*+]\s+", "", lines[i].strip())
                cls = ""
                if item.startswith("[x] ") or item.startswith("[X] "):
                    item, cls = item[4:], ' class="done"'
                elif item.startswith("[ ] "):
                    item, cls = item[4:], ' class="todo"'
                i += 1
                while i < n and lines[i].strip() and not re.match(
                        r"^(\d+\.|[-*+])\s+|^#{1,6}\s|^>|^-{3,}|^\|", lines[i].strip()):
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li{cls}>{inline(item)}</li>")
            out.append("</ul>")
            continue

        # paragraph
        buf = []
        while i < n and lines[i].strip() and not re.match(
                r"^#{1,6}\s|^>|^-{3,}|^\*{3,}|^(\d+\.|[-*+])\s+", lines[i].strip()) \
                and not ("|" in lines[i] and i + 1 < n and _is_table_sep(lines[i + 1])):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{inline(' '.join(buf))}</p>")

    return "\n".join(out)


def sections(body):
    """Split a research file on '## ' headings -> ordered [(title, markdown), ...]."""
    parts, cur, buf = [], None, []
    for line in body.split("\n"):
        m = re.match(r"^##\s+(?!#)(.*)$", line)
        if m:
            if cur is not None:
                parts.append((cur, "\n".join(buf).strip()))
            cur, buf = m.group(1).strip(), []
        else:
            if cur is not None:
                buf.append(line)
    if cur is not None:
        parts.append((cur, "\n".join(buf).strip()))
    return parts


def strip_md(text, limit=None):
    """Plain text from markdown, for meta descriptions and card summaries."""
    t = re.sub(r"[#>*`_]", "", text)
    t = _LINK.sub(r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t
