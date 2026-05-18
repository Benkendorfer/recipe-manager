import streamlit as st

from src.fdc_client import search_foods


def main() -> None:
    st.title("Recipe Health Tracker")
    st.write("Phase 0: manual recipe entry and SQLite storage")


if __name__ == "__main__":
    main()
