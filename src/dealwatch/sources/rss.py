from __future__ import annotations

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from ..config import DiscoverSource
from ..models import DealItem
from . import SourceError, TextFetcher


def fetch(source: DiscoverSource, fetcher: TextFetcher) -> list[DealItem]:
    """Parse an RSS 2.0 or Atom feed. Entries carry a title and link, so filter them by keyword."""
    assert source.url is not None  # guaranteed by config validation
    return parse(fetcher.get(source.url))


def parse(xml_text: str) -> list[DealItem]:
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise SourceError(f"feed is not valid XML: {exc}") from exc

    items = []
    for entry in root.iter():
        if _local(entry.tag) not in ("item", "entry"):
            continue
        fields = {_local(child.tag): child for child in entry}
        title = _text(fields.get("title"))
        link = _link(fields.get("link"))
        item_id = _text(fields.get("guid")) or _text(fields.get("id")) or link
        if title and link and item_id:
            items.append(DealItem(item_id=item_id, title=title, url=link))
    return items


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(element) -> str:
    return (element.text or "").strip() if element is not None else ""


def _link(element) -> str:
    if element is None:
        return ""
    return element.get("href") or _text(element)  # Atom uses href, RSS uses text
