"""Local SQL cache for USDA FoodData Central (FDC) lookups (GitHub issue #6).

Outline / shell. The SQLModel models below are the single source of truth for
the cache schema; ``init_db`` creates the tables from them. The backend is
chosen by ``DB_URL`` so the same code runs against a local SQLite file now and a
server database (Postgres, ...) later -- only the URL changes.

Wiring: src/fdc_client.get_food_details() checks ``get_cached_food(fdc_id)``
first and falls back to the FDC API on a miss, calling ``save_food(details)``
to populate the cache.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import UniqueConstraint, event
from sqlmodel import (
    Field, Relationship, Session, SQLModel, col, create_engine, select)


# --- Engine ------------------------------------------------------------

# Default to a SQLite file at the repo root so the cache lives in one
# place regardless of the process's working directory. Override with e.g.
# RECIPE_DB_URL=postgresql+psycopg://user:pass@host/db to point the cache
# at a server database
_DEFAULT_DB_PATH = Path(__file__).resolve(
).parent.parent / "db" / "recipe_cache.db"
DB_URL = os.environ.get("RECIPE_DB_URL", f"sqlite:///{_DEFAULT_DB_PATH}")

_engine = create_engine(DB_URL, echo=False)


@event.listens_for(_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enforce foreign keys on SQLite, which ignores them by default.

    Without this, the ``ON DELETE CASCADE`` and FK constraints below are not
    honored on the SQLite backend (other backends enforce them already).
    """
    if _engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# --- Models ------------------------------------------------------------

