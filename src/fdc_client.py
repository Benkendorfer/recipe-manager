from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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


def search_foods(query: str, page_size: int = 10) -> list[dict[str, Any]]:
    """Search for foods in the USDA FoodData Central database.

    Args:
        query (str): Name of food to search
        page_size (int, optional): Results to return per page. Defaults to 10.

    Returns:
        list[dict[str, Any]]: Matching food records from the FDC search endpoint.
    """
    response = _SESSION.get(
        f"{FDC_BASE_URL}/foods/search",
        params={
            "api_key": _get_api_key(),
            "query": query
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("foods", [])
