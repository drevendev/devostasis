"""Read-only GitHub REST adapter.

Every endpoint failure becomes an explicit observation status instead of a
value: tier limitations are UNAVAILABLE, authorization denials are FORBIDDEN,
transient failures are ERROR, and a capped pagination is PARTIAL. The adapter
performs no mutation of any kind.

Planning targets come from GitHub milestones or from a structured register
file in the repository; debt items come from a configured label mapping or
from a register file. Change requests are linked to targets either by their
milestone or by an explicit marker line (``Target: <id>``) in their text.
"""

from __future__ import annotations

import base64
import binascii
import http.client
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .. import timeutil
from ..config import ResolvedProject
from ..normalize import (
    CI_CONFIGURED,
    CI_REVISIONS,
    INV_BRANCHES,
    INV_COMMITS,
    INV_CRS,
    INV_DEBT_REGISTER,
    INV_ISSUES,
    INV_RELEASES,
    INV_REPO,
    INV_TARGETS,
)
from ..observations import AVAILABLE, ERROR, FORBIDDEN, PARTIAL, UNAVAILABLE, UNKNOWN, Observation, ObservationSet, Receipt
from ..policy import FLOW, INTEGRITY, PULSE
from . import github_ci
from .cache import ConditionalCache

ADAPTER_VERSION = "devostasis.github.v1"
API_BASE = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 10
MAX_COMMIT_PAGES = 30
MAX_CHANGE_REQUEST_PAGES = 20
MAX_ISSUE_PAGES = 20
MAX_RUN_PAGES = 20
MAX_BRANCH_PAGES = 2
MAX_BRANCH_HEAD_LOOKUPS = 60
MAX_ATTEMPT_LOOKUPS = 60
MAX_ATTEMPTS_PER_RUN = 5
MAX_SUITE_REVISIONS = 100
MAX_SUITE_PAGES = 3
MAX_RELEASES = 30
MAX_REGISTER_BYTES = 1_000_000

TARGETS_REGISTER_SCHEMA = "devostasis.targets.v1"
DEBT_REGISTER_SCHEMA = "devostasis.debt.v1"


class CollectionError(Exception):
    """The subject could not be identified; no observation set can be produced."""


@dataclass
class ApiFailure(Exception):
    status_code: int
    observation_status: str
    reason_code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"HTTP {self.status_code} {self.reason_code}: {self.message}"


