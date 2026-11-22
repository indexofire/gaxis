"""Repository link extraction from paper text."""

from gaxis.acquire.repo import find_repository_urls


def test_github_links_are_found_and_deduplicated() -> None:
    text = (
        "Code: https://github.com/lab/figures and again github.com/lab/figures. "
        "Data at https://zenodo.org/record/1234567."
    )
    links = find_repository_urls(text)
    urls = [link.url for link in links]
    assert "https://github.com/lab/figures" in urls
    assert "https://zenodo.org/records/1234567" in urls
    assert len(urls) == len(set(urls))


def test_issue_and_blob_urls_are_ignored() -> None:
    text = "see https://github.com/lab/figures/issues/3 and https://github.com/lab/figures/blob/main/x.py"
    assert find_repository_urls(text) == []


def test_gitlab_subgroup_path_is_trimmed_to_the_project() -> None:
    links = find_repository_urls("mirror: https://gitlab.com/group/sub/figrepo ")
    assert links
    assert links[0].url == "https://gitlab.com/group/sub"


def test_trailing_punctuation_does_not_leak_into_the_url() -> None:
    links = find_repository_urls("(code: https://github.com/lab/figs).")
    assert [link.url for link in links] == ["https://github.com/lab/figs"]


def test_plain_text_without_links_returns_empty() -> None:
    assert find_repository_urls("no repositories here, only prose") == []


def test_wrapped_urls_from_pdf_text_are_joined() -> None:
    text = (
        "Analysis scripts and data are available at https://github.\n"
        "com/SCAUJunhaoPeng/Epidemiological-Investigation-of-Salmonella-in-\n"
        "the-Pork-Supply-chain.\nReceived: 10 March 2026"
    )
    links = find_repository_urls(text)
    assert [link.url for link in links] == [
        "https://github.com/SCAUJunhaoPeng/Epidemiological-Investigation-of-Salmonella-in-the-Pork-Supply-chain"
    ]
    assert links[0].owner == "SCAUJunhaoPeng"
