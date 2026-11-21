"""Explicitly licensed offline metadata fixtures; network providers are disabled."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field

from backend.research.schemas import Contract, Id, Summary
from .passages import ToolError


class ExternalMetadata(Contract):
    provider: Literal["crossref", "openalex", "arxiv"]
    record_id: Id
    title: Summary
    abstract: str = Field(default="", max_length=12000)
    year: int | None = Field(default=None, ge=1, le=9999)
    landing_url: str = Field(max_length=1000)
    license: Literal["CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"]
    authors: list[Id] = Field(default_factory=list, max_length=50)


HOSTS = {
    "crossref": {"doi.org", "api.crossref.org"},
    "openalex": {"openalex.org"},
    "arxiv": {"arxiv.org"},
}


def fixture_document(record: ExternalMetadata):
    try:
        url = urlsplit(record.landing_url)
        port = url.port
    except ValueError as error:
        raise ToolError("unsupported_metadata_origin") from error
    if (
        url.scheme != "https"
        or url.hostname not in HOSTS[record.provider]
        or url.username
        or url.password
        or port not in (None, 443)
    ):
        raise ToolError("unsupported_metadata_origin")
    return {
        "paper_id": record.provider + ":" + record.record_id,
        "title": record.title,
        "abstract": record.abstract,
        "authors": record.authors,
        "year": record.year,
        "fulltext": "",
        "pdf_available": False,
        "_rights": "licensed_metadata",
        "license": record.license,
        "landing_url": record.landing_url,
    }
