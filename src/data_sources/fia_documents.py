from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests


FIA_DOCUMENT_INDEX_PATH = "data/fia_documents/fia_document_index.csv"
FIA_PDF_HOSTS = frozenset({"fia.com", "www.fia.com"})
FIA_PDF_MAX_BYTES = 20_000_000
_REDIRECT_CODES = {301, 302, 303, 307, 308}


FIA_DOCUMENT_COLUMNS = [
    "year",
    "event",
    "session",
    "document_type",
    "doc_number",
    "document_title",
    "document_url",
    "published_at",
    "driver",
    "team",
    "grid_position",
    "classification_position",
    "penalty_type",
    "penalty_value",
    "summons_reason",
    "status",
    "notes",
    "first_seen_at_utc", "pdf_sha256", "roster_size", "pit_lane_start", "withdrawn",
    "target_session", "decision_text", "decision_reference", "extraction_version",
]

FIA_DOCUMENTS_BASE_URL = "https://www.fia.com"
FIA_F1_DOCUMENTS_SEASON_URL_TEMPLATE = (
    "https://www.fia.com/documents/championships/"
    "fia-formula-one-world-championship-14/season/season-{year}-{season_id}"
)
FIA_F1_SEASON_IDS = {
    2019: 971,
    2020: 1059,
    2021: 1108,
    2022: 2005,
    2023: 2042,
    2024: 2043,
    2025: 2071,
    2026: 2072,
}


@dataclass(frozen=True)
class FiaDocumentListing:
    year: int
    event: str
    document_type: str
    doc_number: str
    document_title: str
    document_url: str
    published_at: str
    session: str
    listing_status: str = 'active'

    def to_row(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "event": self.event,
            "session": self.session,
            "document_type": self.document_type,
            "doc_number": self.doc_number,
            "document_title": self.document_title,
            "document_url": self.document_url,
            "published_at": self.published_at,
            "driver": "",
            "team": "",
            "grid_position": "",
            "classification_position": "",
            "penalty_type": "",
            "penalty_value": "",
            "summons_reason": "",
            "status": "recalled" if self.listing_status == 'recalled' else "metadata",
            "notes": "Fetched from FIA decision documents listing.",
        }


