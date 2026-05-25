from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .food_cache import get_cached_food, save_food


@dataclass
class USDAFoodEntry:
    description: str
    fdc_id: int
    data_type: str
    brand_owner: str


load_dotenv()

FDC_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# FDC search `dataType` values in descending order of preference.
# `search_foods` queries each in turn, so results come back grouped by
# type. Survey (FNDDS) is preferred first: its entries reliably carry
# Energy and a complete, consistent nutrient profile, whereas Foundation
# foods (gold-standard analytical data) are inconsistent -- e.g. pure
# oils have no Energy at all. (SR Legacy omitted.)
DATA_TYPE_PREFERENCE = ("Survey (FNDDS)", "Foundation", "Branded")

# USDA's FDC API gateway intermittently serves bogus 400/404 errors (with an
# HTML body) for otherwise-valid requests; retrying the identical
# request almost always succeeds. We therefore retry on 400 and 404 here,
# even though neither is normally a retryable status.
_RETRY_STATUSES = frozenset({400, 404, 500, 502, 503, 504})


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


def _has_energy(food: dict[str, Any]) -> bool:
    """True if a search result reports food energy in kcal.

    FDC names energy differently by data type -- "Energy" (FNDDS / SR Legacy)
    and "Energy (Atwater General/Specific Factors)" (Foundation) -- so we match
    any nutrient whose name contains "energy" and whose unit is kcal.

    Args:
        food (dict[str, Any]): A single food record from `foods/search`.

    Returns:
        bool: Whether the record carries a kcal Energy value.
    """
    for nutrient in food.get("foodNutrients", []):
        name = (nutrient.get("nutrientName") or "").lower()
        unit = (nutrient.get("unitName") or "").lower()
        if "energy" in name and unit == "kcal" and nutrient.get("value") is not None:
            return True
    return False


def search_foods(
    query: str, page_size: int = 10, require_energy: bool = True
) -> list[dict[str, Any]]:
    """Search for foods in the USDA FoodData Central database.

    Queries each data type in `DATA_TYPE_PREFERENCE` separately and concatenates
    the results, so preferred data types always appear first.

    Args:
        query (str): Name of food to search.
        page_size (int, optional): Max results to fetch per data type. Defaults
            to 10.
        require_energy (bool, optional): Drop results with no kcal Energy value,
            since they are not usable for nutrient tracking. Defaults to True.

    Returns:
        list[dict[str, Any]]: Matching food records, grouped by data-type
            preference (up to `page_size` per type, fewer if filtered).
    """
    foods: list[dict[str, Any]] = []
    for data_type in DATA_TYPE_PREFERENCE:
        response = _get_from_USDA(
            "foods/search",
            {"query": query, "pageSize": page_size, "dataType": data_type},
        )
        response_json = response.json()
        matches = response_json.get("foods", [])
        if require_energy:
            matches = [food for food in matches if _has_energy(food)]
        print(f"{data_type}: {response_json.get('totalHits', -1)} hits, "
              f"{len(matches)} kept")
        foods.extend(matches)
    return foods


def get_food_details(fdc_id: int) -> dict[str, Any]:
    """Fetch full details, including nutrients, for a single FDC food.

    Checks the local cache first (see src/food_cache.py): on a hit the food is
    returned without calling the FDC API; on a miss it is fetched from FDC,
    stored in the cache, and returned. Note that a cache hit returns the cached
    projection (description, data type, brand owner, and nutrients), not the
    full raw FDC payload.

    Args:
        fdc_id (int): FoodData Central identifier of the food.

    Returns:
        dict[str, Any]: The food record, from the local cache or the FDC
            `/food/{fdcId}` endpoint.
    """
    cached = get_cached_food(fdc_id)
    if cached is not None:
        print(f"[FDC] cache hit for fdc_id={fdc_id}")
        return cached

    response = _get_from_USDA(f"food/{fdc_id}")
    details = response.json()
    save_food(details)
    return details


def get_food_entries_from_response(response: list[dict[str, Any]]) -> list[USDAFoodEntry]:
    return [USDAFoodEntry(
        description=food.get("description", "description unknown"),
        fdc_id=food.get("fdcId", 0),
        data_type=food.get("dataType", "dataType unknown"),
        brand_owner=food.get("brandOwner", "")
    ) for food in response]
