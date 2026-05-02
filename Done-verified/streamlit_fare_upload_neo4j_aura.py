#!/usr/bin/env python3
"""
Streamlit UI: Upload Excel (.xlsx/.xls) file, extract (origin, destination, fare) triplets,
edit them, add static fields, and ingest into Neo4j Aura as Fare nodes.

Run from repo root:
    streamlit run streamlit_fare_upload_neo4j_aura.py

For production, move secrets to environment variables instead of hardcoding.
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from neo4j import GraphDatabase
import pandas as pd

# Connection defaults for Neo4j Aura or local Neo4j Desktop (override via sidebar or environment variables)
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USERNAME = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "20665130")

st.set_page_config(page_title="Excel Fare Upload + Neo4j", page_icon="💰", layout="wide")
st.title("Excel Fare Upload and Neo4j connection")
st.caption("Upload Excel files and connect to Neo4j Desktop or Aura. Use the sidebar to enter the database URI and credentials.")


def normalize_uri(uri: str) -> str:
    uri = str(uri or "").strip()
    if not uri:
        return uri
    if "://" not in uri:
        return f"bolt://{uri}"
    return uri


def get_driver(uri: str, username: str, password: str):
    normalized_uri = normalize_uri(uri)
    return GraphDatabase.driver(normalized_uri, auth=(username, password))


def _single_value(result, key: str, default: Any = 0) -> Any:
    record = result.single()
    return record.get(key, default) if record is not None else default


def test_connection(driver) -> str:
    with driver.session() as session:
        result = session.run("RETURN 'Connected to Neo4j' AS message")
        return _single_value(result, "message", "Connected to Neo4j")


def load_neo4j_summary(driver) -> dict[str, int]:
    """Load Fare relationship and Place node counts."""
    with driver.session() as session:
        fare_rows = session.run("MATCH ()-[f:Fare]->() RETURN count(f) AS fare_count")
        fare_count = _single_value(fare_rows, "fare_count", 0)

        place_rows = session.run("MATCH (p:Place) RETURN count(p) AS place_count")
        place_count = _single_value(place_rows, "place_count", 0)

        return {
            "fare_count": fare_count,
            "place_count": place_count,
        }


if "neo4j_driver" not in st.session_state:
    st.session_state.neo4j_driver = None
if "neo4j_status" not in st.session_state:
    st.session_state.neo4j_status = None
if "neo4j_summary" not in st.session_state:
    st.session_state.neo4j_summary = {"fare_count": 0, "place_count": 0}

# Sidebar: Neo4j connection
with st.sidebar:
    st.header("Neo4j Connection")
    st.caption("Enter credentials for local Neo4j Desktop or Neo4j Aura.")
    
    uri = st.text_input(
        "Connection URI",
        value=URI,
        placeholder="bolt://localhost:7687 or neo4j+s://<your-aura-host>",
        help="Use bolt://localhost:7687 for Neo4j Desktop, bolt+ssc://localhost:7687 for self-signed certs, or neo4j+s://... for Aura."
    )
    user = st.text_input("Username", value=USERNAME, placeholder="neo4j")
    password = st.text_input("Password", value=PASSWORD, type="password", placeholder="your_secure_password")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Connect / Test", type="primary"):
            try:
                if st.session_state.neo4j_driver is not None:
                    st.session_state.neo4j_driver.close()
                drv = get_driver(uri, user, password)
                msg = test_connection(drv)
                st.session_state.neo4j_driver = drv
                st.session_state.neo4j_status = msg
                st.session_state.neo4j_summary = load_neo4j_summary(drv)
                st.success(msg)
            except Exception as e:
                st.session_state.neo4j_driver = None
                st.session_state.neo4j_status = None
                message = str(e)
                if "self signed" in message.lower() or "ssl" in message.lower():
                    message += " Use bolt+ssc://localhost:7687 or neo4j+ssc://localhost:7687 for self-signed certificates."
                st.error(f"Connection failed: {message}")
    with c2:
        if st.button("Disconnect"):
            if st.session_state.neo4j_driver is not None:
                st.session_state.neo4j_driver.close()
                st.session_state.neo4j_driver = None
            st.session_state.neo4j_status = None
            st.session_state.neo4j_summary = {"fare_count": 0, "place_count": 0}
            st.info("Disconnected.")

    if st.session_state.neo4j_status:
        st.success(st.session_state.neo4j_status)
        summary = st.session_state.get("neo4j_summary", {})
        st.metric("Fare Relationships", summary.get("fare_count", 0))
        st.metric("Place Nodes", summary.get("place_count", 0))


# Main content: Upload section
st.subheader("Upload Data File")
st.caption("Supported formats: .xlsx, .xls, .csv")

uploaded = st.file_uploader("Choose a data file", type=["xlsx", "xls", "csv"])

df: Any = None
sheet_names: list[str] = []

if uploaded is not None:
    try:
        filename = uploaded.name.lower()
        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded)
            st.success(f"Loaded **{uploaded.name}** ({len(df)} rows from CSV).")
            with st.expander("Preview data", expanded=True):
                st.dataframe(df, use_container_width=True)
        else:
            xls = pd.ExcelFile(uploaded)
            sheet_names = xls.sheet_names

            if len(sheet_names) == 0:
                st.error("No sheets found in the Excel file.")
            else:
                selected_sheet = st.selectbox(
                    "Select sheet",
                    options=sheet_names,
                    index=0,
                    help="Choose which sheet contains your fare data."
                )

                df = pd.read_excel(uploaded, sheet_name=selected_sheet)
                st.success(f"Loaded **{uploaded.name}** ({len(df)} rows from '{selected_sheet}' sheet).")
                with st.expander("Preview data", expanded=True):
                    st.dataframe(df.head(10), use_container_width=True)

    except Exception as e:
        st.error(f"Failed to read data file: {e}")


if df is not None and len(df) > 0:
    # Interchange columns with .1 suffix
    original_columns = list(df.columns)
    column_mapping = {}
    
    # First pass: identify pairs to swap
    for col in original_columns:
        if col.endswith('.1'):
            base_name = col[:-2]  # Remove .1
            if base_name in original_columns:
                # Swap: .1 becomes base, base becomes .1
                column_mapping[col] = base_name
                column_mapping[base_name] = col
    
    # Apply column renaming
    df = df.rename(columns=column_mapping)
    
    if column_mapping:
        swapped_cols = [f"{old} → {new}" for old, new in column_mapping.items() if old.endswith('.1')]
        st.info(f"Column names swapped: {', '.join(swapped_cols)}")
    
    st.subheader("Define Triplet Extraction")
    st.caption("Map column names to origin and destination/fare fields.")
    
    columns = list(df.columns)
    
    origin_col = st.selectbox(
        "Origin column",
        options=columns,
        index=1 if len(columns) > 1 else 0,
        key="origin_col",
        help="Column containing origin/from location",
    )

    dest_start_col = st.selectbox(
        "First destination column",
        options=[c for c in columns if columns.index(c) > columns.index(origin_col)],
        index=0,
        key="dest_start_col",
        help="Choose the first column that represents destination fares. All columns from here onward become destinations.",
    )
    destination_columns = columns[columns.index(dest_start_col) :]

    if st.button("Extract Triplets"):
        st.session_state.extracted_triplets = []

        def _format_fare(value: Any) -> str:
            if pd.isna(value):
                return ""
            result = str(value).strip()
            return "" if result.lower() == "nan" else result

        def _clean_location_name(name: str) -> str:
            """Remove .1 suffix from location names."""
            return name.replace('.1', '') if name.endswith('.1') else name

        for _, row in df.iterrows():
            origin = str(row.get(origin_col, "")).strip()
            if not origin:
                continue
            for dest_col in destination_columns:
                fare = _format_fare(row.get(dest_col))
                destination = str(dest_col).strip()
                if origin and destination and fare:
                    st.session_state.extracted_triplets.append({
                        "origin": _clean_location_name(origin),
                        "destination": _clean_location_name(destination),
                        "fare": fare,
                    })

        st.session_state.extracted_json = [
            triplet for triplet in st.session_state.extracted_triplets
        ]

        # Ensure all triplets are cleaned
        for triplet in st.session_state.extracted_triplets:
            triplet["origin"] = _clean_location_name(triplet["origin"])
            triplet["destination"] = _clean_location_name(triplet["destination"])
        st.session_state.extracted_json = [
            triplet for triplet in st.session_state.extracted_triplets
        ]

        st.success(f"Extracted {len(st.session_state.extracted_triplets)} valid triplets.")

        if st.session_state.extracted_json:
            with st.expander("Transformed JSON", expanded=True):
                st.json(st.session_state.extracted_json)
                st.download_button(
                    "Download transformed JSON",
                    data=json.dumps(st.session_state.extracted_json, indent=2, ensure_ascii=False),
                    file_name="fare_matrix_transformed.json",
                    mime="application/json",
                )
    
    # Display and edit extracted triplets
    if "extracted_triplets" in st.session_state and st.session_state.extracted_triplets:
        st.subheader("Transformed Fare JSON")
        st.caption("The matrix has been converted into origin/destination/fare triplets.")

        # Static properties
        st.markdown("---")
        st.subheader("Static Fare Properties")
        st.caption("Add key/value pairs that will be set on every Fare node.")
        
        if "static_fare_props" not in st.session_state:
            st.session_state.static_fare_props = [
                {"key": "Source", "value": uploaded.name if uploaded else ""},
            ]
        
        static_to_remove: list[int] = []
        static_props_rows: list[dict[str, str]] = []
        
        for sidx, sprop in enumerate(list(st.session_state.static_fare_props)):
            c1, c2, c3 = st.columns([3, 3, 1])
            
            with c1:
                key = st.text_input(
                    f"Key {sidx + 1}",
                    value=sprop.get("key", ""),
                    key=f"static_key_{sidx}",
                    placeholder="e.g., route_name, updated_date"
                )
            
            with c2:
                value = st.text_input(
                    f"Value {sidx + 1}",
                    value=sprop.get("value", ""),
                    key=f"static_val_{sidx}",
                    placeholder="e.g., Colombo - Galle"
                )
            
            with c3:
                if st.button("✕", key=f"static_del_{sidx}"):
                    static_to_remove.append(sidx)
            
            static_props_rows.append({"key": key.strip(), "value": value.strip()})
        
        if static_to_remove:
            static_props_rows = [r for i, r in enumerate(static_props_rows) if i not in set(static_to_remove)]
        
        if st.button("Add Static Property"):
            static_props_rows.append({"key": "", "value": ""})
        
        st.session_state.static_fare_props = static_props_rows
        
        # Build static props dict
        static_props: dict[str, Any] = {}
        for sp in static_props_rows:
            k = str(sp.get("key") or "").strip()
            if k:
                static_props[k] = sp.get("value")
        
        if static_props:
            st.caption(f"✓ Will apply {len(static_props)} static properties to every Fare node.")
        
        # Preview
        st.markdown("---")
        st.subheader("Preview Fare Relationships")
        
        valid_triplets = [
            t for t in st.session_state.extracted_triplets
            if t.get("origin") and t.get("destination") and t.get("fare")
        ]
        
        if valid_triplets:
            preview_data = []
            json_payload = []
            for t in valid_triplets:
                row_data = {
                    "origin": t["origin"],
                    "destination": t["destination"],
                    "fare": t["fare"],
                }
                row_data.update(static_props)
                json_payload.append(row_data)
                if len(preview_data) < 10:
                    preview_data.append(row_data)
            
            st.dataframe(preview_data, use_container_width=True)
            
            if len(valid_triplets) > 10:
                st.info(f"Showing 10 of {len(valid_triplets)} fare relationships.")

            with st.expander("JSON output", expanded=False):
                st.json(json_payload)
                st.download_button(
                    "Download JSON",
                    data=json.dumps(json_payload, indent=2, ensure_ascii=False),
                    file_name="fare_relationships.json",
                    mime="application/json",
                )
        else:
            st.warning("No valid triplets to preview. Ensure origin, destination, and fare are filled.")
        
        # Ingest button
        st.markdown("---")
        if st.session_state.neo4j_driver is None:
            st.warning("⚠️ Connect to Neo4j Aura in the sidebar to ingest data.")
        else:
            if st.button("Ingest Fare Relationships into Neo4j Aura", type="primary"):
                if not valid_triplets:
                    st.warning("Nothing to ingest: no valid triplets.")
                else:
                    try:
                        # Build Cypher query to create Fare relationships between Place nodes
                        cypher = """