class Food(SQLModel, table=True):
    """A food, independent of which source database it came from.

    Holds only source-agnostic fields. Source-specific metadata lives in a
    per-source extension table (e.g. FDCEntry) linked one-to-one, so adding a
    new source means adding a table rather than widening ``foods``.
    """
    __tablename__ = "foods"  # type: ignore

    food_id: int | None = Field(default=None, primary_key=True)  # surrogate PK
    description: str
    source: str  # discriminator: which extension table holds the metadata
    # The reference quantity the nutrient amounts (FoodNutrient.amount) are
    # measured against, e.g. 100 g. Needed to interpret/scale the nutrients.
    canonical_amount: float
    canonical_unit: str
    cached_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))

    # One-to-one extension tables (one per source). Add more as sources grow.
    # Optional["FDCEntry"] (not "FDCEntry | None") so the forward ref wraps only
    # the class name -- SQLAlchemy can't resolve a fully-stringized union.
    fdc_entry: Optional["FDCEntry"] = Relationship(
        back_populates="food",
        sa_relationship_kwargs={
            "uselist": False, "cascade": "all, delete-orphan"},
    )
    nutrients: list["FoodNutrient"] = Relationship(
        back_populates="food",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class FDCEntry(SQLModel, table=True):
    """FDC-specific metadata for a food (one-to-one extension of ``foods``).

    Keyed by ``food_id`` (PK == FK) so there is at most one FDC entry per food.
    ``fdc_id`` is FoodData Central's own identifier, kept unique for lookups.
    """
    __tablename__ = "fdc_entries"  # type: ignore

    food_id: int | None = Field(
        default=None, foreign_key="foods.food_id", ondelete="CASCADE",
        primary_key=True)
    fdc_id: int = Field(unique=True, index=True)  # FDC "fdcId"
    data_type: str | None = None                  # Foundation, Branded, ...
    brand_owner: str | None = None

    food: Food | None = Relationship(back_populates="fdc_entry")


class Nutrient(SQLModel, table=True):
    """A nutrient definition, shared across foods."""
    __tablename__ = "nutrients"  # type: ignore

    nutrient_id: int = Field(primary_key=True)
    name: str
    unit: str | None = None
    fdc_number: str | None = None
    fdc_rank: int | None = None

    measurements: list["FoodNutrient"] = Relationship(
        back_populates="nutrient"
    )


class FoodNutrient(SQLModel, table=True):
    """Association object: the amount of one nutrient in one food."""
    __tablename__ = "food_nutrients"  # type: ignore
    __table_args__ = (UniqueConstraint("food_id", "nutrient_id"),)

    id: int | None = Field(default=None, primary_key=True)
    # FK columns are Optional in Python (populated via the relationships below)
    # but NOT NULL in the database.
    food_id: int | None = Field(
        default=None, foreign_key="foods.food_id", ondelete="CASCADE",
        nullable=False, index=True)
    nutrient_id: int | None = Field(
        default=None, foreign_key="nutrients.nutrient_id",
        nullable=False, index=True)
    amount: float | None = None

    food: Food | None = Relationship(back_populates="nutrients")
    nutrient: Nutrient | None = Relationship(back_populates="measurements")


# --- Schema setup ------------------------------------------------------

_schema_ready = False


def _ensure_db_directory() -> None:
    """Create the parent directory of a file-based SQLite database.

    SQLite creates the database file but not the directory containing it, so a
    path like ``db/recipe_cache.db`` raises "unable to open database file"
    until ``db/`` exists. No-op for in-memory or non-SQLite backends.
    """
    if _engine.dialect.name != "sqlite":
        return
    database = _engine.url.database
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """Create the cache tables if they do not already exist."""
    global _schema_ready
    _ensure_db_directory()
    SQLModel.metadata.create_all(_engine)
    _schema_ready = True


def _ensure_schema() -> None:
    """Create the tables on first use, so callers need not call init_db()."""
    if not _schema_ready:
        init_db()


# --- FDC source adapter ------------------------------------------------
#
# The schema above is source-agnostic; the helpers below read/write FDC
# records specifically. A new source (e.g. Open Food Facts) would get its own
# adapter plus its own extension table, without touching the core tables.

# FDC reports foodNutrients amounts per 100 g of edible portion across all data
# types, so that is the canonical basis for the nutrient values we store.
_FDC_CANONICAL_AMOUNT = 100.0
_FDC_CANONICAL_UNIT = "g"


def _get_food_by_fdc_id(session: Session, fdc_id: int) -> Food | None:
    """Return the cached Food for an FDC id, or None if not cached."""
    return session.exec(
        select(Food).join(FDCEntry).where(FDCEntry.fdc_id == fdc_id)
    ).first()


def get_cached_food(fdc_id: int) -> dict[str, Any] | None:
    """Return a cached FDC food as a plain dict, or None on a cache miss.

    The returned shape mirrors the parts of fdc_client.get_food_details() that
    app.py consumes, so it can serve as a drop-in result on a cache hit.

    Args:
        fdc_id (int): FoodData Central identifier of the food.

    Returns:
        dict[str, Any] | None: The cached record, or None if not cached.

    TODO: treat rows older than a TTL as a miss (see Food.cached_at).
    """
    _ensure_schema()
    with Session(_engine) as session:
        food = _get_food_by_fdc_id(session, fdc_id)
        if food is None:
            return None

        fdc = food.fdc_entry
        assert fdc is not None  # an "fdc" food always has an FDC entry

        food_nutrients = []
        for measurement in food.nutrients:
            nutrient = measurement.nutrient
            assert nutrient is not None  # FK is NOT NULL: always present
            food_nutrients.append(
                {
                    "nutrient": {
                        "id": nutrient.nutrient_id,
                        "name": nutrient.name,
                        "unitName": nutrient.unit,
                    },
                    "amount": measurement.amount,
                }
            )

        return {
            "fdcId": fdc.fdc_id,
            "description": food.description,
            "dataType": fdc.data_type,
            "brandOwner": fdc.brand_owner,
            "canonicalAmount": food.canonical_amount,
            "canonicalUnit": food.canonical_unit,
            "foodNutrients": food_nutrients,
        }


def search_cached_foods(query: str) -> list[dict[str, Any]]:
    """Return cached foods whose description matches `query`.

    Case-insensitive substring match on the description. Each result is shaped
    like a `fdc_client.search_foods()` entry (fdcId/description/dataType/
    brandOwner), so cached and live results flow through the same UI code.

    Args:
        query (str): Substring to match against cached food descriptions.

    Returns:
        list[dict[str, Any]]: Matching cached foods (empty list on no match).
    """
    _ensure_schema()
    pattern = f"%{query}%"
    with Session(_engine) as session:
        rows = session.exec(
            select(Food, FDCEntry)
            .join(FDCEntry)
            .where(col(Food.description).ilike(pattern))
            .order_by(col(Food.description))
        ).all()
        return [
            {
                "fdcId": entry.fdc_id,
                "description": food.description,
                "dataType": entry.data_type,
                "brandOwner": entry.brand_owner,
            }
            for food, entry in rows
        ]


def save_food(details: dict[str, Any]) -> None:
    """Persist an FDC /food/{fdcId} record into the cache.

    Stores the subset of fields app.py uses today; extend as the app
    grows.

    Args:
        details (dict[str, Any]): JSON dict from fdc_client.get_food_details().
    """
    _ensure_schema()
    fdc_id = details["fdcId"]
    food = Food(
        description=details.get("description", ""),
        source="fdc",
        canonical_amount=_FDC_CANONICAL_AMOUNT,
        canonical_unit=_FDC_CANONICAL_UNIT,
        fdc_entry=FDCEntry(
            fdc_id=fdc_id,
            data_type=details.get("dataType"),
            brand_owner=details.get("brandOwner"),
        ),
    )

    with Session(_engine) as session:
        # Replace any prior entry so re-caching refreshes the stored data.
        # delete-orphan removes this food's FDC entry and measurements; the
        # shared Nutrient rows persist.
        existing = _get_food_by_fdc_id(session, fdc_id)
        if existing is not None:
            session.delete(existing)
            session.flush()

        # Add the food up front so each measurement appended below is tracked
        # by the session as soon as it is linked.
        session.add(food)

        for item in details.get("foodNutrients", []):
            meta = item.get("nutrient", {})
            amount = item.get("amount")
            nutrient_id = meta.get("id")
            if not meta.get("name") or amount is None or nutrient_id is None:
                continue

            # Get-or-create the shared nutrient definition, then attach a
            # measurement (amount) linking this food to it.
            nutrient = session.get(Nutrient, nutrient_id)
            if nutrient is None:
                nutrient = Nutrient(
                    nutrient_id=nutrient_id,
                    name=meta["name"],
                    unit=meta.get("unitName"),
                    fdc_number=meta.get("number"),
                    fdc_rank=meta.get("rank"),
                )
                session.add(nutrient)

            food.nutrients.append(
                FoodNutrient(amount=amount, nutrient=nutrient))

        session.commit()


if __name__ == "__main__":
    init_db()
    print(f"Initialized cache schema at {DB_URL}")
