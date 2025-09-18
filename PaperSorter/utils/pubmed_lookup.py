"""Utilities for querying the PubMed REST API by article title."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests
import xml.etree.ElementTree as ET


log = logging.getLogger(__name__)

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT = 10.0

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class PubMedLookupError(Exception):
    """Raised when the PubMed API request cannot be completed."""


@dataclass
class PubMedAuthor:
    """Author information returned by the PubMed summary endpoint."""

    name: Optional[str]
    last_name: Optional[str]
    fore_name: Optional[str]
    initials: Optional[str]
    affiliation: Optional[str]

    @classmethod
    def from_summary(cls, payload: dict) -> "PubMedAuthor":
        """Create an author object from an ESummary author payload."""

        if not payload:
            return cls(None, None, None, None, None)

        return cls(
            name=payload.get("name"),
            last_name=payload.get("lastname") or payload.get("lastName"),
            fore_name=payload.get("forename") or payload.get("foreName"),
            initials=payload.get("initials"),
            affiliation=payload.get("affiliation"),
        )

    def display_name(self) -> Optional[str]:
        """Return a best-effort human-readable author name."""

        if self.name:
            return self.name

        parts = []
        if self.fore_name:
            parts.append(self.fore_name)
        if self.last_name:
            parts.append(self.last_name)
        if not parts and self.initials:
            parts.append(self.initials)
        return " ".join(parts) or None


@dataclass
class PubMedArticle:
    """Structured representation of an article retrieved from PubMed."""

    pmid: str
    title: str
    journal: Optional[str]
    publication_date: Optional[str]
    doi: Optional[str]
    authors: Sequence[PubMedAuthor]
    url: Optional[str]
    abstract: Optional[str] = None
    published: Optional[datetime] = None

    @classmethod
    def from_summary(cls, payload: dict) -> "PubMedArticle":
        """Create a :class:`PubMedArticle` from an ESummary response payload."""

        article_ids = payload.get("articleids", [])
        doi = _extract_article_id(article_ids, "doi")
        url = _extract_article_id(article_ids, "pubmed") or _extract_article_id(article_ids, "pii")
        if url and not url.startswith("http"):
            url = f"https://pubmed.ncbi.nlm.nih.gov/{url}/"

        authors = tuple(PubMedAuthor.from_summary(author) for author in payload.get("authors", []))

        return cls(
            pmid=str(payload["uid"]),
            title=payload.get("title", ""),
            journal=payload.get("fulljournalname") or payload.get("source"),
            publication_date=payload.get("pubdate"),
            doi=doi,
            authors=authors,
            url=url,
            abstract=None,
            published=None,
        )


def _extract_article_id(article_ids: Iterable[dict], target_type: str) -> Optional[str]:
    for item in article_ids:
        if item.get("idtype") == target_type:
            return item.get("value")
    return None


def _normalize_title(text: str) -> str:
    """Normalize a title for matching: lowercase and strip non-alphanumerics."""

    cleaned = re.sub(r"[^a-z0-9]", "", text.lower())
    return cleaned


def _text_content(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _format_abstract(abstract_element: Optional[ET.Element]) -> Optional[str]:
    if abstract_element is None:
        return None

    parts: List[str] = []
    for abstract_text in abstract_element.findall("AbstractText"):
        text = _text_content(abstract_text)
        if not text:
            continue

        label = abstract_text.attrib.get("Label") or abstract_text.attrib.get("Nlmuniqueid")
        if label:
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)

    return "\n\n".join(parts) if parts else None


def _parse_pubmed_pubdate(pub_date_element: Optional[ET.Element]) -> Tuple[Optional[str], Optional[datetime]]:
    if pub_date_element is None:
        return None, None

    year_text = _text_content(pub_date_element.find("Year"))
    month_text = _text_content(pub_date_element.find("Month"))
    day_text = _text_content(pub_date_element.find("Day"))

    if not year_text:
        medline_date = _text_content(pub_date_element.find("MedlineDate"))
        return _parse_medline_date(medline_date)

    try:
        year = int(year_text)
    except ValueError:
        return None, None

    month = 1
    if month_text:
        month_key = month_text.strip().lower()
        month = _MONTHS.get(month_key[:3], 1)

    day = 1
    if day_text:
        try:
            day = int(day_text)
        except ValueError:
            day = 1

    try:
        published = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        published = None

    if day_text:
        date_string = f"{year:04d}-{month:02d}-{day:02d}"
    elif month_text:
        date_string = f"{year:04d}-{month:02d}"
    else:
        date_string = f"{year:04d}"

    return date_string, published


def _parse_medline_date(medline_date: str) -> Tuple[Optional[str], Optional[datetime]]:
    medline_date = medline_date.strip()
    if not medline_date:
        return None, None

    match = re.search(r"(19|20)\d{2}", medline_date)
    if not match:
        return medline_date, None

    year = int(match.group(0))
    try:
        published = datetime(year, 1, 1, tzinfo=timezone.utc)
    except ValueError:
        published = None

    return medline_date, published


def fetch_pubmed_articles(
    ids: Sequence[str],
    *,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT,
    tool: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, PubMedArticle]:
    """Fetch detailed article records via EFetch for the given PubMed IDs."""

    id_list = [str(i) for i in ids if i]
    if not id_list:
        return {}

    http = session or requests.Session()
    close_session = session is None

    params = {
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(id_list),
    }
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    if email:
        params["email"] = email

    try:
        response = http.get(f"{EUTILS_BASE_URL}/efetch.fcgi", params=params, timeout=timeout)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        log.debug("PubMed EFetch error", exc_info=exc)
        raise PubMedLookupError("Failed to fetch PubMed article details") from exc
    finally:
        if close_session:
            http.close()

    articles: Dict[str, PubMedArticle] = {}
    for article_element in root.findall("PubmedArticle"):
        parsed = _parse_article_xml(article_element)
        if parsed:
            articles[parsed.pmid] = parsed

    return articles


def _parse_article_xml(article_element: ET.Element) -> Optional[PubMedArticle]:
    pmid = _text_content(article_element.find("MedlineCitation/PMID"))
    if not pmid:
        return None

    citation = article_element.find("MedlineCitation/Article")
    if citation is None:
        return None

    title = _text_content(citation.find("ArticleTitle"))
    journal = _text_content(citation.find("Journal/Title")) or _text_content(article_element.find("MedlineCitation/MedlineJournalInfo/MedlineTA")) or None

    abstract = _format_abstract(citation.find("Abstract"))

    author_nodes = citation.findall("AuthorList/Author")
    authors: List[PubMedAuthor] = []
    for author in author_nodes:
        collective = _text_content(author.find("CollectiveName"))
        if collective:
            authors.append(PubMedAuthor(name=collective, last_name=None, fore_name=None, initials=None, affiliation=None))
            continue

        authors.append(
            PubMedAuthor(
                name=None,
                last_name=_text_content(author.find("LastName")) or None,
                fore_name=_text_content(author.find("ForeName")) or None,
                initials=_text_content(author.find("Initials")) or None,
                affiliation=_text_content(author.find("AffiliationInfo/Affiliation")) or None,
            )
        )

    article_ids = []
    for id_node in article_element.findall("PubmedData/ArticleIdList/ArticleId"):
        article_ids.append({
            "idtype": id_node.attrib.get("IdType"),
            "value": id_node.text,
        })

    doi = _extract_article_id(article_ids, "doi")
    url = _extract_article_id(article_ids, "pubmed") or _extract_article_id(article_ids, "pii")
    if url and not str(url).startswith("http"):
        url = f"https://pubmed.ncbi.nlm.nih.gov/{url}/"

    pub_date_element = citation.find("Journal/JournalIssue/PubDate")
    publication_date, published = _parse_pubmed_pubdate(pub_date_element)

    return PubMedArticle(
        pmid=pmid,
        title=title,
        journal=journal,
        publication_date=publication_date,
        doi=doi,
        authors=tuple(authors),
        url=url,
        abstract=abstract,
        published=published,
    )


def attach_article_details(
    articles: Sequence[PubMedArticle],
    *,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT,
    tool: Optional[str] = None,
    email: Optional[str] = None,
) -> List[PubMedArticle]:
    """Hydrate summary articles with full EFetch details when available."""

    if not articles:
        return list(articles)

    details = fetch_pubmed_articles(
        [article.pmid for article in articles],
        api_key=api_key,
        session=session,
        timeout=timeout,
        tool=tool,
        email=email,
    )

    enriched: List[PubMedArticle] = []
    for article in articles:
        detailed = details.get(article.pmid)
        if detailed:
            article.title = detailed.title or article.title
            article.journal = detailed.journal or article.journal
            article.publication_date = detailed.publication_date or article.publication_date
            article.doi = detailed.doi or article.doi
            article.authors = detailed.authors or article.authors
            article.url = detailed.url or article.url
            article.abstract = detailed.abstract or article.abstract
            article.published = detailed.published or article.published
        enriched.append(article)

    return enriched


def search_pubmed_by_title(
    title: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT,
    tool: Optional[str] = None,
    email: Optional[str] = None,
) -> List[PubMedArticle]:
    """Search PubMed articles by exact or partial title match.

    This helper uses the NCBI E-utilities REST API. It first performs an
    ``esearch`` query scoped to the article title field, then fetches
    metadata through ``esummary`` for the returned PubMed IDs.

    Args:
        title: Title text to search for.
        max_results: Maximum number of records to return (default: 5).
        api_key: Optional NCBI API key for higher rate limits.
        session: Optional requests session to reuse connections.
        timeout: Per-request timeout in seconds (default: 10 seconds).
        tool: Optional identifier for your application, passed to NCBI.
        email: Optional contact email, recommended by NCBI E-utilities.

    Returns:
        List of :class:`PubMedArticle` objects sorted by relevance.

    Raises:
        PubMedLookupError: If requests fail or responses are malformed.
    """

    title = title.strip()
    if not title:
        raise ValueError("title must not be empty")

    if max_results <= 0:
        return []

    http = session or requests.Session()
    close_session = session is None

    try:
        id_list = _search_ids(
            http,
            title=title,
            max_results=max_results,
            api_key=api_key,
            timeout=timeout,
            tool=tool,
            email=email,
        )
        if not id_list:
            return []

        summaries = _fetch_summaries(
            http,
            ids=id_list,
            api_key=api_key,
            timeout=timeout,
            tool=tool,
            email=email,
        )

        articles = [PubMedArticle.from_summary(summary) for summary in summaries]
        return articles
    except requests.RequestException as exc:
        message = "Failed to reach PubMed API"
        log.debug("PubMed API request error", exc_info=exc)
        raise PubMedLookupError(message) from exc
    finally:
        if close_session:
            http.close()


def _search_ids(
    http: requests.Session,
    *,
    title: str,
    max_results: int,
    api_key: Optional[str],
    timeout: float,
    tool: Optional[str],
    email: Optional[str],
) -> Sequence[str]:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": max_results,
        "term": f"{title}[Title]",
        "sort": "relevance",
    }
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    if email:
        params["email"] = email

    response = http.get(f"{EUTILS_BASE_URL}/esearch.fcgi", params=params, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    try:
        id_list = payload["esearchresult"]["idlist"]
    except (KeyError, TypeError) as exc:
        raise PubMedLookupError("Unexpected esearch response structure") from exc

    return list(id_list)


def _fetch_summaries(
    http: requests.Session,
    *,
    ids: Sequence[str],
    api_key: Optional[str],
    timeout: float,
    tool: Optional[str],
    email: Optional[str],
) -> Sequence[dict]:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "id": ",".join(ids),
    }
    if api_key:
        params["api_key"] = api_key
    if tool:
        params["tool"] = tool
    if email:
        params["email"] = email

    response = http.get(f"{EUTILS_BASE_URL}/esummary.fcgi", params=params, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    try:
        result = payload["result"]
        summaries = [result[uid] for uid in result["uids"]]
    except (KeyError, TypeError) as exc:
        raise PubMedLookupError("Unexpected esummary response structure") from exc

    return summaries


def find_perfect_title_matches(
    title: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    api_key: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: float = DEFAULT_TIMEOUT,
    tool: Optional[str] = None,
    email: Optional[str] = None,
) -> List[PubMedArticle]:
    """Return only articles whose normalized titles match ``title`` exactly."""

    normalized_query = _normalize_title(title)
    if not normalized_query:
        raise ValueError("title must contain alphanumeric characters")

    candidates = search_pubmed_by_title(
        title,
        max_results=max_results,
        api_key=api_key,
        session=session,
        timeout=timeout,
        tool=tool,
        email=email,
    )

    return [article for article in candidates if _normalize_title(article.title) == normalized_query]