class _FiaDocumentListParser(HTMLParser):
    def __init__(self, year: int, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.year = year
        self.base_url = base_url
        self.current_event = ""
        self.current_document: dict[str, str] | None = None
        self._capture_event = False
        self._capture_title = False
        self._capture_published = False
        self._document_li_depth = 0
        self.listings: list[FiaDocumentListing] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set(str(attr.get("class", "")).split())

        if tag == "div" and "event-title" in classes:
            self._capture_event = True
            return

        if tag == "li" and "document-row" in classes:
            self.current_document = {
                "event": self.current_event,
                "href": "",
                "title": "",
                "published": "",
            }
            self._document_li_depth = 1
            return

        if self.current_document is None:
            return

        if tag == "li":
            self._document_li_depth += 1
        elif tag == "a" and attr.get("href"):
            self.current_document["href"] = urljoin(self.base_url, str(attr["href"]))
        elif tag == "div" and "title" in classes:
            self._capture_title = True
        elif tag == "div" and "published" in classes:
            self._capture_published = True

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return

        if self._capture_event:
            self.current_event = text
            return

        if self.current_document is None:
            return

        if self._capture_title:
            self.current_document["title"] = " ".join(
                [self.current_document["title"], text]
            ).strip()
        elif self._capture_published:
            self.current_document["published"] = " ".join(
                [self.current_document["published"], text]
            ).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            self._capture_event = False
            self._capture_title = False
            self._capture_published = False
            return

        if self.current_document is None or tag != "li":
            return

        self._document_li_depth -= 1
        if self._document_li_depth <= 0:
            listing = _listing_from_parser_state(
                year=self.year,
                event=self.current_document["event"],
                href=self.current_document["href"],
                raw_title=self.current_document["title"],
                raw_published=self.current_document["published"],
            )
            if listing is not None:
                self.listings.append(listing)
            self.current_document = None


def _listing_from_parser_state(
    year: int,
    event: str,
    href: str,
    raw_title: str,
    raw_published: str,
) -> FiaDocumentListing | None:
    title_text = unescape(raw_title).strip()
    match = re.search(r"\bDoc(?:ument)?\.?\s+([A-Za-z0-9.-]+)\s*-\s*(.+)", title_text, re.I)
    recalled = title_text.casefold().startswith('recalled')
    if not title_text or (not href and not recalled):
        return None

    # Older FIA archive listings publish a title and PDF URL without a document
    # number. Retain their real metadata rather than discard or invent a number.
    doc_number = f"Doc {match.group(1).strip()}" if match else ""
    document_title = match.group(2).strip() if match else title_text
    published_at = _clean_published_at(raw_published)

    return FiaDocumentListing(
        year=year,
        event=event.strip(),
        document_type=classify_fia_document_type(document_title),
        doc_number=doc_number,
        document_title=document_title,
        document_url=href,
        published_at=published_at,
        session=infer_fia_session(document_title, year=year),
        listing_status='recalled' if recalled else 'active',
    )


def _clean_published_at(value: str) -> str:
    return (
        unescape(value)
        .replace("Published on", "")
        .replace("Published", "")
        .strip()
    )


def classify_fia_document_type(title: str) -> str:
    normalized = title.casefold()
    if "starting grid" in normalized:
        if "final" in normalized:
            return "final starting grid"
        if "official" in normalized:
            return "official starting grid"
        return "starting grid"
    if "classification" in normalized:
        if "qualifying" in normalized:
            return "qualifying classification"
        if "race" in normalized:
            return "race classification"
        return "classification"
    if "summons" in normalized:
        return "summons"
    if "decision" in normalized:
        return "stewards decision"
    if "infringement" in normalized:
        return "infringement"
    if "new pu elements" in normalized or "power unit" in normalized:
        return "power unit"
    if "scrutineering" in normalized:
        return "scrutineering"
    return "document"


def infer_fia_session(title: str, year: int | None = None) -> str:
    normalized = title.casefold()
    if "free practice 1" in normalized or "practice 1" in normalized:
        return "FP1"
    if "free practice 2" in normalized or "practice 2" in normalized:
        return "FP2"
    if "free practice 3" in normalized or "practice 3" in normalized:
        return "FP3"
    if "sprint shootout" in normalized:
        return "SQ"
    if "sprint qualifying" in normalized:
        # In 2021/2022 this name described the sprint race, not a shootout.
        return "S" if year in {2021, 2022} else "SQ"
    if "sprint" in normalized:
        return "S"
    if "qualifying" in normalized:
        return "Q"
    if "starting grid" in normalized or "race classification" in normalized:
        return "R"
    return ""


def fia_f1_documents_url(year: int, season_id: int | None = None) -> str:
    resolved_season_id = season_id or FIA_F1_SEASON_IDS.get(year)
    if resolved_season_id is None:
        raise ValueError(
            f"No FIA season id is configured for {year}. Pass --season-url explicitly."
        )

    return FIA_F1_DOCUMENTS_SEASON_URL_TEMPLATE.format(
        year=year,
        season_id=resolved_season_id,
    )


def parse_fia_document_listing_html(
    html: str,
    year: int,
    base_url: str = FIA_DOCUMENTS_BASE_URL,
) -> list[FiaDocumentListing]:
    parser = _FiaDocumentListParser(year=year, base_url=base_url)
    parser.feed(html)
    return parser.listings


def parse_fia_event_urls(
    html: str,
    base_url: str = FIA_DOCUMENTS_BASE_URL,
) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r'<option\s+value="([^"]*?/event/[^"]+)"', html, re.I):
        url = urljoin(base_url, unescape(match.group(1)))
        if url not in urls:
            urls.append(url)
    return urls