@dataclass
class NetworkFailure(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class RegisterError(Exception):
    """A register file exists but is not a valid register."""


def classify_http_error(status: int, body: Any, headers: dict[str, str]) -> tuple[str, str, bool]:
    """Map an HTTP failure to (observation status, reason code, retryable)."""
    message = ""
    if isinstance(body, dict):
        message = str(body.get("message", ""))
    lowered = message.lower()
    if status == 401:
        return FORBIDDEN, "UNAUTHENTICATED", False
    if status == 403:
        if "rate limit" in lowered or headers.get("x-ratelimit-remaining") == "0":
            return ERROR, "RATE_LIMITED", True
        if "upgrade to github" in lowered or "github pro" in lowered or "not available" in lowered:
            return UNAVAILABLE, "TIER_UNAVAILABLE", False
        return FORBIDDEN, "FORBIDDEN", False
    if status == 404:
        return UNAVAILABLE, "NOT_FOUND", False
    if status == 410:
        return UNAVAILABLE, "DISABLED", False
    if status == 429:
        return ERROR, "RATE_LIMITED", True
    if status >= 500:
        return ERROR, "PROVIDER_ERROR", True
    return ERROR, f"HTTP_{status}", False


class RedirectRefused(urllib.error.URLError):
    """A redirect the transport will not follow with the caller's credential."""


class _SameOriginRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to the configured API origin.

    urllib copies every header of the original request onto the redirected
    one, the bearer token included. A redirect to another origin would hand
    the credential to whoever answers there, and a downgrade to HTTP would
    send it in the clear, so both are refused as a declared transport failure
    (PV-AUDIT-GITHUB-REDIRECT-AUTH-001). The API's own redirects, such as a
    renamed repository, stay on the origin and still work.
    """

    def __init__(self, origin: str) -> None:
        super().__init__()
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - urllib's signature
        target = urllib.parse.urlsplit(newurl)
        if f"{target.scheme}://{target.netloc}".lower() != self.origin:
            raise RedirectRefused(f"redirect to {newurl} refused: it leaves the API origin {self.origin}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibTransport:
    """Minimal HTTPS transport on the standard library."""

    def __init__(self, token: str | None, api_base: str = API_BASE, user_agent: str = "devostasis/0.1", timeout: int = 30) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout
        parts = urllib.parse.urlsplit(self.api_base)
        self.origin = f"{parts.scheme}://{parts.netloc}".lower()
        self._opener = urllib.request.build_opener(_SameOriginRedirects(self.origin))

    def _open(self, request: urllib.request.Request):
        return self._opener.open(request, timeout=self.timeout)

    def get(self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
        url = self.api_base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, method="GET")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", self.user_agent)
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with self._open(request) as response:
                raw = response.read()
                headers = {k.lower(): v for k, v in response.headers.items()}
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else None
                except (ValueError, RecursionError) as exc:
                    # A successful status with a body we cannot read is a
                    # provider failure, not a Python error: it has to reach the
                    # collector as a declared status like every other failure.
                    # A body nested beyond the decoder's depth is one of them.
                    raise ApiFailure(response.status, ERROR, "MALFORMED_RESPONSE", f"{path} answered {response.status} with a body that is not readable JSON: {type(exc).__name__}") from exc
                return response.status, headers, body
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            try:
                raw = exc.read()
            except (http.client.HTTPException, TimeoutError, OSError):
                # The status and headers arrived; the body did not. The status
                # is what classifies an error, so it is kept without a body.
                return exc.code, headers, None
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (ValueError, RecursionError):
                body = {"message": raw.decode("utf-8", "replace")[:200]}
            return exc.code, headers, body
        except RedirectRefused as exc:
            raise ApiFailure(0, ERROR, "REDIRECT_REFUSED", str(exc), False) from exc
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
            # http.client.IncompleteRead (a body cut off mid-read) and
            # BadStatusLine are not OSErrors; they are the same network failure.
            raise NetworkFailure(f"network failure for {path}: {type(exc).__name__}: {exc}") from exc


PAGINATION_CAPPED = "PAGINATION_CAPPED"
# A listing that repeated a row between pages moved while it was read: rows may also be missing.
LISTING_SHIFTED = "LISTING_SHIFTED"
BUDGET_EXHAUSTED = "REQUEST_BUDGET_EXHAUSTED"
NOT_MODIFIED = 304


@dataclass(frozen=True)
class RetryPolicy:
    """When to wait for a provider and when to stop waiting.

    A primary rate limit resets on the hour, so waiting it out inside a run is
    not patience, it is a hang. Short waits, which is what a secondary limit or
    a transient error asks for, are worth taking; anything longer becomes an
    explicit RATE_LIMITED observation and the run moves on.
    """

    attempts: int = 3
    max_single_wait_seconds: int = 30
    total_wait_budget_seconds: int = 120
    backoff_seconds: tuple[int, ...] = (1, 2, 4)


def _header_seconds(raw: str) -> int | None:
    """A numeric header value as whole seconds, or None when it cannot be read as one.

    ``float`` accepts ``inf`` and overflowing exponents that ``int`` then
    refuses with OverflowError; a wait hint that cannot be read is not a
    reason to raise past the provider boundary, it is no hint at all
    (PV-AUDIT-GITHUB-RETRY-HEADER-001).
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    try:
        return int(value)
    except (OverflowError, ValueError):
        return None


def retry_after_seconds(headers: dict[str, str], now: float | None = None) -> int | None:
    """What the provider asked us to wait, from Retry-After or the rate-limit reset; None when unreadable."""
    raw = headers.get("retry-after")
    if raw:
        seconds = _header_seconds(raw)
        return None if seconds is None else max(seconds, 0)
    if headers.get("x-ratelimit-remaining") == "0" and headers.get("x-ratelimit-reset"):
        reset = _header_seconds(headers["x-ratelimit-reset"])
        if reset is None:
            return None
        return max(reset - int(now if now is not None else time.time()), 0)
    return None


class RequestBudgetExhausted(ApiFailure):
    """The run reached its request budget; the evidence it would have fetched is UNKNOWN.

    It is an ApiFailure so that every collector already turns it into an
    explicit observation instead of aborting the run: nothing failed and
    nothing is forbidden, we simply chose not to look, and a value we did not
    look for cannot be proven.
    """

    def __init__(self, budget: int) -> None:
        super().__init__(0, UNKNOWN, BUDGET_EXHAUSTED, f"request budget of {budget} reached", False)


class GitHubClient:
    """Read-only client with conditional requests, bounded retries and a request budget.

    Three limits, all optional and all honest when they bite:

    * a conditional cache replays a body the provider says has not changed; a
      304 costs a round trip but no rate-limit quota, and the observations it
      produces are identical to a fresh fetch;
    * a retryable failure waits only as long as the provider asked and only
      while a total waiting budget lasts, then becomes an explicit status;
    * a request budget stops collection rather than silently truncating: a
      partially enumerated list is PARTIAL with the reason
      ``REQUEST_BUDGET_EXHAUSTED``, and a value never collected keeps the
      explicit status its caller assigns.
    """

    def __init__(
        self,
        transport: Any,
        budget: int | None = None,
        retry: RetryPolicy | None = None,
        cache: ConditionalCache | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.transport = transport
        self.budget = budget
        self.retry = retry or RetryPolicy()
        self.cache = cache
        self._sleep = sleep
        self.request_count = 0
        self.billed_count = 0
        self.conditional_hits = 0
        self.retries = 0
        self.waited_seconds = 0
        self.budget_exhausted = False

    @property
    def budget_remaining(self) -> int | None:
        return None if self.budget is None else max(self.budget - self.billed_count, 0)

    def _claim_request(self) -> None:
        if self.budget is not None and self.billed_count >= self.budget:
            self.budget_exhausted = True
            raise RequestBudgetExhausted(self.budget)

    def incomplete_reason(self) -> str:
        """Why an enumeration stopped short: the budget if it bit, otherwise the page cap."""
        return BUDGET_EXHAUSTED if self.budget_exhausted else PAGINATION_CAPPED

    def notes(self) -> list[str]:
        """Capability notes worth recording in the collection receipt."""
        return [f"{BUDGET_EXHAUSTED}:{self.budget}"] if self.budget_exhausted else []

    def _transport_get(self, path: str, params: dict[str, Any] | None, headers: dict[str, str] | None) -> tuple[int, dict[str, str], Any]:
        self.request_count += 1
        if headers:
            return self.transport.get(path, params, headers)
        return self.transport.get(path, params)

    def _wait_before_retry(self, headers: dict[str, str], attempt: int) -> bool:
        """Sleep if the provider's asking price is affordable; otherwise give up now."""
        asked = retry_after_seconds(headers)
        backoff = self.retry.backoff_seconds[min(attempt - 1, len(self.retry.backoff_seconds) - 1)]
        wait = asked if asked is not None else backoff
        if wait > self.retry.max_single_wait_seconds:
            return False
        if self.waited_seconds + wait > self.retry.total_wait_budget_seconds:
            return False
        self._sleep(wait)
        self.waited_seconds += wait
        self.retries += 1
        return True

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        key = ConditionalCache.key(path, params) if self.cache is not None else None
        headers: dict[str, str] | None = None
        if key is not None:
            etag = self.cache.etag_for(key)
            if etag:
                headers = {"If-None-Match": etag}

        for attempt in range(1, max(self.retry.attempts, 1) + 1):
            self._claim_request()
            status, response_headers, body = self._transport_get(path, params, headers)
            if status == NOT_MODIFIED:
                if key is None:
                    raise ApiFailure(status, ERROR, "UNEXPECTED_NOT_MODIFIED", "provider answered 304 to an unconditional request", False)
                cached = self.cache.body_for(key)
                if cached is not None:
                    self.conditional_hits += 1
                    return cached
                # The provider says nothing changed but our copy is gone: ask
                # again without the tag rather than report an empty answer.
                headers = None
                continue
            if status < 400:
                self.billed_count += 1
                if key is not None:
                    self.cache.store(key, response_headers.get("etag"), body)
                return body

            self.billed_count += 1
            obs_status, reason, retryable = classify_http_error(status, body, response_headers)
            message = body.get("message", "") if isinstance(body, dict) else ""
            if retryable and attempt < self.retry.attempts and self._wait_before_retry(response_headers, attempt):
                continue
            raise ApiFailure(status, obs_status, reason, message, retryable)
        raise ApiFailure(0, ERROR, "RETRIES_EXHAUSTED", f"no usable response for {path}", True)

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None,
        max_pages: int,
        stop: Callable[[dict[str, Any]], bool] | None = None,
        items_key: str | None = None,
        total_key: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Page-number pagination. Returns (items, complete).

        With ``total_key`` the provider's own count is read on every page and
        a listing that ends short of it is incomplete: a filtered
        ``/actions/runs`` query stops at 1,000 results and answers the next
        page empty, which would otherwise read as proof of completeness.
        """
        items: list[dict[str, Any]] = []
        total = 0
        params = dict(params or {})
        params["per_page"] = PER_PAGE
        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                body = self.get(path, params)
            except RequestBudgetExhausted:
                return items, False
            if items_key:
                if not isinstance(body, dict):
                    raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"expected an object with {items_key!r} from {path}, got {type(body).__name__}")
                batch = body.get(items_key)
                if batch is None:
                    raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"expected {items_key!r} in the answer from {path}, got none")
                if total_key is not None:
                    reported = body.get(total_key)
                    if isinstance(reported, bool) or not isinstance(reported, int) or reported < 0:
                        raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"{total_key} from {path} is {reported!r}, not a count")
                    total = max(total, reported)
            else:
                batch = body
            if not isinstance(batch, list):
                raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"expected a list from {path}, got {type(batch).__name__}")
            items.extend(batch)
            if stop is not None and batch and stop(batch[-1]):
                return items, True
            if len(batch) < PER_PAGE:
                return items, total <= len(items)
        return items, False


def _payload_failure(path: str, what: str) -> ApiFailure:
    """A successful answer whose shape or values cannot be read as the endpoint documents.

    It is an ``ApiFailure`` so the collector that asked turns it into an
    explicit ``ERROR / UNEXPECTED_PAYLOAD`` observation on that inventory
    alone, exactly like a failed request; nothing is coerced, defaulted or
    skipped in its place (PV-AUDIT-GITHUB-*-PAYLOAD-001).
    """
    return ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"{path}: {what}")


def _object(path: str, value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _payload_failure(path, f"{what} is {type(value).__name__}, not an object")
    return value


def _rows(path: str, rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise _payload_failure(path, f"expected a list, got {type(rows).__name__}")
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise _payload_failure(path, f"item {position} is {type(row).__name__}, not an object")
    return rows


def _integer(path: str, value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _payload_failure(path, f"{field} is {value!r}, not an integer >= {minimum}")
    return value


def _optional_integer(path: str, value: Any, field: str, minimum: int = 0) -> int | None:
    return None if value is None else _integer(path, value, field, minimum)


def _text(path: str, value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _payload_failure(path, f"{field} is {value!r}, not a non-empty string")
    return value


def _optional_text(path: str, value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _payload_failure(path, f"{field} is {value!r}, not a string")
    return value


def _boolean(path: str, value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _payload_failure(path, f"{field} is {value!r}, not a boolean")
    return value


def _timestamp(path: str, value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _payload_failure(path, f"{field} is {value!r}, not a timestamp")
    try:
        return timeutil.normalize_ts(value)
    except ValueError as exc:
        raise _payload_failure(path, f"{field} {value!r} is not a timestamp: {exc}") from exc


def _optional_timestamp(path: str, value: Any, field: str) -> str | None:
    return None if value is None else _timestamp(path, value, field)


def _failure_observation(observation_id: str, value_type: str, exc: Exception, common: dict[str, Any]) -> Observation:
    if isinstance(exc, ApiFailure):
        return Observation(
            observation_id=observation_id,
            status=exc.observation_status,
            value_type=value_type,
            reason_code=exc.reason_code,
            notes=f"HTTP {exc.status_code}: {exc.message}"[:300],
            **common,
        )
    if isinstance(exc, RegisterError):
        return Observation(observation_id=observation_id, status=ERROR, value_type=value_type, reason_code="INVALID_REGISTER", notes=str(exc)[:300], **common)
    return Observation(observation_id=observation_id, status=ERROR, value_type=value_type, reason_code="NETWORK", notes=str(exc)[:300], **common)


def _title(text: Any) -> str:
    """The first line of a provider-supplied title, or ``""`` when there is none.

    Total on purpose. It is called on commit messages, change-request and issue
    titles, milestone titles and release names, all of which are provider
    payload: a field of the wrong type, or one that is only whitespace, is a
    missing title and not a reason to abandon a fleet run. A register is a
    different case, because its schema declares a string, so
    :func:`_register_title` rejects anything else as an invalid register.
    """
    if not isinstance(text, str):
        return ""
    lines = text.strip().splitlines()
    return lines[0][:160] if lines else ""


def _register_title(where: str, value: Any) -> str:
    """A register title, or an INVALID_REGISTER error when it is not a string."""
    if value is not None and not isinstance(value, str):
        raise RegisterError(f"{where} title must be a string, got {value!r}")
    return _title(value)


def _linkage_text(item: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, list[str]]:
    """The readable free-text fields a target marker can live in, and the ones that cannot be read.

    Payload of the wrong type in a title or body is not an absent link: read as
    one it would report the change request unlinked on evidence nobody could
    parse. It is not a reason to fail the project either. Since
    ``PV-DIRECTION-INCOMPLETE-001`` the change request keeps what could be read
    and names what could not, and Direction treats its linkage as unresolved
    unless a readable reference already links it.
    """
    parts: list[str] = []
    unreadable: list[str] = []
    for field in fields:
        value = item.get(field)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            unreadable.append(f"{field}:{type(value).__name__}")
            continue
        parts.append(value)
    return "\n".join(parts), unreadable


def _milestone_ref(milestone: Any) -> tuple[dict[str, str] | None, str | None]:
    """A milestone is a target link: ``(reference, None)``, ``(None, None)`` when absent, ``(None, reason)`` when unreadable.

    The provider embeds the milestone it links, state included, so the
    reference is resolved by the change request's own payload: a closed
    milestone is still the milestone the work was declared against
    (``PV-REV-DIRECTION-CLOSED-TARGET-001``).
    """
    if not milestone:
        return None, None
    if not isinstance(milestone, dict) or milestone.get("number") is None or isinstance(milestone.get("number"), bool):
        return None, "milestone:NO_NUMBER"
    state = "CLOSED" if str(milestone.get("state") or "").lower() == "closed" else "OPEN"
    return {"target_id": str(milestone["number"]), "state": state}, None


def _normalize_date(value: Any) -> str | None:
    """Accept YYYY-MM-DD or RFC 3339; a bare date means midnight UTC."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RegisterError(f"date must be a string, got {value!r}")
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00Z"
    try:
        return timeutil.normalize_ts(text)
    except ValueError as exc:
        raise RegisterError(f"invalid date {value!r}") from exc


def marker_target_ids(text: str | None, marker: str) -> list[str]:
    """Explicit target references: every standalone ``<marker> <id>`` occurrence, in order, without duplicates.

    The configured marker is a token of its own, never text inside a larger one
    (``PV-AUDIT-TARGET-MARKER-SYNTAX-001``): it starts the text or follows a
    character that cannot continue a word, and a marker that ends in a word
    character is not followed by another. ``SubTarget: B1``, ``NotTarget: B1``
    and ``PreTarget:B1`` therefore link nothing under ``Target:``, while
    ``Target: B1`` at the start of a line, after a space or inside
    ``(Target: B1)`` does. The marker is matched exactly, case included.
    """
    if not text or not marker:
        return []
    tail = r"(?!\w)" if (marker[-1].isalnum() or marker[-1] == "_") else ""
    pattern = re.compile(r"(?<!\w)" + re.escape(marker) + tail + r"[ \t]*([A-Za-z0-9][A-Za-z0-9._/-]*)")
    seen: list[str] = []
    for match in pattern.finditer(text):
        target_id = match.group(1).rstrip(".,;:")
        if target_id and target_id not in seen:
            seen.append(target_id)
    return seen


OPEN_STATES = ("open",)
CLOSED_STATES = ("closed", "done", "resolved", "cancelled", "canceled")


def _register_state(where: str, value: Any) -> str:
    """The documented state vocabulary, or an invalid register.

    An absent or empty state is ``open``, as the register contract allows. A
    present value outside the vocabulary, or of the wrong type, is not an
    open item: it is a register nobody can read, and reading it as open would
    manufacture a target or a debt item (PV-AUDIT-REGISTER-STATE-001).
    """
    if value is None or value == "":
        return "OPEN"
    if not isinstance(value, str):
        raise RegisterError(f"{where} state must be a string, got {value!r}")
    state = value.strip().lower()
    if state in OPEN_STATES:
        return "OPEN"
    if state in CLOSED_STATES:
        return "CLOSED"
    raise RegisterError(f"{where} state {value!r} is not one of {OPEN_STATES + CLOSED_STATES}")


def parse_targets_register(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or document.get("schema") != TARGETS_REGISTER_SCHEMA:
        raise RegisterError(f"targets register must be an object with schema {TARGETS_REGISTER_SCHEMA}")
    targets = document.get("targets")
    if not isinstance(targets, list):
        raise RegisterError("targets register requires a targets list")
    items = []
    seen: set[str] = set()
    for entry in targets:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise RegisterError("every target needs a string id")
        target_id = entry["id"].strip()
        if target_id in seen:
            raise RegisterError(f"duplicate target id {target_id}")
        seen.add(target_id)
        items.append(
            {
                "target_id": target_id,
                "id": target_id,
                "title": _register_title(f"target {target_id}", entry.get("title")),
                "state": _register_state(f"target {target_id}", entry.get("state")),
                "due_at": _normalize_date(entry.get("due")),
                "open_items": 0,
                "closed_items": 0,
                "url": None,
            }
        )
    items.sort(key=lambda m: m["target_id"])
    return items


def parse_debt_register(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or document.get("schema") != DEBT_REGISTER_SCHEMA:
        raise RegisterError(f"debt register must be an object with schema {DEBT_REGISTER_SCHEMA}")
    entries = document.get("items")
    if not isinstance(entries, list):
        raise RegisterError("debt register requires an items list")
    items = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise RegisterError("every debt item needs a string id")
        item_id = entry["id"].strip()
        if item_id in seen:
            raise RegisterError(f"duplicate debt item id {item_id}")
        seen.add(item_id)
        opened = _normalize_date(entry.get("opened"))
        updated = _normalize_date(entry.get("updated")) or opened
        if updated is None:
            raise RegisterError(f"debt item {item_id} needs an opened or updated date")
        items.append(
            {
                "id": item_id,
                "title": _register_title(f"debt item {item_id}", entry.get("title")),
                "state": _register_state(f"debt item {item_id}", entry.get("state")),
                "opened_at": opened,
                "updated_at": updated,
                "closed_at": _normalize_date(entry.get("closed")),
            }
        )
    items.sort(key=lambda i: i["id"])
    return items


def _workflows_total(path: str, payload: Any) -> int:
    """The workflow count a successful ``/actions/workflows`` answer establishes, or a declared failure.

    A 200 whose body is not an object, or whose ``total_count`` is absent or
    not a non-negative integer, establishes no count at all. It is refused as
    ``ERROR / UNEXPECTED_PAYLOAD`` like every other malformed success, so it
    reaches ``workflows_failure`` and the check-suite fallback with a
    ``WORKFLOWS_UNAVAILABLE`` note instead of escaping the inventory as a
    Python exception, and no count is invented in its place (PV-REV-PR-029).
    """
    if not isinstance(payload, dict):
        raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"expected an object from {path}, got {type(payload).__name__}")
    total = payload.get("total_count")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ApiFailure(200, ERROR, "UNEXPECTED_PAYLOAD", f"expected a non-negative integer total_count from {path}, got {total!r}")
    return total


class GitHubAdapter:
    """Collect provider-neutral inventories for one repository at one moment."""

    def __init__(self, client: GitHubClient, now: datetime) -> None:
        self.client = client
        self.now = now.astimezone(timeutil.UTC).replace(microsecond=0)
        self.observed_at = timeutil.format_ts(self.now)
        self.notes: list[str] = []

    def _common(self, source_ref: str) -> dict[str, Any]:
        return {"provider": "github", "collected_at": self.observed_at, "source_ref": source_ref, "adapter_version": ADAPTER_VERSION}

    def collect(self, project: ResolvedProject) -> ObservationSet:
        owner, repo = project.owner, project.repo
        base = f"/repos/{owner}/{repo}"
        started = timeutil.format_ts(timeutil.now_utc())
        try:
            meta = self._repository_metadata(base, self.client.get(base))
        except (ApiFailure, NetworkFailure) as exc:
            raise CollectionError(f"cannot identify {owner}/{repo}: {exc}") from exc
        default_branch = meta["default_branch"]
        subject = {
            "provider": "github",
            "forge_instance": "github.com",
            "owner": owner,
            "repo": repo,
            "display_locator": f"{owner}/{repo}",
            "immutable_project_id": str(meta["id"]),
            "default_branch": default_branch,
            "visibility": meta["visibility"],
        }
        obs = ObservationSet(subject=subject, observed_at=self.observed_at)
        obs.add(
            Observation(
                observation_id=INV_REPO,
                status=AVAILABLE,
                value_type="record",
                value={
                    "id": meta["id"],
                    "full_name": meta["full_name"],
                    "default_branch": default_branch,
                    "visibility": meta["visibility"],
                    "has_issues": meta["has_issues"],
                    "archived": meta["archived"],
                    "pushed_at": meta["pushed_at"],
                    "html_url": meta["html_url"],
                },
                evidence_ref={"endpoint": base},
                **self._common(base),
            )
        )

        commits_by_sha = self._collect_commits(obs, base, default_branch)
        target_states = self._collect_targets(obs, base, project, default_branch)
        self._collect_change_requests(obs, base, project, target_states)
        self._collect_issues(obs, base, meta["has_issues"])
        self._collect_branches(obs, base, default_branch, commits_by_sha)
        self._collect_debt_register(obs, base, project, default_branch)
        self._collect_releases(obs, base)
        self._collect_ci(obs, base, default_branch, commits_by_sha)

        receipt = Receipt(
            run_id=f"run-{timeutil.compact_ts(self.now)}-{owner}-{repo}",
            collector_version=ADAPTER_VERSION,
            target=subject,
            started_at=started,
            ended_at=timeutil.format_ts(timeutil.now_utc()),
            capability_notes=list(self.notes) + self.client.notes(),
            config_hash=project.effective_config_digest(),
        )
        obs.finalize_receipt(receipt)
        return obs

    @staticmethod
    def _repository_metadata(path: str, payload: Any) -> dict[str, Any]:
        """The repository fields collection is routed by, each one typed evidence.

        The default branch decides where commits, registers and verification
        are looked for, the id decides where history lives, and the capability
        flags decide what is asked for. None of them is guessed: an answer that
        does not establish them is a declared failure, never ``main``, never
        the truthiness of a string (PV-AUDIT-GITHUB-REPO-PAYLOAD-001).
        """
        meta = _object(path, payload, "repository metadata")
        return {
            "id": _integer(path, meta.get("id"), "id", 1),
            "full_name": _optional_text(path, meta.get("full_name"), "full_name"),
            "default_branch": _text(path, meta.get("default_branch"), "default_branch"),
            "visibility": _optional_text(path, meta.get("visibility"), "visibility"),
            "has_issues": _boolean(path, meta.get("has_issues"), "has_issues"),
            "archived": _boolean(path, meta.get("archived"), "archived"),
            "pushed_at": _optional_timestamp(path, meta.get("pushed_at"), "pushed_at"),
            "html_url": _optional_text(path, meta.get("html_url"), "html_url"),
        }

    def _fetch_json_register(self, base: str, path: str, ref: str) -> Any:
        """Read a JSON file of the repository through the contents API."""
        encoded = "/".join(urllib.parse.quote(part) for part in path.split("/"))
        endpoint = f"{base}/contents/{encoded}"
        body = self.client.get(endpoint, {"ref": ref})
        if not isinstance(body, dict) or body.get("type") != "file":
            raise RegisterError(f"{path} is not a file")
        # The size is required, not defaulted: a missing size must not wave a
        # body through the byte bound (PV-AUDIT-GITHUB-REGISTER-PAYLOAD-001).
        if _integer(endpoint, body.get("size"), "size") > MAX_REGISTER_BYTES:
            raise RegisterError(f"{path} exceeds {MAX_REGISTER_BYTES} bytes")
        content = body.get("content")
        if body.get("encoding") != "base64" or not isinstance(content, str) or not content:
            raise RegisterError(f"{path} has no base64 content")
        try:
            # GitHub wraps the base64 at 60 columns; anything else outside the
            # alphabet is not a register this adapter will guess at.
            raw = base64.b64decode("".join(content.split()), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RegisterError(f"{path} is not valid base64: {exc}") from exc
        if len(raw) > MAX_REGISTER_BYTES:
            raise RegisterError(f"{path} decodes to more than {MAX_REGISTER_BYTES} bytes")
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise RegisterError(f"{path} is not valid JSON: {type(exc).__name__}") from exc

    def _collect_commits(self, obs: ObservationSet, base: str, default_branch: str) -> dict[str, dict[str, Any]]:
        since = timeutil.minus_days(self.now, PULSE["window_days"])
        path = f"{base}/commits"
        common = self._common(f"{path}?sha={default_branch}&since={timeutil.format_ts(since)}")
        try:
            raw, complete = self.client.paginate(path, {"sha": default_branch, "since": timeutil.format_ts(since)}, MAX_COMMIT_PAGES)
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_COMMITS, "series", exc, common))
            return {}
        try:
            items = [self._commit_record(path, commit) for commit in _rows(path, raw)]
        except ApiFailure as exc:
            obs.add(_failure_observation(INV_COMMITS, "series", exc, common))
            return {}
        # A push between two pages shifts the listing: the same commit comes
        # back twice (and another may be skipped). Each commit is counted once,
        # and a shifted listing is not complete.
        unique = {item["sha"]: item for item in items}
        shifted = len(unique) != len(items)
        items = sorted(unique.values(), key=lambda c: (c["committed_at"], c["sha"]))
        complete = complete and not shifted
        obs.add(
            Observation(
                observation_id=INV_COMMITS,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=items,
                coverage={"window_start": timeutil.format_ts(since), "window_end": self.observed_at, "complete": complete, "branch": default_branch},
                reason_code=None if complete else (LISTING_SHIFTED if shifted else self.client.incomplete_reason()),
                evidence_ref={"endpoint": path, "branch": default_branch},
                **common,
            )
        )
        return {item["sha"]: item for item in items}

    @staticmethod
    def _commit_record(path: str, commit: dict[str, Any]) -> dict[str, Any]:
        """One commit as the inventory records it, or a declared payload failure.

        A commit without a readable date is not skipped: an omitted commit
        would undercount activity and misplace the verification window
        (PV-AUDIT-GITHUB-COMMITS-PAYLOAD-001). The committer date is used when
        present, the author date otherwise, as before.
        """
        sha = _text(path, commit.get("sha"), "sha")
        info = _object(path, commit.get("commit"), f"commit {sha} commit")
        committed: str | None = None
        for role in ("committer", "author"):
            person = info.get(role)
            if person is None:
                continue
            person = _object(path, person, f"commit {sha} {role}")
            if committed is None and person.get("date") is not None:
                committed = _timestamp(path, person.get("date"), f"commit {sha} {role}.date")
        if committed is None:
            raise _payload_failure(path, f"commit {sha} carries no committer or author date")
        return {"sha": sha, "committed_at": committed, "title": _title(info.get("message"))}

    def _target_refs(self, pull: dict[str, Any], project: ResolvedProject, target_states: dict[str, str] | None) -> tuple[list[dict[str, str]], list[str]]:
        """The explicit target references of a change request and what of its linkage evidence could not be read.

        Each reference carries the state its resolution established:
        ``OPEN`` or ``CLOSED`` when the declared target resolves (state-neutral
        linkage, ``PV-REV-DIRECTION-CLOSED-TARGET-001``), ``MISSING`` when the
        complete register positively lacks the id (a broken reference, not
        missing evidence), ``UNKNOWN`` when the register could not be read, so
        nothing about the id is known (``PV-DIRECTION-INCOMPLETE-001``).
        """
        source = project.planning["source"]
        if source == "milestones":
            ref, problem = _milestone_ref(pull.get("milestone") or None)
            return ([ref] if ref else []), ([problem] if problem else [])
        if source == "file":
            marker = project.planning.get("link_marker") or "Target:"
            text, unreadable = _linkage_text(pull, ("title", "body"))
            ids = marker_target_ids(text, marker)
            if target_states is None:
                return [{"target_id": tid, "state": "UNKNOWN"} for tid in ids], unreadable
            return [{"target_id": tid, "state": target_states.get(tid, "MISSING")} for tid in ids], unreadable
        return [], []

    def _collect_change_requests(self, obs: ObservationSet, base: str, project: ResolvedProject, target_states: dict[str, str] | None) -> None:
        since = timeutil.minus_days(self.now, FLOW["window_days"])
        path = f"{base}/pulls"
        common = self._common(f"{path}?state=open|updated>={timeutil.format_ts(since)}")
        try:
            open_raw, open_complete = self.client.paginate(path, {"state": "open", "sort": "created", "direction": "asc"}, MAX_CHANGE_REQUEST_PAGES)
            recent_raw, window_complete = self.client.paginate(
                path,
                {"state": "all", "sort": "updated", "direction": "desc"},
                MAX_CHANGE_REQUEST_PAGES,
                stop=lambda item: timeutil.parse_ts(_timestamp(path, _object(path, item, "change request").get("updated_at"), "updated_at")) < since,
            )
            merged: dict[int, dict[str, Any]] = {}
            for pull in _rows(path, open_raw) + _rows(path, recent_raw):
                record = self._change_request_record(path, pull, project, target_states)
                merged[record["number"]] = record
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_CRS, "series", exc, common))
            return
        items = [merged[number] for number in sorted(merged)]
        complete = open_complete and window_complete
        obs.add(
            Observation(
                observation_id=INV_CRS,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=items,
                coverage={
                    "open_complete": open_complete,
                    "window_complete": window_complete,
                    "window_start": timeutil.format_ts(since),
                    "linkage": project.planning["source"],
                    "link_marker": project.planning.get("link_marker") if project.planning["source"] == "file" else None,
                },
                reason_code=None if complete else self.client.incomplete_reason(),
                evidence_ref={"endpoint": path},
                **common,
            )
        )

    def _change_request_record(self, path: str, pull: dict[str, Any], project: ResolvedProject, target_states: dict[str, str] | None) -> dict[str, Any]:
        """One change request as the inventory records it, or a declared payload failure (PV-AUDIT-GITHUB-CR-PAYLOAD-001)."""
        number = _integer(path, pull.get("number"), "number", 1)
        where = f"change request #{number}"
        merged_at = _optional_timestamp(path, pull.get("merged_at"), f"{where} merged_at")
        state_text = _optional_text(path, pull.get("state"), f"{where} state")
        if merged_at:
            state = "MERGED"
        elif state_text == "closed":
            state = "CLOSED"
        else:
            state = "OPEN"
        user = pull.get("user")
        author = None if user is None else _optional_text(path, _object(path, user, f"{where} user").get("login"), f"{where} user.login")
        refs, linkage_unresolved = self._target_refs(pull, project, target_states)
        return {
            "number": number,
            "id": _optional_integer(path, pull.get("id"), f"{where} id"),
            "title": _title(pull.get("title")),
            "state": state,
            "draft": _boolean(path, pull.get("draft", False), f"{where} draft"),
            "created_at": _timestamp(path, pull.get("created_at"), f"{where} created_at"),
            "updated_at": _timestamp(path, pull.get("updated_at"), f"{where} updated_at"),
            "merged_at": merged_at,
            "closed_at": _optional_timestamp(path, pull.get("closed_at"), f"{where} closed_at"),
            "target_id": refs[0]["target_id"] if refs else None,
            "target_state": refs[0]["state"] if refs else None,
            "target_refs": refs,
            "linkage_unresolved": sorted(linkage_unresolved),
            "author": author,
            "url": _optional_text(path, pull.get("html_url"), f"{where} html_url"),
        }

    @staticmethod
    def _issue_record(path: str, issue: dict[str, Any]) -> dict[str, Any]:
        """One issue as the inventory records it, or a declared payload failure (PV-AUDIT-GITHUB-ISSUES-PAYLOAD-001)."""
        number = _integer(path, issue.get("number"), "number", 1)
        where = f"issue #{number}"
        labels = issue.get("labels")
        if labels is None:
            labels = []
        names = []
        for position, label in enumerate(_rows(path, labels)):
            names.append(_text(path, label.get("name"), f"{where} labels[{position}].name"))
        user = issue.get("user")
        author = None if user is None else _optional_text(path, _object(path, user, f"{where} user").get("login"), f"{where} user.login")
        milestone, milestone_problem = _milestone_ref(issue.get("milestone") or None)
        state_text = _optional_text(path, issue.get("state"), f"{where} state")
        return {
            "number": number,
            "id": _optional_integer(path, issue.get("id"), f"{where} id"),
            "title": _title(issue.get("title")),
            "state": "CLOSED" if state_text == "closed" else "OPEN",
            "created_at": _timestamp(path, issue.get("created_at"), f"{where} created_at"),
            "updated_at": _timestamp(path, issue.get("updated_at"), f"{where} updated_at"),
            "closed_at": _optional_timestamp(path, issue.get("closed_at"), f"{where} closed_at"),
            "labels": sorted(names),
            "target_id": milestone["target_id"] if milestone else None,
            "linkage_unresolved": [milestone_problem] if milestone_problem else [],
            "author": author,
            "url": _optional_text(path, issue.get("html_url"), f"{where} html_url"),
        }

    def _collect_issues(self, obs: ObservationSet, base: str, has_issues: bool) -> None:
        since = timeutil.minus_days(self.now, PULSE["window_days"])
        path = f"{base}/issues"
        common = self._common(f"{path}?state=open|since={timeutil.format_ts(since)}")
        if not has_issues:
            obs.add(Observation(observation_id=INV_ISSUES, status=UNAVAILABLE, value_type="series", reason_code="ISSUES_DISABLED", **common))
            return
        try:
            open_raw, open_complete = self.client.paginate(path, {"state": "open", "sort": "created", "direction": "asc"}, MAX_ISSUE_PAGES)
            recent_raw, window_complete = self.client.paginate(
                path, {"state": "all", "since": timeutil.format_ts(since), "sort": "updated", "direction": "desc"}, MAX_ISSUE_PAGES
            )
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_ISSUES, "series", exc, common))
            return
        merged: dict[int, dict[str, Any]] = {}
        try:
            for issue in _rows(path, open_raw) + _rows(path, recent_raw):
                if issue.get("pull_request"):
                    continue
                record = self._issue_record(path, issue)
                merged[record["number"]] = record
        except ApiFailure as exc:
            obs.add(_failure_observation(INV_ISSUES, "series", exc, common))
            return
        items = [merged[number] for number in sorted(merged)]
        complete = open_complete and window_complete
        obs.add(
            Observation(
                observation_id=INV_ISSUES,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=items,
                coverage={"open_complete": open_complete, "window_complete": window_complete, "window_start": timeutil.format_ts(since)},
                reason_code=None if complete else self.client.incomplete_reason(),
                evidence_ref={"endpoint": path},
                **common,
            )
        )

    def _collect_branches(self, obs: ObservationSet, base: str, default_branch: str, commits_by_sha: dict[str, dict[str, Any]]) -> None:
        path = f"{base}/branches"
        common = self._common(path)
        try:
            raw, complete = self.client.paginate(path, {}, MAX_BRANCH_PAGES)
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_BRANCHES, "series", exc, common))
            return
        items = []
        lookups = 0
        heads_resolved = True
        try:
            for branch in _rows(path, raw):
                name = _text(path, branch.get("name"), "branch name")
                if name == default_branch:
                    continue
                sha = _text(path, _object(path, branch.get("commit"), f"branch {name} commit").get("sha"), f"branch {name} commit.sha")
                protected = _boolean(path, branch.get("protected", False), f"branch {name} protected")
                committed_at = None
                if sha in commits_by_sha:
                    committed_at = commits_by_sha[sha]["committed_at"]
                elif lookups < MAX_BRANCH_HEAD_LOOKUPS:
                    lookups += 1
                    detail_path = f"{base}/commits/{sha}"
                    try:
                        # A head whose detail cannot be read stays unresolved: the
                        # inventory is then PARTIAL / BRANCH_HEADS_UNRESOLVED, and
                        # nothing is inferred about its age (PV-AUDIT-GITHUB-BRANCH-PAYLOAD-001).
                        committed_at = self._commit_record(detail_path, _object(detail_path, self.client.get(detail_path), "commit detail"))["committed_at"]
                    except (ApiFailure, NetworkFailure):
                        heads_resolved = False
                else:
                    heads_resolved = False
                items.append({"name": name, "head_sha": sha, "head_committed_at": committed_at, "protected": protected})
        except ApiFailure as exc:
            obs.add(_failure_observation(INV_BRANCHES, "series", exc, common))
            return
        items.sort(key=lambda b: b["name"])
        status = AVAILABLE if (complete and heads_resolved) else PARTIAL
        obs.add(
            Observation(
                observation_id=INV_BRANCHES,
                status=status,
                value_type="series",
                value=items,
                coverage={"complete": complete, "heads_resolved": heads_resolved, "head_lookups": lookups},
                reason_code=None if status == AVAILABLE else (self.client.incomplete_reason() if not complete else "BRANCH_HEADS_UNRESOLVED"),
                evidence_ref={"endpoint": path},
                **common,
            )
        )

    def _collect_targets(self, obs: ObservationSet, base: str, project: ResolvedProject, default_branch: str) -> dict[str, str] | None:
        """Planning targets from milestones or a register file; returns id -> state for file sources."""
        source = project.planning["source"]
        if source == "none":
            common = self._common("config:planning")
            obs.add(Observation(observation_id=INV_TARGETS, status=UNAVAILABLE, value_type="series", reason_code="PLANNING_SOURCE_NONE", **common))
            return None
        if source == "file":
            path = project.planning["path"]
            common = self._common(f"{base}/contents/{path}?ref={default_branch}")
            try:
                items = parse_targets_register(self._fetch_json_register(base, path, default_branch))
            except (ApiFailure, NetworkFailure, RegisterError) as exc:
                if isinstance(exc, ApiFailure) and exc.reason_code == "NOT_FOUND":
                    exc = ApiFailure(exc.status_code, UNAVAILABLE, "REGISTER_NOT_FOUND", f"{path} not found on {default_branch}")
                obs.add(_failure_observation(INV_TARGETS, "series", exc, common))
                return None
            for item in items:
                item["url"] = f"https://github.com/{project.owner}/{project.repo}/blob/{default_branch}/{path}"
            obs.add(
                Observation(
                    observation_id=INV_TARGETS,
                    status=AVAILABLE,
                    value_type="series",
                    value=items,
                    coverage={"complete": True, "source": "file", "path": path, "schema": TARGETS_REGISTER_SCHEMA},
                    evidence_ref={"endpoint": f"{base}/contents/{path}", "ref": default_branch},
                    **common,
                )
            )
            return {item["target_id"]: item["state"] for item in items}

        path = f"{base}/milestones"
        common = self._common(f"{path}?state=all")
        try:
            raw, complete = self.client.paginate(path, {"state": "all", "sort": "due_on", "direction": "asc"}, 3)
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_TARGETS, "series", exc, common))
            return None
        try:
            items = [self._milestone_record(path, milestone) for milestone in _rows(path, raw)]
        except ApiFailure as exc:
            obs.add(_failure_observation(INV_TARGETS, "series", exc, common))
            return None
        items.sort(key=lambda m: int(m["target_id"]))
        obs.add(
            Observation(
                observation_id=INV_TARGETS,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=items,
                coverage={"complete": complete, "source": "milestones"},
                reason_code=None if complete else self.client.incomplete_reason(),
                evidence_ref={"endpoint": path},
                **common,
            )
        )
        return None

    @staticmethod
    def _milestone_record(path: str, milestone: dict[str, Any]) -> dict[str, Any]:
        number = _integer(path, milestone.get("number"), "milestone number", 1)
        where = f"milestone {number}"
        state_text = _optional_text(path, milestone.get("state"), f"{where} state")
        return {
            "target_id": str(number),
            "id": _optional_integer(path, milestone.get("id"), f"{where} id"),
            "title": _title(milestone.get("title")),
            "state": "CLOSED" if state_text == "closed" else "OPEN",
            "due_at": _optional_timestamp(path, milestone.get("due_on"), f"{where} due_on"),
            "open_items": _optional_integer(path, milestone.get("open_issues"), f"{where} open_issues") or 0,
            "closed_items": _optional_integer(path, milestone.get("closed_issues"), f"{where} closed_issues") or 0,
            "url": _optional_text(path, milestone.get("html_url"), f"{where} html_url"),
        }

    def _collect_debt_register(self, obs: ObservationSet, base: str, project: ResolvedProject, default_branch: str) -> None:
        mapping = project.debt_mapping
        if not mapping or mapping.get("source") != "file":
            return
        path = mapping["path"]
        common = self._common(f"{base}/contents/{path}?ref={default_branch}")
        try:
            items = parse_debt_register(self._fetch_json_register(base, path, default_branch))
        except (ApiFailure, NetworkFailure, RegisterError) as exc:
            if isinstance(exc, ApiFailure) and exc.reason_code == "NOT_FOUND":
                exc = ApiFailure(exc.status_code, UNAVAILABLE, "REGISTER_NOT_FOUND", f"{path} not found on {default_branch}")
            obs.add(_failure_observation(INV_DEBT_REGISTER, "series", exc, common))
            return
        obs.add(
            Observation(
                observation_id=INV_DEBT_REGISTER,
                status=AVAILABLE,
                value_type="series",
                value=items,
                coverage={"complete": True, "source": "file", "path": path, "schema": DEBT_REGISTER_SCHEMA, "mapping_version": mapping["mapping_version"]},
                evidence_ref={"endpoint": f"{base}/contents/{path}", "ref": default_branch},
                **common,
            )
        )

    def _collect_releases(self, obs: ObservationSet, base: str) -> None:
        path = f"{base}/releases"
        common = self._common(path)
        limit = MAX_RELEASES
        try:
            raw = _rows(path, self.client.get(path, {"per_page": limit}))
            items = []
            for position, release in enumerate(raw):
                where = f"release {position}"
                # A draft is positively a draft, and only then may it carry no
                # publication date; every other row is a published release whose
                # tag and date must be readable (PV-AUDIT-GITHUB-RELEASE-PAYLOAD-001).
                if _boolean(path, release.get("draft"), f"{where} draft"):
                    continue
                items.append(
                    {
                        "tag": _text(path, release.get("tag_name"), f"{where} tag_name"),
                        "name": _title(release.get("name")),
                        "published_at": _timestamp(path, release.get("published_at"), f"{where} published_at"),
                        "prerelease": _boolean(path, release.get("prerelease"), f"{where} prerelease"),
                        "url": _optional_text(path, release.get("html_url"), f"{where} html_url"),
                    }
                )
        except (ApiFailure, NetworkFailure) as exc:
            obs.add(_failure_observation(INV_RELEASES, "series", exc, common))
            return
        # A full page means the provider had at least this many: the newest are
        # observed, the rest are not, and that is PARTIAL rather than complete.
        complete = len(raw) < limit
        items.sort(key=lambda r: (r["published_at"], r["tag"]))
        obs.add(
            Observation(
                observation_id=INV_RELEASES,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=items,
                coverage={"recent_only": True, "limit": limit, "complete": complete},
                reason_code=None if complete else self.client.incomplete_reason(),
                evidence_ref={"endpoint": path},
                **common,
            )
        )

    @staticmethod
    def _attempt_record(path: str, payload: Any, run_id: int, number: int) -> dict[str, Any]:
        """An earlier attempt of a run, proven to be the attempt that was asked for.

        An attempt that names another run or another number is not evidence
        about this run's history; counting it would let ``attempts_complete``
        be true over attempts nobody proved (PV-AUDIT-GITHUB-CI-PAYLOAD-001).
        """
        attempt = _object(path, payload, "run attempt")
        if _integer(path, attempt.get("id"), "id", 1) != run_id:
            raise _payload_failure(path, f"attempt belongs to run {attempt.get('id')}, not {run_id}")
        if _integer(path, attempt.get("run_attempt"), "run_attempt", 1) != number:
            raise _payload_failure(path, f"attempt {number} was asked for, {attempt.get('run_attempt')} answered")
        _text(path, attempt.get("status"), "status")
        _optional_text(path, attempt.get("conclusion"), "conclusion")
        return attempt

    @staticmethod
    def _check_suite_record(path: str, suite: dict[str, Any]) -> dict[str, Any]:
        """A check suite with every consumed field typed; a count nobody sent is not one."""
        suite_id = _integer(path, suite.get("id"), "check suite id")
        where = f"check suite {suite_id}"
        _text(path, suite.get("status"), f"{where} status")
        _optional_text(path, suite.get("conclusion"), f"{where} conclusion")
        app = suite.get("app")
        app_slug = None if app is None else _optional_text(path, _object(path, app, f"{where} app").get("slug"), f"{where} app.slug")
        count = _integer(path, suite.get("latest_check_runs_count"), f"{where} latest_check_runs_count")
        # The parent record carries the url into the bundle; untyped, a number there failed the canonical encoder.
        _optional_text(path, suite.get("url"), f"{where} url")
        return {"raw": suite, "app_slug": app_slug, "latest_check_runs_count": count}

    def _collect_ci(self, obs: ObservationSet, base: str, default_branch: str, commits_by_sha: dict[str, dict[str, Any]]) -> None:
        since = timeutil.minus_days(self.now, INTEGRITY["window_days"])
        window_commits = [c for c in commits_by_sha.values() if timeutil.parse_ts(c["committed_at"]) >= since]
        commits_obs = obs.get(INV_COMMITS)
        common_conf = self._common(f"{base}/actions/workflows")
        common_rev = self._common(f"{base}/actions/runs?branch={default_branch}&created>={timeutil.utc_day(since)}")
        if commits_obs is None or not commits_obs.has_value:
            obs.add(Observation(observation_id=CI_CONFIGURED, status=UNKNOWN, value_type="boolean", reason_code="REVISIONS_UNAVAILABLE", **common_conf))
            obs.add(Observation(observation_id=CI_REVISIONS, status=UNKNOWN, value_type="series", reason_code="REVISIONS_UNAVAILABLE", **common_rev))
            return

        workflows_total: int | None = None
        workflows_failure: Exception | None = None
        workflows_path = f"{base}/actions/workflows"
        try:
            workflows_total = _workflows_total(workflows_path, self.client.get(workflows_path, {"per_page": 1}))
        except (ApiFailure, NetworkFailure) as exc:
            workflows_failure = exc

        parents_by_sha: dict[str, list[dict[str, Any]]] = {}
        runs_complete = True
        runs_shifted = False
        attempts_complete = True
        runs_failure: Exception | None = None
        runs_seen = 0
        if workflows_total:
            try:
                runs, runs_complete = self.client.paginate(
                    f"{base}/actions/runs",
                    {"branch": default_branch, "created": f">={timeutil.utc_day(since)}"},
                    MAX_RUN_PAGES,
                    items_key="workflow_runs",
                    total_key="total_count",
                )
            except (ApiFailure, NetworkFailure) as exc:
                runs_failure = exc
                runs = []
            attempt_lookups = 0
            runs_path = f"{base}/actions/runs"
            try:
                seen_runs: set[int] = set()
                for run in _rows(runs_path, runs):
                    # Every run is validated before the window is applied: a run
                    # whose head cannot be read is not an out-of-window run
                    # (PV-AUDIT-GITHUB-CI-PAYLOAD-001). The fields the parent
                    # record carries into the bundle are typed too: a number
                    # where a name belongs would otherwise fail the canonical
                    # encoder and cost the whole project its bundle.
                    sha = _text(runs_path, run.get("head_sha"), "head_sha")
                    run_id = _integer(runs_path, run.get("id"), "id", 1)
                    current_attempt = _integer(runs_path, run.get("run_attempt"), f"run {run_id} run_attempt", 1)
                    _text(runs_path, run.get("status"), f"run {run_id} status")
                    _optional_text(runs_path, run.get("conclusion"), f"run {run_id} conclusion")
                    for field in ("name", "event", "html_url"):
                        _optional_text(runs_path, run.get(field), f"run {run_id} {field}")
                    _optional_integer(runs_path, run.get("workflow_id"), f"run {run_id} workflow_id")
                    if run_id in seen_runs:
                        # Page-number pagination over a list that grew between
                        # pages repeats a run, and may have skipped another.
                        runs_shifted = True
                        continue
                    seen_runs.add(run_id)
                    if sha not in commits_by_sha:
                        continue
                    runs_seen += 1
                    prior: list[dict[str, Any]] = []
                    if current_attempt > 1:
                        wanted = list(range(max(1, current_attempt - MAX_ATTEMPTS_PER_RUN), current_attempt))
                        for number in wanted:
                            if attempt_lookups >= MAX_ATTEMPT_LOOKUPS:
                                attempts_complete = False
                                break
                            attempt_lookups += 1
                            attempt_path = f"{runs_path}/{run_id}/attempts/{number}"
                            try:
                                prior.append(self._attempt_record(attempt_path, self.client.get(attempt_path), run_id, number))
                            except NetworkFailure:
                                attempts_complete = False
                            except ApiFailure as exc:
                                if exc.reason_code == "UNEXPECTED_PAYLOAD":
                                    raise
                                attempts_complete = False
                        if current_attempt - 1 > MAX_ATTEMPTS_PER_RUN:
                            attempts_complete = False
                    parents_by_sha.setdefault(sha, []).append(github_ci.actions_parent(run, prior))
            except ApiFailure as exc:
                runs_failure = exc
            self.notes.append("CI_SURFACE:GITHUB_ACTIONS_ONLY")
            if runs_seen:
                self.notes.append("CHECKS_SURFACE_NOT_COLLECTED")

        # The check-suite surface is sampled per revision, newest first, when
        # no Actions run was seen. Its coverage is tracked on its own (#12
        # finding 1): how many revisions were planned and examined, whether
        # every suite page was read, and why sampling stopped. A truncated
        # sample, a failed fetch or a spent budget make the series PARTIAL;
        # the parents already collected are kept, a failure among them stays.
        suites_planned = 0
        suites_sampled = 0
        suites_pages_complete = True
        suites_stop: str | None = None
        suites_failure: Exception | None = None
        if not runs_seen and not runs_failure:
            planned = sorted(window_commits, key=lambda c: (c["committed_at"], c["sha"]), reverse=True)
            suites_planned = len(planned)
            for commit in planned[:MAX_SUITE_REVISIONS]:
                try:
                    suites, page_complete = self.client.paginate(f"{base}/commits/{commit['sha']}/check-suites", {}, MAX_SUITE_PAGES, items_key="check_suites")
                except (ApiFailure, NetworkFailure) as exc:
                    suites_failure = exc
                    suites_stop = exc.reason_code if isinstance(exc, ApiFailure) else "NETWORK"
                    break
                if not page_complete and not suites:
                    # The budget refused the first page: this revision was not
                    # examined at all, and must not be counted as if it had
                    # shown no suites (that made ci.configured a false "false").
                    suites_pages_complete = False
                    suites_stop = suites_stop or self.client.incomplete_reason()
                    break
                suites_sampled += 1
                if not page_complete:
                    suites_pages_complete = False
                    suites_stop = suites_stop or self.client.incomplete_reason()
                suites_path = f"{base}/commits/{commit['sha']}/check-suites"
                try:
                    validated = [self._check_suite_record(suites_path, suite) for suite in _rows(suites_path, suites)]
                except ApiFailure as exc:
                    suites_failure = exc
                    suites_stop = exc.reason_code
                    break
                for suite in validated:
                    if suite["app_slug"] == "github-actions" and workflows_total:
                        continue
                    if suite["latest_check_runs_count"] == 0:
                        continue
                    parents_by_sha.setdefault(commit["sha"], []).append(github_ci.check_suite_parent(suite["raw"]))
                if self.client.budget_exhausted:
                    suites_stop = suites_stop or BUDGET_EXHAUSTED
                    break
            if suites_failure is None and suites_sampled < suites_planned:
                suites_stop = suites_stop or ("CHECK_SUITE_SAMPLE_CAPPED" if suites_sampled >= MAX_SUITE_REVISIONS else BUDGET_EXHAUSTED)
            if suites_sampled:
                self.notes.append("CI_SURFACE:GITHUB_CHECK_SUITES_SAMPLED")
        suites_complete = suites_failure is None and suites_pages_complete and suites_sampled == suites_planned

        any_parents = any(parents_by_sha.values())
        if workflows_failure is not None:
            # The Actions surface could not be asked at all. When check suites
            # then supply the evidence, the collection is legitimately
            # parent-level, but a reader of the receipt must be able to tell
            # "no Actions runs" from "Actions could not be read", exactly as
            # CHECK_SUITES_UNAVAILABLE says it for the other surface.
            reason = workflows_failure.reason_code if isinstance(workflows_failure, ApiFailure) else "NETWORK"
            self.notes.append(f"WORKFLOWS_UNAVAILABLE:{reason}")
        if workflows_total and workflows_total > 0:
            obs.add(Observation(observation_id=CI_CONFIGURED, status=AVAILABLE, value_type="boolean", value=True, evidence_ref={"workflows_total": workflows_total}, **common_conf))
        elif any_parents:
            obs.add(Observation(observation_id=CI_CONFIGURED, status=AVAILABLE, value_type="boolean", value=True, evidence_ref={"check_suites": True}, **common_conf))
        elif workflows_failure is not None:
            obs.add(_failure_observation(CI_CONFIGURED, "boolean", workflows_failure, common_conf))
        elif suites_failure is not None:
            obs.add(_failure_observation(CI_CONFIGURED, "boolean", suites_failure, common_conf))
        elif window_commits and not suites_complete:
            # "false" needs every planned revision read to its last page.
            obs.add(Observation(observation_id=CI_CONFIGURED, status=UNKNOWN, value_type="boolean", reason_code="SAMPLE_INCOMPLETE", **common_conf))
        else:
            obs.add(Observation(observation_id=CI_CONFIGURED, status=AVAILABLE, value_type="boolean", value=False, evidence_ref={"workflows_total": 0, "check_suites_sampled": suites_sampled}, **common_conf))

        if runs_failure is not None:
            obs.add(_failure_observation(CI_REVISIONS, "series", runs_failure, common_rev))
            return
        if suites_failure is not None and not any_parents and not workflows_total:
            obs.add(_failure_observation(CI_REVISIONS, "series", suites_failure, common_rev))
            return
        if suites_failure is not None:
            reason = suites_failure.reason_code if isinstance(suites_failure, ApiFailure) else "NETWORK"
            self.notes.append(f"CHECK_SUITES_UNAVAILABLE:{reason}")
        records = github_ci.build_revision_records(window_commits, parents_by_sha)
        complete = runs_complete and not runs_shifted and attempts_complete and suites_complete and (commits_obs.status == AVAILABLE)
        reason = None
        if runs_shifted:
            reason = LISTING_SHIFTED
        elif not runs_complete:
            reason = self.client.incomplete_reason()
        elif not attempts_complete:
            reason = "ATTEMPT_HISTORY_INCOMPLETE"
        elif not suites_complete:
            reason = "CHECK_SUITES_INCOMPLETE"
        elif commits_obs.status != AVAILABLE:
            reason = "REVISIONS_PARTIAL"
        obs.add(
            Observation(
                observation_id=CI_REVISIONS,
                status=AVAILABLE if complete else PARTIAL,
                value_type="series",
                value=records,
                coverage={
                    "window_start": timeutil.format_ts(since),
                    "window_end": self.observed_at,
                    "runs_complete": runs_complete,
                    "attempts_complete": attempts_complete,
                    "suites_complete": suites_complete,
                    "suite_revisions_planned": suites_planned,
                    "suite_revisions_examined": suites_sampled,
                    "suites_stop_reason": suites_stop,
                    "outcome_map_version": github_ci.OUTCOME_MAP_VERSION,
                    "surface": "github_actions" if runs_seen else ("github_check_suites" if any_parents else "none"),
                },
                reason_code=reason,
                evidence_ref={"branch": default_branch, "runs_matched": runs_seen},
                **common_rev,
            )
        )
