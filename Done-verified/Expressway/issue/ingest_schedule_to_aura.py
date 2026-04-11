#!/usr/bin/env python3
"""
Ingest schedule data from JSON file into Neo4j Aura
Handles nested time objects and mixed data formats
"""

import json
import os
import argparse
from neo4j import GraphDatabase, basic_auth
from typing import Dict, List, Optional, Any, Tuple
import re

# Neo4j Aura connection details
URI = "neo4j+ssc://10e45f8e.databases.neo4j.io"
USER = "neo4j"
PASSWORD = "yJKJlZc3YNu5_ZErIyucEV3ICFfdXaTqdF6naQA5YoQ"
DATABASE = "neo4j"

# Default JSON file
JSON_FILE = "Galle - Negombo, Kandy_extracted_tables_english.json"


def parse_time(time_value: Any) -> Optional[str]:
    """
    Parse time value to HH:MM format
    Handles strings, objects, and None values
    """
    if time_value is None:
        return None
    
    # If it's a dictionary/object with time fields
    if isinstance(time_value, dict):
        # Try to extract departure or arrival time
        if "departure_from_terminal" in time_value:
            time_str = time_value["departure_from_terminal"]
        elif "arrival_to_terminal" in time_value:
            time_str = time_value["arrival_to_terminal"]
        elif "departure" in time_value:
            time_str = time_value["departure"]
        elif "arrival" in time_value:
            time_str = time_value["arrival"]
        else:
            return None
    else:
        time_str = str(time_value).strip()
    
    if not time_str or time_str.lower() in ['', 'nan', 'none', 'null']:
        return None
    
    # Replace dots with colons
    time_str = time_str.replace('.', ':')
    
    # Match HH:MM or H:MM format
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        
        # Validate hours and minutes
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return None
        
        # Format as HH:MM
        return f"{hours:02d}:{minutes:02d}"
    
    return None