UNWIND $rows AS row
MERGE (origin_place:Place {name: row.origin})
MERGE (dest_place:Place {name: row.destination})
CREATE (origin_place)-[fare:Fare {
    fare: row.fare,
    id: row.origin + '_' + row.destination + '_' + row.fare,
    createdAt: datetime()
}]->(dest_place)
SET fare += row.static_props
RETURN count(fare) AS created_count
                        """
                        
                        rows_payload = [
                            {
                                "origin": t["origin"],
                                "destination": t["destination"],
                                "fare": t["fare"],
                                "static_props": static_props,
                            }
                            for t in valid_triplets
                        ]
                        
                        with st.session_state.neo4j_driver.session() as session:
                            result = session.run(cypher, rows=rows_payload)
                            summary = result.single()
                            created = summary.get("created_count", 0) if summary else 0
                        
                        st.success(f"✓ Successfully ingested {created} Fare relationships into Neo4j Aura!")
                        
                        # Refresh summary
                        if st.session_state.neo4j_driver is not None:
                            st.session_state.neo4j_summary = load_neo4j_summary(st.session_state.neo4j_driver)
                            st.rerun()
                    
                    except Exception as e:
                        st.error(f"Ingestion failed: {e}")


# Optional: Ad-hoc Cypher query section
st.markdown("---")
st.subheader("Optional: Run Ad-hoc Cypher Query")

if st.session_state.neo4j_driver is None:
    st.info("Connect to Neo4j Aura in the sidebar to run queries.")
else:
    default_query = "MATCH ()-[f:Fare]->() RETURN count(f) AS fare_count, count(DISTINCT f.fare) AS unique_fares LIMIT 1"
    cypher_query = st.text_area(
        "Cypher query (read-only recommended)",
        value=default_query,
        height=100,
        help="For testing only; keep to read operations."
    )
    
    if st.button("Run Query"):
        try:
            with st.session_state.neo4j_driver.session() as session:
                result = session.run(cypher_query)
                rows = [r.data() for r in result]
            
            if rows:
                st.dataframe(rows, use_container_width=True)
            else:
                st.info("Query returned no results.")
        
        except Exception as e:
            st.error(f"Query failed: {e}")
