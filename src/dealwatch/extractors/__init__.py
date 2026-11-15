from __future__ import annotations

from ..config import Extract
from ..models import Observation


class ExtractionError(Exception):
    pass


def extract(html: str, url: str, spec: Extract) -> Observation:
    from . import css, jsonld

    if spec.type == "css":
        return css.extract(html, url, spec)
    return jsonld.extract(html, url)
