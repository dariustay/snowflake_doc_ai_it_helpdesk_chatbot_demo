import streamlit as st
from typing import List, Dict, Any
from utils.snowflake_utils import session, root


def query_cortex_search_service(query: str, service: str, limit: int, metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Execute a search against a specified Cortex Search service and format results.
    """
    
    if not service:
        st.warning("Please select a search service.")
        return []

    idx = next((i for i, m in enumerate(metadata) if m["name"] == service), None)
    if idx is None or not metadata[idx]["search_column"]:
        st.error(f"Invalid service metadata for '{service}'.")
        return []

    search_col = metadata[idx]["search_column"]
    svc = (
        root.databases[session.get_current_database()]
            .schemas[session.get_current_schema()]
            .cortex_search_services[service]
    )
    try:
        resp = svc.search(
            query=query,
            columns=[
                search_col,
                'FILE_NAME',
                'TITLE_VALUE',
                'LAST_UPDATED_VALUE',
                'APPLIES_TO_VALUE',
                'SNOWFLAKE_FILE_URL'
            ],
            limit=limit
        )
    except Exception as e:
        st.error(f"Search failed: {e}")
        return []

    # Format and return results list
    return [
        {
            "file": rec["FILE_NAME"],
            "chunk": rec[search_col],
            "title": rec["TITLE_VALUE"],
            "last_updated": rec["LAST_UPDATED_VALUE"],
            "applies_to": rec['APPLIES_TO_VALUE'],
            "file_url":     rec["SNOWFLAKE_FILE_URL"]
        }
        for rec in resp.results
    ]