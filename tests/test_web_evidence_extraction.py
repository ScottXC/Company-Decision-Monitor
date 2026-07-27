from __future__ import annotations

from cdm_desktop.public_api.content_extractor import (
    classify_content,
    extract_pdf_evidence,
    extract_web_evidence,
)

HTML = """
<!doctype html>
<html lang="en"><head>
  <title>Example Investor Relations</title>
  <link rel="canonical" href="/investors/overview?utm_source=test">
  <meta name="description" content="Official investor information">
  <meta property="og:title" content="Example IR">
  <meta property="og:description" content="Official releases and reports">
  <meta property="og:site_name" content="Example Corp">
  <meta property="article:published_time" content="2026-07-01T10:00:00Z">
  <meta property="article:modified_time" content="2026-07-02T10:00:00Z">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Corporation",
        "name": "Example Corp",
        "alternateName": "Example",
        "legalName": "Example Corporation",
        "url": "https://example.com/",
        "logo": {"url": "https://example.com/logo.png"},
        "address": {
          "@type": "PostalAddress",
          "streetAddress": "1 Main Street",
          "addressLocality": "Singapore",
          "postalCode": "000001",
          "addressCountry": "SG"
        },
        "telephone": "+65 1234 5678",
        "email": "ir@example.com",
        "foundingDate": "2001-01-02",
        "sameAs": ["https://www.wikidata.org/wiki/Q1"]
      },
      {
        "@type": "NewsArticle",
        "headline": "Example results",
        "datePublished": "2026-07-01T10:00:00Z",
        "author": {"name": "Investor Relations"}
      }
    ]
  }
  </script>
</head><body>
  <nav>Home Products Investors Careers</nav>
  <div class="cookie-banner">Accept all cookies</div>
  <main>
    <h1>Investor Relations</h1>
    <h2>Latest results</h2>
    <p>Example Corporation publishes verified financial information here.</p>
    <p>Example Corporation publishes verified financial information here.</p>
    <a href="/press-releases/latest">Latest press release</a>
  </main>
  <footer>Footer navigation and legal links</footer>
</body></html>
"""


def test_content_extractor_metadata_json_ld_cleaned_text_and_links() -> None:
    item = extract_web_evidence(
        HTML,
        source_url="https://example.com/investors",
        company_id="company:1",
        company_name="Example",
        is_official_domain=True,
    )

    assert item.title == "Example IR"
    assert item.meta_description == "Official investor information"
    assert item.og_description == "Official releases and reports"
    assert item.h1 == "Investor Relations"
    assert item.site_name == "Example Corp"
    assert item.author == "Investor Relations"
    assert item.published_at == "2026-07-01T10:00:00Z"
    assert item.modified_at == "2026-07-02T10:00:00Z"
    assert item.language == "en"
    assert item.canonical_url == "https://example.com/investors/overview"
    assert item.content_type == "investor_relations"
    assert item.display_mode == "full_cleaned_text"
    assert "verified financial information" in item.cleaned_text
    assert item.cleaned_text.count("verified financial information") == 1
    assert "Home Products" not in item.cleaned_text
    assert "Accept all cookies" not in item.cleaned_text
    assert "Footer navigation" not in item.cleaned_text
    assert item.headings == ["Investor Relations", "Latest results"]
    assert any(link["url"].endswith("/press-releases/latest") for link in item.links)
    organization = item.structured_data["organization"]
    assert organization["legalName"] == "Example Corporation"
    assert organization["logo"] == "https://example.com/logo.png"
    assert "1 Main Street" in organization["address"]
    assert item.content_hash


def test_third_party_content_is_excerpt_only_and_does_not_store_full_body() -> None:
    item = extract_web_evidence(
        HTML.replace("/investors", "/news"),
        source_url="https://media.example/news/story",
        is_official_domain=False,
    )

    assert item.display_mode == "excerpt_only"
    assert item.cleaned_text == ""
    assert item.content_snippet
    assert len(item.content_snippet) <= 300
    assert len(item.extracted_text_preview) <= 800
    assert item.content_type == "third_party_news"


def test_pdf_is_metadata_only_without_body() -> None:
    item = extract_pdf_evidence(
        source_url="https://example.com/reports/annual-report-2025.pdf",
        company_id="company:1",
        is_official_domain=True,
    )

    assert item.content_type == "annual_report"
    assert item.display_mode == "metadata_only"
    assert not item.cleaned_text
    assert "未在此版本下载或解析" in item.content_snippet


def test_deterministic_content_classification() -> None:
    assert classify_content("https://example.com/press-releases/a") == "press_release"
    assert classify_content("https://example.com/announcements/a") == "announcement"
    assert classify_content("https://example.com/reports/q2.pdf") == "financial_report"
    assert classify_content("https://example.com/careers", is_official_domain=True) == "careers"
    assert classify_content("https://example.com/", is_official_domain=True) == "company_homepage"
