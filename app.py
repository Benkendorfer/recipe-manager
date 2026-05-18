import streamlit as st

from src.fdc_client import (
    USDAFoodEntry,
    get_food_details,
    get_food_entries_from_response,
    search_foods,
)


def format_food_option(food: USDAFoodEntry) -> str:
    return f"{food.description} [{food.data_type}, FDC ID: {food.fdc_id}, brand_owner: {food.brand_owner}]"


def main() -> None:
    st.title("Recipe Health Tracker")
    st.subheader("USDA ingredient lookup")

    query = st.text_input(
        "Ingredient name", placeholder="e.g. olive oil, onion, chicken breast")

    if not query:
        return

    if st.button("Search USDA"):
        with st.spinner("Searching FoodData Central..."):
            st.session_state["food_results"] = search_foods(
                query, page_size=10)

    foods = get_food_entries_from_response(
        st.session_state.get("food_results", []))

    if not foods:
        return

    selected_food = st.selectbox(
        "Select the closest USDA food match",
        options=foods,
        format_func=format_food_option,
    )

    st.write("Selected food:")
    st.json(
        {
            "fdcId": selected_food.fdc_id,
            "description": selected_food.description,
            "dataType": selected_food.data_type,
        }
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
