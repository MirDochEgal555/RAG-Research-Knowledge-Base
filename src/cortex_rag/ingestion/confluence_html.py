"""Convert Confluence HTML space exports into Markdown documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import unicodedata
import zipfile

from cortex_rag.config import PROCESSED_DATA_DIR, RAW_DATA_DIR


CONFLUENCE_RAW_DIR = RAW_DATA_DIR / "confluence"
CONFLUENCE_PROCESSED_DIR = PROCESSED_DATA_DIR / "confluence"


_SPACE_TITLE_PATTERN = re.compile(r"^(?P<key>[^()]+?)\s+\((?P<name>.+)\)$")
_CREATED_PATTERN = re.compile(
    r"Created by\s+(?P<author>.+?)\s+on\s+(?P<created_on>[A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
)
_MARKDOWN_LIST_PATTERN = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class HtmlElement:
    """A lightweight HTML node built from the standard library parser."""

    tag: str
    attrs: dict[str, str]
    children: list[str | "HtmlElement"] = field(default_factory=list)


@dataclass(slots=True)
class ConfluencePage:
    """Parsed information for a single Confluence HTML page."""

    source_html: str
    document_title: str
    page_title: str
    breadcrumbs: list[str]
    page_type: str
    content_node: HtmlElement
    created_by: str | None = None
    created_on: str | None = None
    output_name: str = ""


class _HtmlTreeBuilder(HTMLParser):
    """Build a tolerant HTML tree that is sufficient for Confluence exports."""

    _VOID_TAGS = {"br", "img", "hr", "meta", "link", "input"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlElement("document", {})
        self._stack: list[HtmlElement] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = HtmlElement(tag.lower(), {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(element)
        if element.tag not in self._VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = HtmlElement(tag.lower(), {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(element)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


class _MarkdownRenderer:
    """Render selected HTML content to Markdown."""

    def __init__(self, link_map: dict[str, str], current_source: str) -> None:
        self._link_map = link_map
        self._current_source = current_source
        self._current_dir = posixpath.dirname(current_source)

    def render(self, node: HtmlElement) -> str:
        return _normalize_markdown_spacing(self._render_children(node).strip())

    def _render_children(self, node: HtmlElement, list_depth: int = 0) -> str:
        parts: list[str] = []
        for child in node.children:
            if isinstance(child, str):
                text = _normalize_markdownish_text(child)
                if text:
                    parts.append(text + "\n\n")
                continue
            parts.append(self._render_node(child, list_depth))
        return "".join(parts)

    def _render_node(self, node: HtmlElement, list_depth: int = 0) -> str:
        tag = node.tag

        if tag in {"style", "script"}:
            return ""
        if tag == "br":
            return "  \n"
        if tag == "hr":
            return "\n---\n\n"
        if tag in {"div", "section", "article", "span", "tbody", "thead", "tfoot"}:
            return self._render_children(node, list_depth)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            text = _normalize_markdownish_text(self._render_inline(node))
            return f"{'#' * level} {text}\n\n" if text else ""
        if tag == "p":
            text = _normalize_markdownish_text(self._render_inline(node))
            return _format_markdown_paragraph(text)
        if tag in {"ul", "ol"}:
            return self._render_list(node, ordered=tag == "ol", list_depth=list_depth)
        if tag == "li":
            text = _normalize_markdownish_text(self._render_inline(node))
            return _format_markdown_paragraph(text)
        if tag == "blockquote":
            text = self._render_children(node).strip()
            if not text:
                return ""
            quoted = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
            return quoted + "\n\n"
        if tag == "pre":
            code = _collect_text(node).strip("\n")
            return f"```\n{code}\n```\n\n" if code else ""
        if tag == "table":
            return self._render_table(node)
        if tag == "img":
            return ""
        return self._render_children(node, list_depth)

    def _render_list(self, node: HtmlElement, ordered: bool, list_depth: int) -> str:
        lines: list[str] = []
        item_index = 1
        for child in node.children:
            if not isinstance(child, HtmlElement) or child.tag != "li":
                continue

            prefix = f"{item_index}. " if ordered else "- "
            item_index += 1

            item_text, nested_blocks = self._render_list_item(child, list_depth)
            if not item_text and not nested_blocks:
                continue

            indent = "  " * list_depth
            lines.append(f"{indent}{prefix}{item_text}".rstrip())
            if nested_blocks:
                lines.append(nested_blocks.rstrip())

        return "\n".join(lines) + ("\n\n" if lines else "")

    def _render_list_item(self, node: HtmlElement, list_depth: int) -> tuple[str, str]:
        inline_parts: list[str] = []
        nested_parts: list[str] = []

        for child in node.children:
            if isinstance(child, str):
                inline_parts.append(child)
                continue

            if child.tag in {"ul", "ol"}:
                nested = self._render_list(
                    child, ordered=child.tag == "ol", list_depth=list_depth + 1
                ).strip()
                if nested:
                    nested_parts.append(nested)
                continue

            if child.tag == "p":
                paragraph = _normalize_markdownish_text(self._render_inline(child))
                if paragraph:
                    inline_parts.append(paragraph)
                continue

            inline_parts.append(self._render_inline(child))

        item_text = _normalize_markdownish_text("".join(inline_parts))
        nested_blocks = "\n".join(nested_parts)
        return item_text, nested_blocks

    def _render_table(self, node: HtmlElement) -> str:
        rows = _extract_table_rows(node)
        if not rows:
            return ""

        if all(len(row) == 2 and row[0][0] == "th" for row in rows):
            lines = [
                f"- {_escape_table_cell(cells[0][1])}: {_escape_table_cell(cells[1][1])}"
                for cells in rows
            ]
            return "\n".join(lines) + "\n\n"

        rendered_rows = [[_escape_table_cell(text) for _, text in row] for row in rows]
        header = rendered_rows[0]
        body = rendered_rows[1:]
        if not any(header):
            header = [f"Column {index + 1}" for index in range(len(header))]
        separator = ["---"] * len(header)
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in body:
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[: len(header)]) + " |")
        return "\n".join(lines) + "\n\n"

    def _render_inline(self, node: HtmlElement | str) -> str:
        if isinstance(node, str):
            return _collapse_inline_whitespace(node)

        tag = node.tag
        if tag in {"style", "script"}:
            return ""
        if tag == "br":
            return "\n"
        if tag in {"strong", "b"}:
            text = self._render_inline_children(node)
            return f"**{text}**" if text else ""
        if tag in {"em", "i"}:
            text = self._render_inline_children(node)
            return f"*{text}*" if text else ""
        if tag == "code":
            text = self._render_inline_children(node)
            return f"`{text}`" if text else ""
        if tag == "a":
            text = self._render_inline_children(node).strip() or node.attrs.get("href", "").strip()
            href = node.attrs.get("href", "").strip()
            if not href:
                return text
            resolved = self._resolve_href(href)
            return f"[{text}]({resolved})"
        if tag == "img":
            return ""
        return self._render_inline_children(node)

    def _render_inline_children(self, node: HtmlElement) -> str:
        return "".join(self._render_inline(child) for child in node.children)

    def _resolve_href(self, href: str) -> str:
        if href.startswith(("http://", "https://", "mailto:", "#")):
            return href

        normalized = posixpath.normpath(posixpath.join(self._current_dir, href))
        return self._link_map.get(normalized, href)


def preprocess_confluence_exports(
    input_dir: Path = CONFLUENCE_RAW_DIR,
    output_dir: Path = CONFLUENCE_PROCESSED_DIR,
) -> list[Path]:
    """Convert every Confluence space archive in a directory into Markdown files."""

    output_paths: list[Path] = []
    if not input_dir.exists():
        return output_paths

    for zip_path in sorted(input_dir.glob("*.zip")):
        output_paths.extend(preprocess_confluence_archive(zip_path, output_dir))
    return output_paths


def preprocess_confluence_archive(zip_path: Path, output_dir: Path = CONFLUENCE_PROCESSED_DIR) -> list[Path]:
    """Convert a single Confluence space archive into Markdown files."""

    space_key = zip_path.stem.split("_", maxsplit=1)[0]
    archive_output_dir = output_dir / space_key
    archive_output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        page_names = sorted(
            name for name in archive.namelist() if name.endswith(".html") and not name.endswith("/styles/site.css")
        )
        pages = [_parse_page(name, archive.read(name).decode("utf-8", errors="ignore")) for name in page_names]

    space_name = _resolve_space_name(space_key, pages)
    link_map = _build_link_map(pages)

    output_paths: list[Path] = []
    for page in pages:
        renderer = _MarkdownRenderer(link_map=link_map, current_source=page.source_html)
        body = renderer.render(page.content_node)
        document = _build_markdown_document(
            space_key=space_key,
            space_name=space_name,
            source_zip=zip_path.name,
            page=page,
            body=body,
        )
        output_path = archive_output_dir / page.output_name
        output_path.write_text(document, encoding="utf-8")
        output_paths.append(output_path)

    return output_paths


def _parse_page(source_html: str, html_text: str) -> ConfluencePage:
    tree = _parse_html_tree(html_text)
    breadcrumbs = _extract_breadcrumbs(tree)
    document_title = _extract_document_title(tree)
    page_type = "space_index" if source_html.endswith("/index.html") else "page"
    page_title = _clean_page_title(_extract_header_title(tree) or document_title, breadcrumbs)
    content_node = _find_by_id(tree, "content") if page_type == "space_index" else _find_by_id(tree, "main-content")
    if content_node is None:
        raise ValueError(f"Could not locate content node in {source_html}")

    created_by = None
    created_on = None
    metadata_node = _find_by_class(tree, "page-metadata")
    if metadata_node is not None:
        created_by, created_on = _parse_created_metadata(_collect_text(metadata_node))

    return ConfluencePage(
        source_html=source_html,
        document_title=document_title,
        page_title=page_title,
        breadcrumbs=breadcrumbs,
        page_type=page_type,
        content_node=content_node,
        created_by=created_by,
        created_on=created_on,
    )


def _parse_html_tree(html_text: str) -> HtmlElement:
    parser = _HtmlTreeBuilder()
    parser.feed(html_text)
    parser.close()
    return parser.root


def _extract_breadcrumbs(node: HtmlElement) -> list[str]:
    breadcrumb_node = _find_by_id(node, "breadcrumbs")
    if breadcrumb_node is None:
        return []

    crumbs: list[str] = []
    for child in _iter_elements(breadcrumb_node):
        if child.tag == "a":
            text = _collect_text(child)
            if text:
                crumbs.append(text)
    return crumbs


def _extract_document_title(node: HtmlElement) -> str:
    title_node = _find_first(node, lambda item: item.tag == "title")
    return _collect_text(title_node) if title_node is not None else ""


def _extract_header_title(node: HtmlElement) -> str:
    title_node = _find_by_id(node, "title-text")
    return _collect_text(title_node) if title_node is not None else ""


def _parse_created_metadata(text: str) -> tuple[str | None, str | None]:
    match = _CREATED_PATTERN.search(_normalize_spaces(text))
    if not match:
        return None, None

    created_on = match.group("created_on")
    try:
        created_on = datetime.strptime(created_on, "%b %d, %Y").date().isoformat()
    except ValueError:
        pass
    return match.group("author").strip(), created_on


def _resolve_space_name(space_key: str, pages: list[ConfluencePage]) -> str:
    for page in pages:
        if page.breadcrumbs:
            return page.breadcrumbs[0]

    for page in pages:
        match = _SPACE_TITLE_PATTERN.match(page.document_title)
        if match and match.group("key").strip() == space_key:
            return match.group("name").strip()

    return space_key


def _build_link_map(pages: list[ConfluencePage]) -> dict[str, str]:
    counts: dict[str, int] = {}
    link_map: dict[str, str] = {}
    for page in pages:
        page.output_name = _build_output_name(page, counts)
        link_map[page.source_html] = page.output_name
    return link_map


def _build_output_name(page: ConfluencePage, counts: dict[str, int]) -> str:
    if page.page_type == "space_index":
        return "space-index.md"

    source_stem = Path(page.source_html).stem
    match = re.match(r"^(?P<name>.+?)_(?P<page_id>\d+)$", source_stem)
    page_id = match.group("page_id") if match else None

    title_seed = _strip_markdown_prefix(page.page_title) or source_stem
    slug = _slugify(title_seed) or _slugify(source_stem) or "page"
    base_name = f"{slug}-{page_id}" if page_id else slug

    count = counts.get(base_name, 0)
    counts[base_name] = count + 1
    if count:
        return f"{base_name}-{count + 1}.md"
    return f"{base_name}.md"


def _build_markdown_document(
    *,
    space_key: str,
    space_name: str,
    source_zip: str,
    page: ConfluencePage,
    body: str,
) -> str:
    front_matter: list[str] = [
        "---",
        f"space_key: {_yaml_quote(space_key)}",
        f"space_name: {_yaml_quote(space_name)}",
        f"page_title: {_yaml_quote(page.page_title)}",
        f"page_type: {_yaml_quote(page.page_type)}",
        f"source_zip: {_yaml_quote(source_zip)}",
        f"source_html: {_yaml_quote(page.source_html)}",
    ]
    if page.breadcrumbs:
        front_matter.append("breadcrumbs:")
        front_matter.extend(f"  - {_yaml_quote(crumb)}" for crumb in page.breadcrumbs)
    if page.created_by:
        front_matter.append(f"created_by: {_yaml_quote(page.created_by)}")
    if page.created_on:
        front_matter.append(f"created_on: {_yaml_quote(page.created_on)}")
    front_matter.append("---")

    if body:
        return "\n".join(front_matter) + "\n\n" + body + "\n"
    return "\n".join(front_matter) + "\n"


def _find_by_id(node: HtmlElement, target_id: str) -> HtmlElement | None:
    return _find_first(node, lambda item: item.attrs.get("id") == target_id)


def _find_by_class(node: HtmlElement, target_class: str) -> HtmlElement | None:
    return _find_first(node, lambda item: target_class in item.attrs.get("class", "").split())


def _find_first(node: HtmlElement, predicate) -> HtmlElement | None:
    if predicate(node):
        return node
    for child in node.children:
        if isinstance(child, str):
            continue
        found = _find_first(child, predicate)
        if found is not None:
            return found
    return None


def _iter_elements(node: HtmlElement):
    for child in node.children:
        if isinstance(child, str):
            continue
        yield child
        yield from _iter_elements(child)


def _collect_text(node: HtmlElement | None) -> str:
    if node is None:
        return ""

    pieces: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            pieces.append(child)
            continue
        if child.tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            pieces.append("\n")
        pieces.append(_collect_text(child))
    return _normalize_spaces("".join(pieces))


def _extract_table_rows(node: HtmlElement) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    for element in _iter_elements(node):
        if element.tag != "tr":
            continue
        cells: list[tuple[str, str]] = []
        for child in element.children:
            if isinstance(child, str) or child.tag not in {"th", "td"}:
                continue
            cells.append((child.tag, _normalize_markdownish_text(_collect_text(child))))
        if cells:
            rows.append(cells)
    return rows


def _escape_table_cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", "<br>")


def _clean_page_title(raw_title: str, breadcrumbs: list[str]) -> str:
    title = _normalize_spaces(raw_title).rstrip(":")
    if breadcrumbs:
        prefix = breadcrumbs[0]
        marker = f"{prefix} : "
        if title.startswith(marker):
            title = title[len(marker) :]
    return _strip_markdown_prefix(title) or title


def _strip_markdown_prefix(text: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", text).strip()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    collapsed = _NON_ALNUM_PATTERN.sub("-", ascii_value).strip("-")
    return collapsed


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _collapse_inline_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text


def _normalize_markdownish_text(text: str) -> str:
    text = _collapse_inline_whitespace(text).strip()
    if not text:
        return ""

    text = re.sub(r"^\u2022\s*", "- ", text)
    text = re.sub(r"^[•◦▪]\s*", "- ", text)
    text = re.sub(r"^(\d+)\.\s*", r"\1. ", text)

    if text in {"⸻", "—", "–––"}:
        return "---"
    return text


def _format_markdown_paragraph(text: str) -> str:
    if not text:
        return ""
    if text == "---":
        return "\n---\n\n"
    if _MARKDOWN_HEADING_PATTERN.match(text):
        return text + "\n\n"
    if _MARKDOWN_LIST_PATTERN.match(text):
        return text + "\n"
    return text + "\n\n"


def _normalize_markdown_spacing(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    for index, line in enumerate(lines):
        normalized.append(line)
        if index == len(lines) - 1:
            continue

        next_line = lines[index + 1]
        if not line or not next_line:
            continue
        if _is_list_line(line) and not _is_markdown_list_continuation(next_line):
            normalized.append("")

    return "\n".join(normalized).strip()


def _is_list_line(text: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]|\d+\.)\s+", text))


def _is_markdown_list_continuation(text: str) -> bool:
    return _is_list_line(text) or text.startswith("  ")
