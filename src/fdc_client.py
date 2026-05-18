from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class USDAFoodEntry:
    description: str
    fdc_id: int
    data_type: str
    brand_owner: str


load_dotenv()

FDC_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# USDA's FDC API gateway intermittently serves a bogus 404 (with an HTML body)
# for otherwise-valid requests; retrying the identical request almost always
# succeeds. We therefore retry on 404 here, even though 404 is normally not a
# retryable status.
_RETRY_STATUSES = frozenset({404, 500, 502, 503, 504})


def _make_session() -> requests.Session:
    """Build a Session that retries the FDC gateway's transient failures."""
    retry = Retry(
        total=5,
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=frozenset({"GET"}),
        backoff_factor=0.5,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


_SESSION = _make_session()


def _get_api_key() -> str:
    """Return the FDC API key, raising a clear error if it is missing or blank."""
    key = os.environ.get("FDC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "FDC_API_KEY is not set. Add it to your .env file "
            "(get a free key at https://fdc.nal.usda.gov/api-key-signup.html)."
        )
    return key


def _get_from_USDA(path: str, params: dict[str, Any] | None = None) -> requests.Response:
    """GET an FDC endpoint, report rate-limit usage, and raise on HTTP errors.

    Args:
        path (str): Endpoint path relative to `FDC_BASE_URL`, e.g. `foods/search`.
        params (dict, optional): Query params; the API key is added automatically.

    Returns:
        requests.Response: The successful response.
    """
    query: dict[str, Any] = {"api_key": _get_api_key()}
    if params:
        query.update(params)
    response = _SESSION.get(
        f"{FDC_BASE_URL}/{path}",
        params=query,
        timeout=20,
    )
    # Printed before raise_for_status so usage shows even on a 429/error.
    limit = response.headers.get("X-RateLimit-Limit", "?")
    remaining = response.headers.get("X-RateLimit-Remaining", "?")
    print(f"[FDC] rate limit: {remaining}/{limit} remaining")
    response.raise_for_status()
    return response


def search_foods(query: str, page_size: int = 10) -> list[dict[str, Any]]:
    """Search for foods in the USDA FoodData Central database.

    Args:
        query (str): Name of food to search
        page_size (int, optional): Results to return per page. Defaults to 10.

    Returns:
        list[dict[str, Any]]: Matching food records from the FDC search endpoint.
    """
    response = _get_from_USDA("foods/search", {"query": query, "pageSize": page_size})
    response_json = response.json()
    print(f"Results: {response_json.get("totalHits", -1)}")
    return response_json.get("foods", [])


def get_food_details(fdc_id: int) -> dict[str, Any]:
    """Fetch full details, including nutrients, for a single FDC food.

    Args:
        fdc_id (int): FoodData Central identifier of the food.

    Returns:
        dict[str, Any]: The food record from the FDC `/food/{fdcId}` endpoint.
    """
    response = _get_from_USDA(f"food/{fdc_id}")
    return response.json()


def get_food_entries_from_response(response: list[dict[str, Any]]) -> list[USDAFoodEntry]:
    return [USDAFoodEntry(
        description=food.get("description", "description unknown"),
        fdc_id=food.get("fdcId", 0),
        data_type=food.get("dataType", "dataType unknown"),
        brand_owner=food.get("brandOwner", "")
    ) for food in response]