def _dedupe_listings(listings: list[FiaDocumentListing]) -> list[FiaDocumentListing]:
    seen: set[tuple[str, str, str, str]] = set()
    output: list[FiaDocumentListing] = []

    for listing in listings:
        key = (
            str(listing.year),
            listing.event.casefold(),
            listing.doc_number.casefold(),
            listing.document_url,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(listing)

    return output


def fetch_fia_document_listings(
    year: int,
    season_url: str | None = None,
    timeout: int = 30,
    include_event_pages: bool = True,
) -> list[FiaDocumentListing]:
    url = season_url or fia_f1_documents_url(year)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    listings = parse_fia_document_listing_html(response.text, year=year, base_url=url)

    if include_event_pages:
        for event_url in parse_fia_event_urls(response.text, base_url=url):
            event_response = requests.get(event_url, timeout=timeout)
            event_response.raise_for_status()
            listings.extend(
                parse_fia_document_listing_html(
                    event_response.text,
                    year=year,
                    base_url=event_url,
                )
            )

    return _dedupe_listings(listings)


def ensure_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not output_path.exists():
        pd.DataFrame(columns=FIA_DOCUMENT_COLUMNS).to_csv(output_path, index=False)

    return str(output_path)


def load_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    ensure_fia_document_index(path)

    df = pd.read_csv(path)

    for col in FIA_DOCUMENT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
            
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    df["driver"] = df["driver"].fillna('').astype(str).str.strip().str.upper()
    df["event"] = df["event"].astype(str).str.strip()
    df["document_type"] = df["document_type"].astype(str).str.strip().str.lower()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["grid_position"] = pd.to_numeric(df["grid_position"], errors="coerce")
    df["classification_position"] = pd.to_numeric(
        df["classification_position"],
        errors="coerce",
    )

    return df[FIA_DOCUMENT_COLUMNS].copy()


def _filter_event(
    df: pd.DataFrame,
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
) -> pd.DataFrame:
    output = df.copy()

    if year is not None and "year" in output.columns:
        output = output[output["year"].eq(year)]

    if event is not None and "event" in output.columns:
        event_lower = event.strip().lower()
        output = output[output["event"].astype(str).str.lower().eq(event_lower)]

    if session is not None and "session" in output.columns:
        session_lower = session.strip().lower()
        output = output[output["session"].astype(str).str.lower().eq(session_lower)]

    return output.reset_index(drop=True)


def official_grid(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    grid = df[
        df["document_type"].isin(
            [
                "grid",
                "starting grid",
                "official starting grid",
                "final starting grid",
            ]
        )
    ].copy()

    grid = grid.dropna(subset=["driver", "grid_position"])

    if grid.empty:
        return pd.DataFrame(columns=["Driver", "fia_grid_position", "fia_grid_source"])

    grid["Driver"] = grid["driver"].astype(str).str.upper()
    grid["fia_grid_position"] = grid["grid_position"].astype(int)
    grid["fia_grid_source"] = grid["document_title"].fillna("FIA official grid")

    return grid[
        [
            "Driver",
            "team",
            "fia_grid_position",
            "fia_grid_source",
            "document_url",
            "published_at",
        ]
    ].sort_values("fia_grid_position").reset_index(drop=True)


def penalties(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(
            [
                "penalty",
                "decision",
                "stewards decision",
                "grid penalty",
            ]
        )
        | df["penalty_type"].notna()
    ].copy()

    return output.reset_index(drop=True)


def summons(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(["summons", "summon"])
        | df["summons_reason"].notna()
    ].copy()

    return output.reset_index(drop=True)


def classification(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> pd.DataFrame:
    df = _filter_event(
        load_fia_document_index(path),
        year=year,
        event=event,
        session=session,
    )

    output = df[
        df["document_type"].isin(
            [
                "classification",
                "final classification",
                "race classification",
                "qualifying classification",
            ]
        )
        | df["classification_position"].notna()
    ].copy()

    if output.empty:
        return output

    output["Driver"] = output["driver"].astype(str).str.upper()

    return output.reset_index(drop=True)


def build_fia_context(
    year: int | None = None,
    event: str | None = None,
    session: str | None = None,
    path: str = FIA_DOCUMENT_INDEX_PATH,
    *, cutoff: str | None = None, safe_asof: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    Returns official FIA context frames for future integration.

    Intended consumers:
    - grid.py: official starting grids and penalties
    - strategy.py: summons/penalties that affect tyre/race assumptions
    - report_card.py: show FIA notes and official document links
    """

    if safe_asof:
        from src.data_sources.fia_asof import context_asof
        return context_asof(load_fia_document_index(path),year,event,cutoff)
    return {
        "official_grid": official_grid(year=year, event=event, session=session, path=path),
        "penalties": penalties(year=year, event=event, session=session, path=path),
        "summons": summons(year=year, event=event, session=session, path=path),
        "classification": classification(year=year, event=event, session=session, path=path),
    }


def save_fia_context(
    context: dict[str, pd.DataFrame],
    output_dir: str = "outputs/data_sources/fia",
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved: dict[str, str] = {}

    for name, df in context.items():
        file_path = output_path / f"{name}.csv"
        df.to_csv(file_path, index=False)
        saved[name] = str(file_path)

    return saved


def create_example_fia_document_index(
    path: str = FIA_DOCUMENT_INDEX_PATH,
) -> str:
    """
    Creates a starter/example CSV if one does not already exist.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)

    example = pd.DataFrame(
        [
            {
                "year": 2026,
                "event": "Barcelona Grand Prix",
                "session": "R",
                "document_type": "official starting grid",
                "doc_number": "Doc XX",
                "document_title": "Official Starting Grid",
                "document_url": "",
                "published_at": "",
                "driver": "RUS",
                "team": "Mercedes",
                "grid_position": 1,
                "classification_position": pd.NA,
                "penalty_type": "",
                "penalty_value": "",
                "summons_reason": "",
                "status": "",
                "notes": "Example row. Replace with real FIA scraper output.",
            }
        ],
        columns=FIA_DOCUMENT_COLUMNS,
    )

    example.to_csv(output_path, index=False)

    return str(output_path)


def load_driver_map(path: str | None = None) -> dict[str, dict[str, str]]:
    if not path:
        return {}

    frame = pd.read_csv(path)
    output: dict[str, dict[str, str]] = {}

    for row in frame.to_dict("records"):
        car_number = str(row.get("car_number", row.get("number", ""))).strip()
        if not car_number:
            continue
        output[car_number] = {
            "driver": str(row.get("driver", "")).strip().upper(),
            "team": str(row.get("team", "")).strip(),
        }

    return output


def _base_row_from_listing(
    listing: FiaDocumentListing,
    status: str,
    notes: str,
) -> dict[str, Any]:
    row = listing.to_row()
    row["status"] = status
    row["notes"] = notes
    return row


def _line_to_competitor_row(
    line: str,
    *,
    listing: FiaDocumentListing,
    position_field: str,
    driver_map: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    normalized = " ".join(line.split())
    match = re.match(r"^(\d{1,2})\s+(\d{1,3})\s+(.+)$", normalized)
    if not match:
        return None

    position = match.group(1)
    car_number = match.group(2)
    rest = match.group(3)
    mapped = driver_map.get(car_number, {})

    driver = mapped.get("driver", "")
    team = mapped.get("team", "")

    acronym_match = re.search(r"\b([A-Z]{3})\b", rest)
    if not driver and acronym_match:
        driver = acronym_match.group(1)

    row = _base_row_from_listing(
        listing,
        status="parsed",
        notes=f"Parsed from FIA PDF text. Car {car_number}: {rest}",
    )
    row["driver"] = driver
    row["team"] = team
    row[position_field] = int(position)
    return row


def parse_fia_competitor_rows_from_text(
    text: str,
    listing: FiaDocumentListing,
    driver_map: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    driver_map = driver_map or {}
    position_field = (
        "grid_position"
        if "grid" in listing.document_type
        else "classification_position"
    )
    rows: list[dict[str, Any]] = []

    for line in text.splitlines():
        row = _line_to_competitor_row(
            line,
            listing=listing,
            position_field=position_field,
            driver_map=driver_map,
        )
        if row is not None:
            rows.append(row)

    return rows


def parse_fia_stewards_row_from_title(
    listing: FiaDocumentListing,
    driver_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    if listing.document_type not in {"summons", "stewards decision", "infringement"}:
        return None

    driver_map = driver_map or {}
    match = re.search(r"\bCar\s+(\d{1,3})\b\s*-?\s*(.*)", listing.document_title, re.I)
    if not match:
        return None

    car_number = match.group(1)
    reason = match.group(2).strip(" -")
    mapped = driver_map.get(car_number, {})
    row = _base_row_from_listing(
        listing,
        status="parsed",
        notes=f"Parsed from FIA listing title. Car {car_number}.",
    )
    row["driver"] = mapped.get("driver", "")
    row["team"] = mapped.get("team", "")

    if listing.document_type == "summons":
        row["summons_reason"] = reason
    else:
        row["penalty_type"] = listing.document_type
        row["penalty_value"] = reason

    return row


def _read_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF enrichment requires pypdf. Install requirements.txt or rerun "
            "without --enrich-pdfs."
        ) from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def is_official_fia_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in FIA_PDF_HOSTS


def fetch_fia_pdf(
    url: str,
    *,
    get=None,
    timeout: int = 20,
    max_bytes: int = FIA_PDF_MAX_BYTES,
) -> bytes:
    """Download one official FIA PDF.

    Redirects are followed by hand so every hop is checked against the FIA
    host allowlist, and the body is streamed so an oversized response is
    rejected before it is held in memory.
    """
    get = get or requests.get
    for _ in range(5):
        if not is_official_fia_url(url):
            raise ValueError("Only official HTTPS FIA PDF URLs are accepted.")
        response = get(url, timeout=timeout, stream=True, allow_redirects=False)
        if response.status_code not in _REDIRECT_CODES:
            break
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError("FIA redirect had no location.")
        url = urljoin(url, location)
    else:
        raise ValueError("Too many FIA redirects.")
    try:
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ValueError("Expected an official PDF under 20 MB.")
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Expected an official PDF under 20 MB.")
            chunks.append(chunk)
    finally:
        response.close()
    content = b"".join(chunks)
    if not content.startswith(b"%PDF"):
        raise ValueError("Expected an official PDF under 20 MB.")
    return content


def _cache_file_for_url(cache_dir: Path, url: str) -> Path:
    # Different events reuse file names, so key the cache by the full URL.
    return cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.pdf"


def download_fia_pdf(
    url: str,
    cache_dir: str | Path | None = None,
    timeout: int = 30,
) -> bytes:
    if not is_official_fia_url(url):
        raise ValueError("Only official HTTPS FIA PDF URLs are accepted.")
    if cache_dir is not None:
        cache_path = _cache_file_for_url(Path(cache_dir), url)
        if cache_path.exists():
            return cache_path.read_bytes()

    content = fetch_fia_pdf(url, timeout=timeout)

    if cache_dir is not None:
        cache_path = _cache_file_for_url(Path(cache_dir), url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)

    return content


def enrich_fia_listing_from_pdf(
    listing: FiaDocumentListing,
    driver_map: dict[str, dict[str, str]] | None = None,
    cache_dir: str | Path | None = "data/fia_documents/cache",
    timeout: int = 30,
) -> list[dict[str, Any]]:
    if "grid" not in listing.document_type and "classification" not in listing.document_type:
        stewards_row = parse_fia_stewards_row_from_title(listing, driver_map=driver_map)
        return [stewards_row] if stewards_row is not None else []

    text = _read_pdf_text(
        download_fia_pdf(
            listing.document_url,
            cache_dir=cache_dir,
            timeout=timeout,
        )
    )
    return parse_fia_competitor_rows_from_text(
        text,
        listing=listing,
        driver_map=driver_map,
    )


def merge_fia_document_rows(
    existing: pd.DataFrame,
    new_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    for col in FIA_DOCUMENT_COLUMNS:
        if col not in existing.columns:
            existing[col] = pd.NA

    incoming = pd.DataFrame(new_rows, columns=FIA_DOCUMENT_COLUMNS)
    combined = pd.concat(
        [existing[FIA_DOCUMENT_COLUMNS], incoming],
        ignore_index=True,
    )
    combined = combined.astype("object").where(pd.notna(combined), "")
    # CSV reloads turn nullable integers into floats. 1 and 1.0 must identify
    # the same driver row on subsequent hourly refreshes.
    for column in ('grid_position','classification_position'):
        combined[column] = combined[column].map(
            lambda value: str(int(float(value))) if str(value).strip() and
            re.fullmatch(r'[-+]?\d+(?:\.0+)?',str(value).strip()) else value)
    combined['_version_published'] = combined['published_at'].where(combined['extraction_version'].ne(''),'')
    combined["_dedupe_key"] = combined.apply(
        lambda row: "|".join(
            str(row.get(col, "")).strip()
            for col in [
                "year",
                "event",
                "doc_number",
                "document_url",
                "document_type",
                "driver",
                "grid_position",
                "classification_position",
                "penalty_type",
                "summons_reason",
                "_version_published", "pdf_sha256", "extraction_version",
            ]
        ),
        axis=1,
    )
    combined = combined.drop_duplicates("_dedupe_key", keep="last")
    combined = combined.drop(columns=["_dedupe_key", "_version_published"])

    sort_columns = ["year", "event", "doc_number", "driver"]
    return combined.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def update_fia_document_index(
    *,
    year: int,
    path: str = FIA_DOCUMENT_INDEX_PATH,
    season_url: str | None = None,
    event: str | None = None,
    enrich_pdfs: bool = False,
    driver_map_path: str | None = None,
    cache_dir: str | Path | None = "data/fia_documents/cache",
    timeout: int = 30,
) -> dict[str, Any]:
    listings = fetch_fia_document_listings(
        year=year,
        season_url=season_url,
        timeout=timeout,
    )

    if event:
        event_lower = event.casefold()
        listings = [
            listing for listing in listings if listing.event.casefold() == event_lower
        ]

    rows = [listing.to_row() for listing in listings]
    enriched_count = 0
    warnings: list[str] = []

    if enrich_pdfs:
        driver_map = load_driver_map(driver_map_path)
        for listing in listings:
            try:
                enriched = enrich_fia_listing_from_pdf(
                    listing,
                    driver_map=driver_map,
                    cache_dir=cache_dir,
                    timeout=timeout,
                )
            except RuntimeError as exc:
                warnings.append(str(exc))
                break
            except requests.RequestException as exc:
                warnings.append(f"Skipped {listing.document_url}: {exc}")
                continue

            rows.extend(enriched)
            enriched_count += len(enriched)

    ensure_fia_document_index(path)
    existing = pd.read_csv(path)
    output = merge_fia_document_rows(existing, rows)
    output.to_csv(path, index=False)

    return {
        "path": path,
        "listings": len(listings),
        "rows_written": len(rows),
        "enriched_rows": enriched_count,
        "warnings": warnings,
    }