def extract_times_from_cell(cell_value: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract departure and arrival times from a cell
    Returns: (departure_time, arrival_time)
    """
    if isinstance(cell_value, dict):
        # Handle nested time objects
        departure = parse_time(cell_value.get("departure_from_terminal") or cell_value.get("departure"))
        arrival = parse_time(cell_value.get("arrival_to_terminal") or cell_value.get("arrival"))
        return departure, arrival
    else:
        # Single time value - treat as both departure and arrival (or just one)
        time = parse_time(cell_value)
        return time, time


def process_table(table: Dict, route_type: str = "Expressway", optional_properties: Dict = None) -> List[Dict]:
    """
    Process a table and extract schedule data
    Returns list of route dictionaries with schedules
    Preserves arrival_to_terminal and departure_from_terminal properties
    """
    if optional_properties is None:
        optional_properties = {}
    
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    
    # Filter out non-location headers
    location_keywords = ['trip', 'number', 'bus', 'running', 'no', 'pair', 'route']
    locations = []
    location_indices = []
    
    for idx, header in enumerate(headers):
        header_lower = str(header).lower().strip()
        if not any(keyword in header_lower for keyword in location_keywords):
            locations.append(str(header).strip())
            location_indices.append(idx)
    
    if len(locations) < 2:
        return []
    
    routes = []
    
    # Process each pair of consecutive locations
    for i in range(len(locations) - 1):
        from_loc = locations[i]
        to_loc = locations[i + 1]
        from_idx = location_indices[i]
        to_idx = location_indices[i + 1]
        
        schedules = []
        
        # Process each row
        for row in rows:
            if not isinstance(row, list) or len(row) <= max(from_idx, to_idx):
                continue
            
            from_cell = row[from_idx] if from_idx < len(row) else None
            to_cell = row[to_idx] if to_idx < len(row) else None
            
            # Check if there are more locations after the destination (intermediate stops)
            has_intermediate = len(locations) > 2
            
            # Extract departure from first element
            departure = None
            departure_from_terminal = None
            
            if isinstance(from_cell, dict):
                # If first cell is an object, extract departure_from_terminal
                departure_from_terminal = parse_time(from_cell.get("departure_from_terminal"))
                departure = departure_from_terminal
            else:
                # If first cell is a string, use it as departure
                departure = parse_time(from_cell)
                departure_from_terminal = departure
            
            # Extract arrival
            arrival = None
            arrival_to_terminal = None
            
            if has_intermediate and i == 0:
                # For first route in multi-stop table, use last element as arrival
                # and extract terminal times from intermediate cell (to_cell)
                last_idx = location_indices[-1]
                last_cell = row[last_idx] if last_idx < len(row) else None
                arrival = parse_time(last_cell)
                
                # Extract terminal times from intermediate cell (to_cell)
                if isinstance(to_cell, dict):
                    departure_from_terminal = parse_time(to_cell.get("departure_from_terminal")) or departure_from_terminal
                    arrival_to_terminal = parse_time(to_cell.get("arrival_to_terminal"))
                else:
                    # If intermediate cell is string, use arrival as arrival_to_terminal
                    arrival_to_terminal = arrival
            else:
                # For direct routes (2 locations) or subsequent routes, use to_cell as arrival
                if isinstance(to_cell, dict):
                    arrival_to_terminal = parse_time(to_cell.get("arrival_to_terminal"))
                    arrival = arrival_to_terminal
                else:
                    arrival = parse_time(to_cell)
                    arrival_to_terminal = arrival
            
            # Create schedule if we have both departure and arrival
            if departure and arrival:
                schedule_item = {
                    "departure": departure,
                    "arrival": arrival
                }
                
                # Add terminal-specific properties
                if departure_from_terminal:
                    schedule_item["departure_from_terminal"] = departure_from_terminal
                
                if arrival_to_terminal:
                    schedule_item["arrival_to_terminal"] = arrival_to_terminal
                
                # Add optional properties
                schedule_item.update(optional_properties)
                schedules.append(schedule_item)
        
        if schedules:
            routes.append({
                "from": from_loc,
                "to": to_loc,
                "schedules": schedules
            })
    
    return routes


def create_place_node(session, place_name: str) -> bool:
    """Create Place node if it doesn't exist (MERGE - safe)"""
    query = """
    MERGE (p:Place {name: $place_name})
    ON CREATE SET p.created_at = datetime()
    RETURN p
    """
    try:
        result = session.run(query, place_name=place_name)
        return result.single() is not None
    except Exception as e:
        print(f"    ⚠️  Error creating place '{place_name}': {e}")
        return False


def create_schedule_relationship(session, from_place: str, to_place: str,
                                 departure: str, arrival: str,
                                 optional_props: Dict) -> bool:
    """Create Schedule relationship with properties"""
    # Build properties dictionary (exclude None values from MERGE)
    props_for_merge = {}
    props_for_set = {}
    
    # Required properties
    props_for_set['departure'] = departure
    props_for_set['arrival'] = arrival
    
    # Add optional properties
    for key, value in optional_props.items():
        if value is not None:
            props_for_merge[key] = value
        props_for_set[key] = value
    
    # Build MERGE pattern with only non-null properties
    if props_for_merge:
        merge_props = [f"{key}: ${key}" for key in props_for_merge.keys()]
        merge_pattern = "{" + ", ".join(merge_props) + "}"
    else:
        merge_pattern = ""
    
    # Build SET clauses
    set_props = [f"s.{key} = ${key}" for key in props_for_set.keys()]
    set_clause = ", ".join(set_props)
    
    # Use CREATE to allow multiple schedules with same route but different times/terminal info
    # This preserves all terminal properties (arrival_to_terminal, departure_from_terminal)
    query = f"""
    MATCH (from:Place {{name: $from_place}})
    MATCH (to:Place {{name: $to_place}})
    CREATE (from)-[s:Schedule]->(to)
    SET {set_clause}, s.created_at = datetime()
    RETURN s
    """
    
    # Prepare parameters
    params = {
        'from_place': from_place,
        'to_place': to_place,
        **props_for_set
    }
    
    try:
        result = session.run(query, **params)
        return result.single() is not None
    except Exception as e:
        print(f"    ⚠️  Error creating schedule: {e}")
        return False


def ingest_schedule_data(driver, json_file_path: str, route_type: str = "Expressway", 
                         optional_properties: Dict = None) -> Dict[str, int]:
    """
    Ingest schedule data from JSON file into Neo4j Aura
    """
    if optional_properties is None:
        optional_properties = {}
    
    counts = {
        "places_created": 0,
        "schedules_created": 0,
        "routes_processed": 0
    }
    
    print(f"📂 Loading data from {json_file_path}...")
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error loading JSON file: {e}")
        return counts
    
    if not data.get("success") or "extracted_data" not in data:
        print("❌ Invalid JSON structure")
        return counts
    
    tables = data.get("extracted_data", {}).get("tables", [])
    print(f"📊 Found {len(tables)} table(s)")
    
    # Add route_type to optional properties
    if route_type:
        optional_properties['route_type'] = route_type
    
    all_routes = []
    
    # Process all tables
    for table in tables:
        routes = process_table(table, route_type, optional_properties)
        all_routes.extend(routes)
        counts["routes_processed"] += len(routes)
    
    print(f"📋 Extracted {len(all_routes)} route(s) with {sum(len(r['schedules']) for r in all_routes)} total schedules")
    
    # Collect unique places
    unique_places = set()
    for route in all_routes:
        unique_places.add(route["from"])
        unique_places.add(route["to"])
    
    print(f"📍 Found {len(unique_places)} unique places")
    
    # Ingest to Neo4j
    with driver.session(database=DATABASE) as session:
        # Create all places first
        print("🏗️  Creating Place nodes...")
        for place in unique_places:
            if create_place_node(session, place):
                counts["places_created"] += 1
        
        # Create schedule relationships
        print("🚌 Creating Schedule relationships...")
        for route in all_routes:
            from_place = route["from"]
            to_place = route["to"]
            
            for schedule in route["schedules"]:
                if create_schedule_relationship(
                    session,
                    from_place,
                    to_place,
                    schedule["departure"],
                    schedule["arrival"],
                    {k: v for k, v in schedule.items() if k not in ["departure", "arrival"]}
                ):
                    counts["schedules_created"] += 1
    
    return counts


def verify_ingestion(driver) -> None:
    """Verify the data was ingested correctly"""
    with driver.session(database=DATABASE) as session:
        # Count places
        place_query = "MATCH (p:Place) RETURN count(p) AS place_count"
        place_result = session.run(place_query)
        place_count = place_result.single()["place_count"]
        
        # Count schedules
        schedule_query = "MATCH ()-[s:Schedule]->() RETURN count(s) AS schedule_count"
        schedule_result = session.run(schedule_query)
        schedule_count = schedule_result.single()["schedule_count"]
        
        # Sample schedules
        sample_query = """
        MATCH (from:Place)-[s:Schedule]->(to:Place)
        RETURN from.name AS from_place, to.name AS to_place, 
               s.departure AS departure, s.arrival AS arrival,
               s.departure_from_terminal AS departure_from_terminal,
               s.arrival_to_terminal AS arrival_to_terminal,
               s.route_type AS route_type
        LIMIT 10
        """
        sample_result = session.run(sample_query)
        
        print("\n" + "="*60)
        print("📊 Ingestion Verification")
        print("="*60)
        print(f"✅ Places: {place_count}")
        print(f"✅ Schedules: {schedule_count}")
        print("\n📋 Sample Schedules:")
        for record in sample_result:
            route_info = f" [{record['route_type']}]" if record['route_type'] else ""
            terminal_info = ""
            if record.get('departure_from_terminal') or record.get('arrival_to_terminal'):
                dep_term = record.get('departure_from_terminal', 'N/A')
                arr_term = record.get('arrival_to_terminal', 'N/A')
                terminal_info = f" (Terminal: {dep_term} -> {arr_term})"
            print(f"   {record['from_place']} -> {record['to_place']}: {record['departure']} - {record['arrival']}{terminal_info}{route_info}")


def clear_last_ingestion(driver, source: str = None) -> Dict[str, int]:
    """
    Remove schedule data (optional - by source if provided)
    """
    counts = {
        "schedules_deleted": 0,
        "orphaned_places_deleted": 0
    }
    
    with driver.session(database=DATABASE) as session:
        if source:
            # Delete by source
            delete_query = """
            MATCH ()-[s:Schedule]->()
            WHERE s.source = $source
            DELETE s
            RETURN count(s) AS deleted
            """
            result = session.run(delete_query, source=source)
            counts["schedules_deleted"] = result.single()["deleted"]
        else:
            # Delete all Schedule relationships (use with caution)
            delete_query = """
            MATCH ()-[s:Schedule]->()
            DELETE s
            RETURN count(s) AS deleted
            """
            result = session.run(delete_query)
            counts["schedules_deleted"] = result.single()["deleted"]
        
        # Delete orphaned places
        delete_orphaned_query = """
        MATCH (p:Place)
        WHERE NOT (p)-[]-() AND NOT ()-[]->(p)
        DELETE p
        RETURN count(p) AS deleted
        """
        result = session.run(delete_orphaned_query)
        counts["orphaned_places_deleted"] = result.single()["deleted"]
    
    return counts


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Ingest schedule data from JSON into Neo4j Aura",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest schedule data (source will be auto-set to JSON filename)
  python ingest_schedule_to_aura.py
  
  # Use different JSON file
  python ingest_schedule_to_aura.py --json-file "path/to/file.json"
  
  # Add custom source identifier
  python ingest_schedule_to_aura.py --source "Galle-Negombo-Kandy-2024"
  
  # Add route type
  python ingest_schedule_to_aura.py --route-type "Expressway"
  
  # Add custom properties
  python ingest_schedule_to_aura.py --property "service_class:Premium" --property "days:Weekday"
  
  # Clear previous ingestion with specific source before ingesting
  python ingest_schedule_to_aura.py --clear-last "Galle-Negombo-Kandy-2024" --source "Galle-Negombo-Kandy-2024"
        """
    )
    
    parser.add_argument(
        '--json-file',
        type=str,
        default=JSON_FILE,
        help=f'JSON file path (default: {JSON_FILE})'
    )
    
    parser.add_argument(
        '--route-type',
        type=str,
        default="Expressway",
        help='Route type (default: Expressway)'
    )
    
    parser.add_argument(
        '--property',
        type=str,
        action='append',
        default=[],
        help='Additional property in format "key:value" (can be used multiple times)'
    )
    
    parser.add_argument(
        '--clear-all',
        action='store_true',
        help='Clear all Schedule relationships before ingestion (use with caution)'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default=None,
        help='Source identifier for the ingested data (e.g., filename or source name). Used for tracking and selective deletion.'
    )
    
    parser.add_argument(
        '--clear-last',
        type=str,
        metavar='SOURCE',
        help='Clear only schedules with the specified source before ingestion'
    )
    
    args = parser.parse_args()
    
    # Parse additional properties
    optional_properties = {}
    for prop in args.property:
        if ':' in prop:
            key, value = prop.split(':', 1)
            optional_properties[key.strip()] = value.strip()
        else:
            print(f"⚠️  Warning: Property '{prop}' not in format 'key:value', skipping...")
    
    # Add source if provided
    if args.source:
        optional_properties['source'] = args.source
    else:
        # Use JSON filename as default source if not specified
        json_filename = os.path.basename(args.json_file)
        optional_properties['source'] = json_filename
    
    print("🚀 Starting Schedule Data Ingestion to Neo4j Aura")
    print("="*60)
    
    # Connect to Neo4j Aura
    print("🔌 Connecting to Neo4j Aura...")
    try:
        driver = GraphDatabase.driver(
            URI,
            auth=basic_auth(USER, PASSWORD),
            database=DATABASE
        )
        
        # Test connection
        with driver.session(database=DATABASE) as session:
            result = session.run("RETURN 1 as test")
            if result.single()["test"] == 1:
                print("✅ Connected to Neo4j Aura successfully!")
        print()
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j Aura: {e}")
        return
    
    # Clear data if requested
    if args.clear_all:
        print("🗑️  Clearing all Schedule relationships...")
        deleted = clear_last_ingestion(driver)
        print(f"   ✅ Deleted {deleted['schedules_deleted']} schedules")
        print(f"   ✅ Deleted {deleted['orphaned_places_deleted']} orphaned places")
        print()
    elif args.clear_last:
        print(f"🗑️  Clearing schedules with source '{args.clear_last}'...")
        deleted = clear_last_ingestion(driver, source=args.clear_last)
        print(f"   ✅ Deleted {deleted['schedules_deleted']} schedules")
        print(f"   ✅ Deleted {deleted['orphaned_places_deleted']} orphaned places")
        print()
    
    # Ingest data
    try:
        counts = ingest_schedule_data(
            driver,
            args.json_file,
            route_type=args.route_type,
            optional_properties=optional_properties
        )
        
        print(f"\n✅ Ingestion Summary:")
        print(f"   • Routes processed: {counts['routes_processed']}")
        print(f"   • Places created/merged: {counts['places_created']}")
        print(f"   • Schedules created: {counts['schedules_created']}")
        
    except Exception as e:
        print(f"❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        driver.close()
        return
    
    # Verify ingestion
    verify_ingestion(driver)
    
    # Close connection
    driver.close()
    print("\n✅ Ingestion completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()

