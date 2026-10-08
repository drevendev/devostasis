"""DEV-PAGES: contradictory provider metadata cannot claim complete selection."""

import pytest

from devostasis.workscope.collect import Client


def page(items, **headers):
    return [{"id": i} for i in items], {k.replace("_", "-"): str(v) for k, v in headers.items()}


def collect(pages, provider="gitlab", key=None):
    client = Client(provider, "https://example.invalid/api", max_pages=3)
    client.get = lambda path, params: pages[params["page"] - 1]
    return client.pages("/items", key=key)


@pytest.mark.parametrize("headers,reason", [
    ({"x_total": 101, "x_next_page": ""}, "PAGINATION_TOTAL_MISMATCH"),
    ({"x_total": 99, "x_next_page": ""}, "PAGINATION_TOTAL_MISMATCH"),
    ({"x_page": 2, "x_next_page": ""}, "PAGINATION_PAGE_MISMATCH"),
    ({"x_per_page": 50, "x_next_page": ""}, "PAGINATION_PAGE_MISMATCH"),
    ({"x_next_page": 3}, "PAGINATION_PAGE_MISMATCH"),
    ({"x_next_page": "https://foreign.invalid/?token=x"}, "INVALID_PAGINATION_HEADER"),
    ({"x_total": "-1", "x_next_page": ""}, "INVALID_PAGINATION_HEADER"),
    ({"x_total": "many", "x_next_page": ""}, "INVALID_PAGINATION_HEADER"),
    ({"x_total": 100, "x_total_pages": 2, "x_next_page": ""}, "PAGINATION_TOTAL_MISMATCH"),
    ({"x_total": 100, "x_next_page": 2}, "PAGINATION_TOTAL_MISMATCH"),
])
def test_work_pagination_contradictory_headers_preserve_observed_partial_items(headers, reason):
    value = collect([page(range(100), **headers)])
    assert value["status"] == "PARTIAL" and len(value["items"]) == 100
    assert value["reasons"] == [reason]


def test_work_pagination_changed_total_between_pages_is_partial():
    value = collect([page(range(100), x_total=101, x_next_page=2), page([100], x_total=102, x_next_page="")])
    assert value["status"] == "PARTIAL" and value["reasons"] == ["PAGINATION_TOTAL_SHIFT"]


@pytest.mark.parametrize("pages", [
    [page(range(100), x_page=1, x_total=100, x_total_pages=1, x_next_page="")],
    [page(range(100)), page([])],
    [page(range(100), x_total=101, x_next_page=2), page([100], x_total=101, x_next_page="")],
    [page([], x_total=0, x_total_pages=0, x_next_page="")],
])
def test_work_pagination_valid_exact_full_empty_and_header_absent_responses_are_complete(pages):
    assert collect(pages)["status"] == "COMPLETE"


@pytest.mark.parametrize("total", [1001, True, -1, "1"])
def test_work_pagination_github_result_caps_and_invalid_totals_are_not_complete(total):
    result = collect([({"items": [{"id": 1}], "total_count": total}, {})], "github", "items")
    assert result["status"] == "PARTIAL"
