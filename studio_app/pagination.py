from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

_BREAK_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "div"})

_DEFAULT_WRAPPER = (
    '<!DOCTYPE html><html><head><meta charset="utf-8">'
    '<style>.page{{box-sizing:border-box;padding:2em;}}</style></head>'
    "<body><div class=\"page\">{content}</div></body></html>"
)


def _visible_len(html_fragment: str) -> int:
    return len(BeautifulSoup(html_fragment, "html.parser").get_text())


def _wrap_page(inner_html: str, page_template: str | None) -> str:
    tpl = page_template if page_template is not None else _DEFAULT_WRAPPER
    return tpl.format(content=inner_html)


def paginate_html_to_pages(
    html: str,
    chars_per_page: int,
    *,
    page_template: str | None = None,
) -> list[str]:
    """Split html into standalone page documents at element boundaries."""
    if chars_per_page < 1:
        raise ValueError("chars_per_page must be >= 1")
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if body is None:
        wrapper = BeautifulSoup(f"<body>{html}</body>", "html.parser")
        children = list(wrapper.body.children) if wrapper.body else []
    else:
        children = [c for c in body.children if getattr(c, "name", None)]

    if not children:
        return [_wrap_page("", page_template)]

    pages: list[str] = []
    buf: list[str] = []
    running = 0

    for child in children:
        frag = str(child)
        tag = child.name if hasattr(child, "name") else None
        text_len = _visible_len(frag)

        if buf and running + text_len > chars_per_page and tag in _BREAK_TAGS:
            pages.append(_wrap_page("".join(buf), page_template))
            buf = []
            running = 0

        buf.append(frag)
        running += text_len

        if running >= chars_per_page and tag in _BREAK_TAGS:
            pages.append(_wrap_page("".join(buf), page_template))
            buf = []
            running = 0

    if buf:
        pages.append(_wrap_page("".join(buf), page_template))

    return pages or [_wrap_page("", page_template)]


def paginate_txt(text: str, chars_per_page: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    inner = "".join(f"<p>{p}</p>" for p in paragraphs) if paragraphs else ""
    return paginate_html_to_pages(inner, chars_per_page)


def paginate_docx(path: Path, chars_per_page: int) -> list[str]:
    import mammoth
    with path.open("rb") as fh:
        result = mammoth.convert_to_html(fh)
    return paginate_html_to_pages(result.value, chars_per_page)
