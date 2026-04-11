#!/usr/bin/env python3
"""
Sample Streamlit UI: upload a JSON file, preview it, and connect to a local Neo4j instance.

Run from repo root:
    streamlit run Done-verified/json_upload_neo4j_sample_ui.py

For production, move secrets to environment variables instead of hardcoding.
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from neo4j import GraphDatabase

# Connection defaults (override via sidebar or NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USERNAME = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "20665130")

st.set_page_config(page_title="JSON upload + Neo4j", page_icon="📄", layout="wide")
st.title("JSON upload and Neo4j connection sample")
st.caption("Upload any `.json` file for preview; use the sidebar to test the database driver.")


def get_driver(uri: str, username: str, password: str):
    return GraphDatabase.driver(uri, auth=(username, password))


def test_connection(driver) -> str:
    with driver.session() as session:
        result = session.run("RETURN 'Connected to Neo4j' AS message")
        return result.single()["message"]


def load_neo4j_summary(driver) -> dict[str, list[str]]:
    """Load unique node names, relationship types, and property keys."""
    with driver.session() as session:
        node_rows = session.run(
            "MATCH (n) WHERE n.name IS NOT NULL RETURN DISTINCT n.name AS name ORDER BY name LIMIT 1000"
        )
        rel_rows = session.run(
            "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type ORDER BY rel_type LIMIT 200"
        )
        key_rows = session.run(
            "MATCH ()-[r]->() UNWIND keys(r) AS k RETURN DISTINCT k AS key ORDER BY key"
        )
        return {
            "nodes": [r.get("name") for r in node_rows if r.get("name") is not None],
            "relationships": [r.get("rel_type") for r in rel_rows if r.get("rel_type") is not None],
            "property_keys": [r.get("key") for r in key_rows if r.get("key") is not None],
        }


if "neo4j_driver" not in st.session_state:
    st.session_state.neo4j_driver = None
if "neo4j_status" not in st.session_state:
    st.session_state.neo4j_status = None
if "neo4j_summary" not in st.session_state:
    st.session_state.neo4j_summary = {"nodes": [], "relationships": [], "property_keys": []}

with st.sidebar:
    st.header("Neo4j connection")
    uri = st.text_input("URI", value=URI)
    user = st.text_input("Username", value=USERNAME)
    password = st.text_input("Password", value=PASSWORD, type="password")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Connect / test", type="primary"):
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
                st.session_state.neo4j_summary = {"nodes": [], "relationships": [], "property_keys": []}
                st.error(f"Connection failed: {e}")
    with c2:
        if st.button("Disconnect"):
            if st.session_state.neo4j_driver is not None:
                st.session_state.neo4j_driver.close()
                st.session_state.neo4j_driver = None
            st.session_state.neo4j_status = None
            st.session_state.neo4j_summary = {"nodes": [], "relationships": [], "property_keys": []}
            st.info("Disconnected.")

    if st.session_state.neo4j_status:
        st.info(st.session_state.neo4j_status)


st.subheader("Upload JSON")
uploaded = st.file_uploader("Choose a JSON file", type=["json"])

data: Any | None = None
if uploaded is not None:
    try:
        raw = uploaded.getvalue().decode("utf-8")
        data = json.loads(raw)
        st.success(f"Loaded **{uploaded.name}** ({len(raw):,} bytes).")
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
    except UnicodeDecodeError as e:
        st.error(f"Could not decode as UTF-8: {e}")


def _find_tables(payload: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of table blocks with headers/rows."""
    if not isinstance(payload, dict):
        return []
    # Specific SmartMove extraction shape
    extracted = payload.get("extracted_data") or payload.get("data") or {}
    tables = extracted.get("tables")
    if isinstance(tables, list):
        out: list[dict[str, Any]] = []
        for t in tables:
            if not isinstance(t, dict):
                continue
            headers = t.get("headers")
            rows = t.get("rows")
            if isinstance(headers, list) and isinstance(rows, list):
                out.append({"headers": headers, "rows": rows, "meta": {k: v for k, v in t.items() if k not in {"headers", "rows"}}})
        if out:
            return out
    # Fallback: single table-style dict
    headers = payload.get("headers")
    rows = payload.get("rows")
    if isinstance(headers, list) and isinstance(rows, list):
        return [{"headers": headers, "rows": rows, "meta": {}}]
    return []


