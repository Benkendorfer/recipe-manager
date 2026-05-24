# Recipe Manager

A Streamlit app for building recipes and tracking their nutrition, backed by the
USDA [FoodData Central](https://fdc.nal.usda.gov/) (FDC) database.

**Phase 0:** manual recipe entry, USDA ingredient lookup, and SQLite storage.

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

## Project structure

| Path                 | Purpose                                              |
| -------------------- | ---------------------------------------------------- |
| `app.py`             | Streamlit UI: ingredient search and nutrient display |
| `src/fdc_client.py`  | Client for the USDA FoodData Central API             |
| `environment.yml`    | Conda environment definition                         |

## Notes

- USDA ingredient search queries Foundation, Survey (FNDDS), and Branded food
  types in that order of preference, so curated results appear first.
- The FDC API gateway intermittently returns spurious `400`/`404` errors;
  `fdc_client` retries these automatically.
