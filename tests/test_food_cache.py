"""Unit tests for src/food_cache.py.

These are white-box tests: they reach into the module's engine/models to assert
on the stored rows, not just the public dicts.
"""

from sqlmodel import Session, SQLModel, select

from src import food_cache
from src.food_cache import (
    FDCEntry,
    Food,
    FoodNutrient,
    Nutrient,
    get_cached_food,
    save_food,
    search_cached_foods,
)


# --- helpers -----------------------------------------------------------

def nutrient_item(name="Energy", nid=1008, unit="kcal", amount=884.0,
                  number="208", rank=300):
    """Build one FDC `foodNutrients` entry."""
    return {
        "nutrient": {"id": nid, "name": name, "unitName": unit,
                     "number": number, "rank": rank},
        "amount": amount,
    }


def make_details(fdc_id=111, description="Olive oil", data_type="Foundation",
                 brand_owner=None, nutrients=None):
    """Build a minimal FDC /food/{fdcId} payload for save_food()."""
    if nutrients is None:
        nutrients = [nutrient_item()]
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": data_type,
        "brandOwner": brand_owner,
        "foodNutrients": nutrients,
    }


def count(model):
    with Session(food_cache._engine) as session:
        return len(session.exec(select(model)).all())


# --- round trip --------------------------------------------------------

def test_save_and_get_roundtrip():
    save_food(make_details(fdc_id=111, description="Olive oil",
                           data_type="Foundation", brand_owner="Acme"))

    got = get_cached_food(111)

    assert got is not None
    assert got["fdcId"] == 111
    assert got["description"] == "Olive oil"
    assert got["dataType"] == "Foundation"
    assert got["brandOwner"] == "Acme"
    assert got["canonicalAmount"] == 100.0
    assert got["canonicalUnit"] == "g"
    assert got["foodNutrients"] == [
        {"nutrient": {"id": 1008, "name": "Energy", "unitName": "kcal"},
         "amount": 884.0}
    ]


def test_get_cached_food_miss_returns_none():
    assert get_cached_food(999) is None


# --- save_food filtering -----------------------------------------------

def test_save_food_skips_invalid_nutrients():
    details = make_details(nutrients=[
        nutrient_item(name="Energy", nid=1008, amount=884.0),   # kept
        nutrient_item(name="Protein", nid=1003, amount=None),   # no amount
        nutrient_item(name="", nid=1004, amount=10.0),          # no name
        nutrient_item(name="Fat", nid=None, amount=20.0),       # no id
    ])

    save_food(details)

    got = get_cached_food(111)
    names = [n["nutrient"]["name"] for n in got["foodNutrients"]]
    assert names == ["Energy"]


def test_save_food_stores_nutrient_metadata():
    save_food(make_details(nutrients=[
        nutrient_item(name="Energy", nid=1008, unit="kcal",
                      number="208", rank=300)]))

    with Session(food_cache._engine) as session:
        nutrient = session.get(Nutrient, 1008)
        assert nutrient is not None
        assert nutrient.name == "Energy"
        assert nutrient.unit == "kcal"
        assert nutrient.fdc_number == "208"
        assert nutrient.fdc_rank == 300


# --- nutrient de-duplication -------------------------------------------

def test_shared_nutrient_is_deduplicated():
    energy = nutrient_item(name="Energy", nid=1008, amount=884.0)
    fat = nutrient_item(name="Total fat", nid=1004, unit="g", amount=100.0)
    save_food(make_details(fdc_id=111, description="Olive oil",
                           nutrients=[energy, fat]))
    save_food(make_details(fdc_id=222, description="Butter",
                           nutrients=[energy, fat]))

    # Two foods, two distinct nutrients, four measurements.
    assert count(Food) == 2
    assert count(Nutrient) == 2
    assert count(FoodNutrient) == 4

    # Reverse navigation: every food that contains Energy.
    with Session(food_cache._engine) as session:
        energy_row = session.get(Nutrient, 1008)
        descriptions = sorted(
            m.food.description for m in energy_row.measurements)
    assert descriptions == ["Butter", "Olive oil"]


# --- re-cache (upsert) -------------------------------------------------

def test_recache_replaces_without_duplicates():
    save_food(make_details(fdc_id=111, description="Olive oil", nutrients=[
        nutrient_item(name="Energy", nid=1008, amount=884.0),
        nutrient_item(name="Total fat", nid=1004, unit="g", amount=100.0),
    ]))
    # Re-cache the same fdc_id with updated description and a single nutrient.
    save_food(make_details(fdc_id=111, description="Olive oil, extra virgin",
                           nutrients=[nutrient_item(name="Energy", nid=1008,
                                                    amount=900.0)]))

    got = get_cached_food(111)
    assert got["description"] == "Olive oil, extra virgin"
    assert len(got["foodNutrients"]) == 1
    assert got["foodNutrients"][0]["amount"] == 900.0

    assert count(Food) == 1            # not duplicated
    assert count(FDCEntry) == 1        # extension replaced, not duplicated
    assert count(FoodNutrient) == 1    # stale measurement removed


def test_recache_keeps_shared_nutrient_rows():
    energy = nutrient_item(name="Energy", nid=1008, amount=884.0)
    save_food(make_details(fdc_id=111, nutrients=[energy]))
    save_food(make_details(fdc_id=222, nutrients=[energy]))

    # Re-caching 111 must not delete the shared Energy nutrient (222 still uses it).
    save_food(make_details(fdc_id=111, nutrients=[energy]))

    assert count(Nutrient) == 1
    assert get_cached_food(222) is not None


# --- search_cached_foods -----------------------------------------------

def test_search_cached_foods_substring_case_insensitive():
    save_food(make_details(fdc_id=1, description="Olive oil"))
    save_food(make_details(fdc_id=2, description="Onion, raw"))
    save_food(make_details(fdc_id=3, description="EXTRA VIRGIN OLIVE OIL",
                           data_type="Branded", brand_owner="Acme"))

    hits = search_cached_foods("olive")

    assert [h["fdcId"] for h in hits] == [3, 1]  # ordered by description
    assert all("olive" in h["description"].lower() for h in hits)
    assert hits[0] == {
        "fdcId": 3, "description": "EXTRA VIRGIN OLIVE OIL",
        "dataType": "Branded", "brandOwner": "Acme",
    }


def test_search_cached_foods_no_match_returns_empty():
    save_food(make_details(fdc_id=1, description="Olive oil"))
    assert search_cached_foods("banana") == []


# --- lazy schema creation ----------------------------------------------

def test_ensure_schema_creates_tables_on_first_use():
    # Simulate a brand-new process: no tables, schema not yet initialized.
    SQLModel.metadata.drop_all(food_cache._engine)
    food_cache._schema_ready = False

    # Should lazily (re)create the schema rather than raising "no such table".
    assert get_cached_food(123) is None