if "mapping_prefs" not in st.session_state:
    # Simple header -> role memory shared across uploads
    st.session_state.mapping_prefs: dict[str, dict[str, Any]] = {}

tables: list[dict[str, Any]] = _find_tables(data) if data is not None else []

if data is not None:
    c_raw, c_map = st.columns([1, 2])
    with c_raw:
        with st.expander("Raw structure", expanded=True):
            st.json(data, expanded=False)
        if st.session_state.get("neo4j_driver") is not None:
            if st.button("Refresh Neo4j summary"):
                try:
                    st.session_state.neo4j_summary = load_neo4j_summary(st.session_state.neo4j_driver)
                except Exception as e:
                    st.warning(f"Could not refresh Neo4j summary: {e}")
            summary = st.session_state.get("neo4j_summary", {})
            with st.expander("Nodes", expanded=False):
                st.write(summary.get("nodes", []))
            with st.expander("Relationships", expanded=False):
                st.write(summary.get("relationships", []))
            with st.expander("Property keys", expanded=False):
                st.write(summary.get("property_keys", []))

    with c_map:
        st.subheader("Map columns → nodes and relationship")
        if not tables:
            st.info("No table with `headers` and `rows` found in this JSON.")
        else:
            table_idx = 0
            if len(tables) > 1:
                table_idx = st.number_input("Table index", min_value=0, max_value=len(tables) - 1, value=0, step=1)
            table = tables[int(table_idx)]
            headers = [str(h) for h in (table.get("headers") or [])]
            rows = table.get("rows") or []

            if not headers:
                st.warning("No headers found for selected table.")
            else:
                st.write("Detected headers:", ", ".join(headers))

                # --- Node roles configuration (user defines how many nodes) ---
                st.markdown("**Node roles**")
                if "node_roles" not in st.session_state:
                    st.session_state.node_roles = ["from", "to"]

                def _load_place_names() -> list[str]:
                    """Fetch existing Neo4j Place node names for dropdown suggestions."""
                    drv = st.session_state.get("neo4j_driver")
                    if drv is None:
                        return []
                    try:
                        with drv.session() as session:
                            # DISTINCT list of existing nodes for suggestions
                            result = session.run(
                                "MATCH (p:Place) RETURN DISTINCT p.name AS name ORDER BY name LIMIT 500"
                            )
                            return [r.get("name") for r in result if r.get("name") is not None]
                    except Exception:
                        return []

                num_nodes = st.number_input(
                    "How many nodes do you want to define?",
                    min_value=2,
                    max_value=6,
                    value=len(st.session_state.node_roles),
                    step=1,
                    help="Define logical node roles (e.g. from, via, to).",
                )

                # Ensure list length matches chosen count
                roles = list(st.session_state.node_roles)
                if len(roles) < num_nodes:
                    roles.extend([f"node_{i+1}" for i in range(len(roles), int(num_nodes))])
                elif len(roles) > num_nodes:
                    roles = roles[: int(num_nodes)]

                cols = st.columns(int(num_nodes))
                new_roles: list[str] = []
                # Cache place names to avoid querying on every rerun
                if "place_name_suggestions" not in st.session_state:
                    st.session_state.place_name_suggestions = []
                if "place_name_loaded_once" not in st.session_state:
                    st.session_state.place_name_loaded_once = False

                if st.session_state.get("neo4j_driver") is not None and not st.session_state.place_name_loaded_once:
                    st.session_state.place_name_suggestions = _load_place_names()
                    st.session_state.place_name_loaded_once = True

                if st.session_state.get("neo4j_driver") is not None:
                    if st.button("Refresh Place name suggestions"):
                        st.session_state.place_name_suggestions = _load_place_names()

                # Build suggestions from current JSON headers + prior typed nodes
                if "node_name_history" not in st.session_state:
                    st.session_state.node_name_history = []

                header_name_suggestions: list[str] = [h for h in headers if isinstance(h, str) and h.strip()]

                type_new_sentinel = "<type new node name>"
                history_suggestions: list[str] = st.session_state.get("node_name_history", []) or []

                # Deduplicated ordered options:
                # previous typed nodes -> headers -> type new
                place_options: list[str] = []
                for group in (history_suggestions, header_name_suggestions):
                    for item in group:
                        if str(item).strip().lower() in {"from", "to"}:
                            continue
                        if item not in place_options:
                            place_options.append(item)
                place_options.append(type_new_sentinel)

                for i in range(int(num_nodes)):
                    with cols[i]:
                        current_val = roles[i]
                        default_choice = current_val if current_val in place_options else type_new_sentinel

                        picked = st.selectbox(
                            f"Node {i+1}",
                            options=place_options,
                            index=place_options.index(default_choice) if default_choice in place_options else 0,
                            key=f"node_choice_{i}",
                        )
                        if picked == type_new_sentinel:
                            lbl = st.text_input(
                                "Node name",
                                value=current_val,
                                key=f"node_role_{i}",
                            )
                            new_roles.append(lbl.strip() or f"node_{i+1}")
                        else:
                            new_roles.append(picked)

                st.session_state.node_roles = new_roles
                # Keep node-name history for future uploads in same session
                for n in new_roles:
                    if n and n not in st.session_state.node_name_history:
                        st.session_state.node_name_history.append(n)

                prefs = st.session_state.mapping_prefs

                # Nodes are created from the user-typed node labels (static per upload).
                node_labels: list[str] = list(st.session_state.node_roles)
                st.caption("Nodes will be created using these typed names (static per upload).")

                # --- Two-column mapping UI for relationship properties ---
                # Include ALL headers (including node value columns) so the user can
                # also store node values as relationship properties if desired.
                prop_candidates = headers

                mapping_key = "rel_mapping_rows"
                # Filter/refresh mapping rows if node column choices changed
                existing_rows = list(st.session_state.get(mapping_key, []) or [])
                existing_rows = [r for r in existing_rows if r.get("source") in prop_candidates]
                # If nothing left, initialize defaults
                if not existing_rows:
                    rows_init: list[dict[str, Any]] = []
                    for h in prop_candidates:
                        remembered = prefs.get(h, {}).get("prop_name")
                        prop_name = remembered or h.strip().lower().replace(" ", "_")
                        rows_init.append({"source": h, "prop": prop_name})
                    existing_rows = rows_init
                st.session_state[mapping_key] = existing_rows

                # --- Relationship properties mapping rows ---
                st.markdown("**Relationship properties mapping**")
                st.caption("Left: JSON column (header). Right: property key on the relationship. You can add/remove rows.")

                # Initialize dynamic rows in session state
                new_rows = []
                to_remove: list[int] = []
                for idx, row in enumerate(list(st.session_state[mapping_key])):
                    c1, c2, c3 = st.columns([3, 3, 1])
                    with c1:
                        src = st.selectbox(
                            f"Column {idx + 1}",
                            prop_candidates,
                            index=prop_candidates.index(row.get("source", prop_candidates[0]))
                            if row.get("source") in prop_candidates
                            else 0,
                            key=f"map_src_{idx}",
                        )
                    with c2:
                        prop_name = st.text_input(
                            f"Property key {idx + 1}",
                            value=row.get("prop") or src.strip().lower().replace(" ", "_"),
                            key=f"map_prop_{idx}",
                        )
                    with c3:
                        if st.button("✕", key=f"map_del_{idx}"):
                            to_remove.append(idx)
                    new_rows.append({"source": src, "prop": prop_name})

                # Apply removals
                if to_remove:
                    new_rows = [r for i, r in enumerate(new_rows) if i not in set(to_remove)]

                if st.button("Add mapping row"):
                    # Add one more, defaulting to first candidate
                    base = prop_candidates[0] if prop_candidates else ""
                    new_rows.append({"source": base, "prop": base.strip().lower().replace(" ", "_")})

                # Persist updated rows and memory
                st.session_state[mapping_key] = new_rows
                for r in new_rows:
                    h = r["source"]
                    if h:
                        prefs[h] = {"role": "prop", "prop_name": r["prop"]}

                st.caption("Your mapping preferences are remembered by header name for future uploads.")

                st.markdown("**Static relationship properties (applied to every edge)**")
                st.caption("Add key/value pairs that will be SET on every created `:ROUTE` relationship.")

                static_key = "static_rel_props_rows"
                if static_key not in st.session_state:
                    st.session_state[static_key] = []

                st.session_state[static_key] = list(st.session_state.get(static_key, []) or [])
                # Default static row: Source -> pdf name
                if isinstance(data, dict):
                    pdf_path = data.get("pdf_path")
                    if isinstance(pdf_path, str) and pdf_path.strip():
                        pdf_name = pdf_path.split("\\")[-1]
                    elif uploaded is not None:
                        pdf_name = uploaded.name
                    else:
                        pdf_name = "unknown.pdf"
                else:
                    pdf_name = uploaded.name if uploaded is not None else "unknown.pdf"

                has_source_row = any(
                    str(r.get("key", "")).strip().lower() == "source"
                    for r in st.session_state[static_key]
                )
                if not has_source_row:
                    st.session_state[static_key].insert(0, {"key": "Source", "value": pdf_name})

                static_to_remove: list[int] = []
                static_rows: list[dict[str, str]] = []
                for sidx, srow in enumerate(list(st.session_state[static_key])):
                    c1, c2, c3 = st.columns([3, 3, 1])
                    with c1:
                        s_k = st.text_input(
                            f"Key {sidx + 1}",
                            value=srow.get("key", ""),
                            key=f"static_key_{sidx}",
                        )
                    with c2:
                        s_v = st.text_input(
                            f"Value {sidx + 1}",
                            value=srow.get("value", ""),
                            key=f"static_val_{sidx}",
                        )
                    with c3:
                        if st.button("✕", key=f"static_del_{sidx}"):
                            static_to_remove.append(sidx)
                    static_rows.append({"key": s_k, "value": s_v})

                if static_to_remove:
                    static_rows = [r for i, r in enumerate(static_rows) if i not in set(static_to_remove)]

                if st.button("Add static property"):
                    static_rows.append({"key": "", "value": ""})

                st.session_state[static_key] = static_rows

                static_props: dict[str, Any] = {}
                for s in static_rows:
                    k = str(s.get("key") or "").strip()
                    if not k:
                        continue
                    # Keep values as strings for simplicity; can extend to numbers later
                    static_props[k] = s.get("value")

                if static_props:
                    st.caption(f"Will apply {len(static_props)} static properties to every relationship.")

                # Relationship creation strategy:
                # - MERGE collapses multiple rows into a single edge per endpoints pair.
                # - CREATE creates a new edge per row, preserving all data.
                st.markdown("**Edge creation strategy**")
                if "edge_mode" not in st.session_state:
                    st.session_state.edge_mode = "create"
                edge_mode = st.selectbox(
                    "How to write relationships into Neo4j",
                    options=["merge_endpoints_only", "create_per_row"],
                    index=0 if st.session_state.edge_mode == "merge_endpoints_only" else 1,
                    format_func=lambda x: (
                        "Merge (one edge per endpoints)" if x == "merge_endpoints_only" else "Create (one edge per row)"
                    ),
                )
                st.session_state.edge_mode = edge_mode

                def _build_unwind_payload() -> list[dict[str, Any]]:
                    out_rows: list[dict[str, Any]] = []
                    for r in rows:
                        row_map = dict(zip(headers, r))
                        # Use typed node labels as node identifiers.
                        nodes = [str(node_labels[i]) for i in range(int(num_nodes))]
                        rel_props: dict[str, Any] = {}
                        for m in st.session_state.get(mapping_key, []):
                            src = m.get("source")
                            key = m.get("prop")
                            if not src or not key:
                                continue
                            rel_props[key] = row_map.get(src)
                        out_rows.append(
                            {
                                "nodes": nodes,
                                "props": rel_props,
                            }
                        )
                    return out_rows

                # Build a chain of relationships across consecutive nodes:
                # n0 -[:Schedule]-> n1 -[:Schedule]-> n2 ...
                cypher_lines: list[str] = ["UNWIND $rows AS row"]
                for i in range(int(num_nodes)):
                    cypher_lines.append(f"MERGE (n{i}:Place {{name: row.nodes[{i}]}})")
                for i in range(int(num_nodes) - 1):
                    if edge_mode == "create_per_row":
                        cypher_lines.append(f"CREATE (n{i})-[r{i}:Schedule]->(n{i+1})")
                    else:
                        cypher_lines.append(f"MERGE (n{i})-[r{i}:Schedule]->(n{i+1})")
                    cypher_lines.append(f"SET r{i} += row.props")
                    if static_props:
                        cypher_lines.append(f"SET r{i} += $static_props")
                cypher_template = "\n".join(cypher_lines)

                rows_payload = _build_unwind_payload()

                # Preview extracted graph as edge → props mapping
                st.subheader("Extracted graph preview")
                with st.expander("Edges and properties (first few rows)", expanded=True):
                    if rows_payload:
                        edge_preview: dict[str, Any] = {}
                        for entry in rows_payload[:10]:
                            nodes_label = " -> ".join(entry.get("nodes", []))
                            if not nodes_label:
                                continue
                            edge_preview[nodes_label] = entry.get("props", {})
                        if edge_preview:
                            st.json(edge_preview, expanded=False)
                        else:
                            st.info("No edges could be built from current mapping.")
                        if static_props:
                            st.write("Static properties (applied to every relationship):")
                            st.json(static_props, expanded=False)
                    else:
                        st.info("No valid rows (missing node values).")

                st.subheader("Generated Cypher (preview)")
                with st.expander("Cypher text", expanded=False):
                    st.code(cypher_template, language="cypher")

                if st.session_state.neo4j_driver is None:
                    st.warning("Connect to Neo4j in the sidebar to run ingestion.")
                else:
                    if st.button("Ingest into Neo4j", type="primary"):
                        if not rows_payload:
                            st.warning("Nothing to ingest: no valid node rows.")
                        else:
                            try:
                                with st.session_state.neo4j_driver.session() as session:
                                    session.run(cypher_template, rows=rows_payload, static_props=static_props)
                                st.success(f"Ingested {len(rows_payload)} rows into Neo4j.")
                            except Exception as e:
                                st.error(f"Ingestion failed: {e}")

st.subheader("Optional: run an ad-hoc read-only Cypher")
if st.session_state.neo4j_driver is None:
    st.warning("Connect to Neo4j in the sidebar first.")
else:
    default_q = "MATCH (n) RETURN count(n) AS n LIMIT 1"
    cypher = st.text_input("Cypher (keep to reads for this sample)", value=default_q)
    if st.button("Run query"):
        try:
            with st.session_state.neo4j_driver.session() as session:
                result = session.run(cypher)
                rows = [r.data() for r in result]
            st.dataframe(rows, use_container_width=True)
        except Exception as e:
            st.error(str(e))
