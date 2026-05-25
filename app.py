import streamlit as st

from src.fdc_client import (
    USDAFoodEntry,
    get_food_details,
    get_food_entries_from_response,
    search_foods,
)
from src.food_cache import search_cached_foods


def format_food_option(food: USDAFoodEntry) -> str:
    return f"{food.description} [{food.data_type}, FDC ID: {food.fdc_id}, brand_owner: {food.brand_owner}]"


def _store_results(results: list[dict], source: str, query: str) -> None:
    st.session_state["food_results"] = results
    st.session_state["results_source"] = source
    st.session_state["results_query"] = query


def main() -> None:
    st.title("Recipe Health Tracker")
    st.subheader("Ingredient lookup")

    query = st.text_input(
        "Ingredient name", placeholder="e.g. olive oil, onion, chicken breast")

    if not query:
        return

    # Drop stale results when the query changes, so we never show matches for a
    # previous ingredient.
    if st.session_state.get("results_query") != query:
        for key in ("food_results", "results_source", "results_query"):
            st.session_state.pop(key, None)

    # Primary action: look in the local cache first, and only fall back to the
    # USDA API on a cache miss.
    if st.button("Search"):
        cached = search_cached_foods(query)
        if cached:
            _store_results(cached, "cache", query)
        else:
            with st.spinner("Not in cache - searching FoodData Central..."):
                _store_results(search_foods(query, page_size=10), "usda", query)

    # Secondary action: let the user query USDA even when the cache has matches.
    if st.session_state.get("results_source") == "cache":
        if st.button("Search USDA for more matches"):
            with st.spinner("Searching FoodData Central..."):
                _store_results(search_foods(query, page_size=10), "usda", query)

    results = st.session_state.get("food_results", [])
    foods = get_food_entries_from_response(results)

    if not foods:
        return

    if st.session_state.get("results_source") == "cache":
        st.caption(f"Showing {len(foods)} match(es) from your local cache.")
    else:
        st.caption(f"Showing {len(foods)} match(es) from USDA FoodData Central.")

    selected_food = st.selectbox(
        "Select the closest food match",
        options=foods,
        format_func=format_food_option,
    )

    if st.button("Use this food"):
        details = get_food_details(selected_food.fdc_id)

        st.session_state["selected_food_details"] = details

        st.success(f"Selected: {selected_food.description}")

    if "selected_food_details" in st.session_state:
        details = st.session_state["selected_food_details"]

        st.subheader("Nutrients")

        nutrients = details.get("foodNutrients", [])

        rows = []
        for item in nutrients:
            nutrient = item.get("nutrient", {})
            name = nutrient.get("name")
            unit = nutrient.get("unitName")
            amount = item.get("amount")

            if name and amount is not None:
                rows.append(
                    {
                        "nutrient": name,
                        "amount": amount,
                        "unit": unit,
                    }
                )

        st.dataframe(rows, use_container_width=True)


if __name__ == "__main__":
    main()
