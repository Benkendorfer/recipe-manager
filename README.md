# Recipe Manager

A Streamlit app for building recipes and tracking their nutrition, backed by the
USDA [FoodData Central](https://fdc.nal.usda.gov/) (FDC) database.

**Phase 0:** manual recipe entry, USDA ingredient lookup, and SQLite storage.

- [Recipe Manager](#recipe-manager)
  - [Setup](#setup)
  - [Running](#running)
  - [Tests](#tests)
  - [Project structure](#project-structure)
  - [Notes](#notes)

## Setup

1. **Create the conda environment** (Python 3.14):

   ```bash
   conda env create -f environment.yml
   conda activate recipe_manager
   ```

2. **Add a USDA API key.** Get a free key at
   [fdc.nal.usda.gov/api-key-signup.html](https://fdc.nal.usda.gov/api-key-signup.html),
   then create a `.env` file in the project root:

   ```txt
   FDC_API_KEY=your_key_here
   ```

## Running

```bash
streamlit run app.py
```

## Tests

```bash
pytest
```

(`environment.yml` installs the test dependencies via `-e .[test]`.)

## Project structure

| Path                | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `app.py`            | Streamlit UI: ingredient search and nutrient display |
| `src/fdc_client.py` | Client for the USDA FoodData Central API             |
| `src/food_cache.py` | Local SQLite cache for FDC lookups (SQLModel models) |
| `environment.yml`   | Conda environment definition                         |
| `tests/`            | Pytest unit tests for the cache                      |

## Notes

- Ingredient search prefers Survey (FNDDS) foods, then Foundation, then Branded,
  and skips entries that lack energy data.
- Searched foods are cached in a local SQLite database (`db/recipe_cache.db`),
  so repeat lookups are served from disk instead of the FDC API.
- The FDC API gateway intermittently returns spurious `400`/`404` errors;
  `fdc_client` retries these automatically.
