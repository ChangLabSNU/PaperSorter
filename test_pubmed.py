"""Lightweight sanity tests for the PubMed lookup helper."""

import unittest

from PaperSorter.utils import pubmed_lookup


class MockResponse:
    """Fake requests response object that returns predefined payloads."""

    def __init__(self, payload=None, *, text=None):
        self._payload = payload
        self._text = text
        self.status_code = 200

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload configured")
        return self._payload

    @property
    def text(self):  # pragma: no cover - simple delegation
        return self._text or ""

    @property
    def content(self):  # pragma: no cover - simple delegation
        return (self._text or "").encode("utf-8")

    def raise_for_status(self):
        return None


class FakeSession:
    """Stub requests.Session that records calls and returns queued responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        try:
            return self._responses.pop(0)
        except IndexError as exc:  # pragma: no cover - defensive guard
            raise AssertionError("Unexpected extra HTTP call") from exc

    def close(self):  # pragma: no cover - compatibility method
        return None


class SearchPubMedByTitleTests(unittest.TestCase):
    def test_fetches_summary_data_and_formats_articles(self):
        session = FakeSession(
            responses=[
                MockResponse({"esearchresult": {"idlist": ["12345", "67890"]}}),
                MockResponse(
                    {
                        "result": {
                            "uids": ["12345", "67890"],
                            "12345": {
                                "uid": "12345",
                                "title": "Genome editing advances",
                                "fulljournalname": "Nature Genetics",
                                "pubdate": "2024 Jan",
                                "articleids": [
                                    {"idtype": "pubmed", "value": "12345"},
                                    {"idtype": "doi", "value": "10.1000/genome"},
                                ],
                                "authors": [
                                    {
                                        "name": "Doe J",
                                        "lastname": "Doe",
                                        "forename": "John",
                                        "initials": "JD",
                                        "affiliation": "Genome Lab",
                                    }
                                ],
                            },
                            "67890": {
                                "uid": "67890",
                                "title": "Genome editing advances",
                                "source": "Science",
                                "pubdate": "2024 Feb",
                                "articleids": [
                                    {"idtype": "pubmed", "value": "67890"},
                                ],
                                "authors": [],
                            },
                        }
                    }
                ),
            ]
        )

        articles = pubmed_lookup.search_pubmed_by_title(
            "Genome editing advances",
            max_results=2,
            session=session,
            timeout=5.0,
            tool="papersorter",
            email="papersorter@example.org",
        )

        self.assertEqual(len(articles), 2)
        first = articles[0]
        self.assertEqual(first.pmid, "12345")
        self.assertEqual(first.title, "Genome editing advances")
        self.assertEqual(first.journal, "Nature Genetics")
        self.assertEqual(first.publication_date, "2024 Jan")
        self.assertEqual(first.doi, "10.1000/genome")
        self.assertEqual(first.url, "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertEqual(len(first.authors), 1)
        author = first.authors[0]
        self.assertEqual(author.last_name, "Doe")
        self.assertEqual(author.fore_name, "John")
        self.assertEqual(author.affiliation, "Genome Lab")

        self.assertEqual(articles[1].journal, "Science")

        esearch_call, esummary_call = session.calls
        self.assertEqual(
            esearch_call[0],
            f"{pubmed_lookup.EUTILS_BASE_URL}/esearch.fcgi",
        )
        self.assertEqual(esummary_call[0], f"{pubmed_lookup.EUTILS_BASE_URL}/esummary.fcgi")
        self.assertEqual(esearch_call[1]["term"], "Genome editing advances[Title]")
        self.assertEqual(esummary_call[1]["id"], "12345,67890")
        self.assertEqual(esearch_call[2], 5.0)

    def test_rejects_empty_title(self):
        with self.assertRaises(ValueError):
            pubmed_lookup.search_pubmed_by_title("   ")

    def test_returns_empty_list_when_max_results_zero(self):
        session = FakeSession(responses=[])
        result = pubmed_lookup.search_pubmed_by_title(
            "Anything",
            max_results=0,
            session=session,
        )
        self.assertEqual(result, [])
        self.assertEqual(session.calls, [])


class FindPerfectTitleMatchesTests(unittest.TestCase):
    def test_filters_to_titles_matching_after_normalization(self):
        session = FakeSession(
            responses=[
                MockResponse({"esearchresult": {"idlist": ["111", "222"]}}),
                MockResponse(
                    {
                        "result": {
                            "uids": ["111", "222"],
                            "111": {
                                "uid": "111",
                                "title": "Genome editing advances",
                                "fulljournalname": "Nature Genetics",
                                "pubdate": "2023 Dec",
                                "articleids": [
                                    {"idtype": "pubmed", "value": "111"},
                                ],
                                "authors": [],
                            },
                            "222": {
                                "uid": "222",
                                "title": "Genome editing update",
                                "fulljournalname": "Science",
                                "pubdate": "2024 Jan",
                                "articleids": [
                                    {"idtype": "pubmed", "value": "222"},
                                ],
                                "authors": [],
                            },
                        }
                    }
                ),
            ]
        )

        matches = pubmed_lookup.find_perfect_title_matches(
            "Genome Editing Advances!!!",
            max_results=2,
            session=session,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].pmid, "111")

    def test_requires_alphanumeric_characters(self):
        with self.assertRaises(ValueError):
            pubmed_lookup.find_perfect_title_matches("!!!")


class FetchPubMedArticlesTests(unittest.TestCase):
    def test_fetch_pubmed_articles_parses_xml_payload(self):
        xml_payload = """
            <PubmedArticleSet>
              <PubmedArticle>
                <MedlineCitation>
                  <PMID>111</PMID>
                  <Article>
                    <ArticleTitle>Genome editing advances</ArticleTitle>
                    <Abstract>
                      <AbstractText Label="Background">CRISPR techniques.</AbstractText>
                      <AbstractText>Significant improvements reported.</AbstractText>
                    </Abstract>
                    <AuthorList>
                      <Author>
                        <LastName>Doe</LastName>
                        <ForeName>John</ForeName>
                        <Initials>JD</Initials>
                        <AffiliationInfo>
                          <Affiliation>Genome Lab</Affiliation>
                        </AffiliationInfo>
                      </Author>
                    </AuthorList>
                    <Journal>
                      <JournalIssue>
                        <PubDate>
                          <Year>2024</Year>
                          <Month>Feb</Month>
                          <Day>15</Day>
                        </PubDate>
                      </JournalIssue>
                      <Title>Nature Genetics</Title>
                    </Journal>
                  </Article>
                </MedlineCitation>
                <PubmedData>
                  <ArticleIdList>
                    <ArticleId IdType="pubmed">111</ArticleId>
                    <ArticleId IdType="doi">10.1000/genome</ArticleId>
                  </ArticleIdList>
                </PubmedData>
              </PubmedArticle>
            </PubmedArticleSet>
        """

        session = FakeSession([MockResponse(text=xml_payload)])
        result = pubmed_lookup.fetch_pubmed_articles(["111"], session=session)

        self.assertIn("111", result)
        article = result["111"]
        self.assertEqual(article.title, "Genome editing advances")
        self.assertEqual(article.journal, "Nature Genetics")
        self.assertEqual(article.doi, "10.1000/genome")
        self.assertEqual(article.url, "https://pubmed.ncbi.nlm.nih.gov/111/")
        self.assertEqual(article.publication_date, "2024-02-15")
        self.assertIsNotNone(article.published)
        self.assertEqual(article.published.year, 2024)
        self.assertEqual(len(article.authors), 1)
        self.assertEqual(article.authors[0].display_name(), "John Doe")
        self.assertIn("CRISPR techniques.", article.abstract)
        self.assertIn("Significant improvements", article.abstract)

        (efetch_call,) = session.calls
        self.assertIn("efetch.fcgi", efetch_call[0])


if __name__ == "__main__":
    unittest.main()
