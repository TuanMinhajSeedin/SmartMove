# Schedule Data Ingestion Example

This document shows how your schedule data will look after ingestion into Neo4j Aura.

## 📍 Place Nodes Created

The following Place nodes will be created (or merged if they already exist):

```
(:Place {name: "Galle"})
(:Place {name: "Kadawatha"})
(:Place {name: "Negombo"})
```

## 🚌 Schedule Relationships Created

### Table 1: Galle → Kadawatha

Based on the first table, 4 Schedule relationships will be created:

#### Schedule 1:
**Source Data:** `[{"arrival_to_terminal": "6:00", "departure_from_terminal": "6:15"}, "7.45"]`
- `departure` extracted from `departure_from_terminal` in first cell: "06:15"
- `arrival` extracted from second element: "07:45"
```
(Galle)-[:Schedule {
  departure: "06:15",
  arrival: "07:45",
  departure_from_terminal: "06:15",
  arrival_to_terminal: "07:45",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Kadawatha)
```

#### Schedule 2:
**Source Data:** `[{"arrival_to_terminal": "6:15", "departure_from_terminal": "6:30"}, "8:00"]`
- `departure` extracted from `departure_from_terminal` in first cell: "06:30"
- `arrival` extracted from second element: "08:00"
```
(Galle)-[:Schedule {
  departure: "06:30",
  arrival: "08:00",
  departure_from_terminal: "06:30",
  arrival_to_terminal: "08:00",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Kadawatha)
```

#### Schedule 3:
**Source Data:** `[{"arrival_to_terminal": "14:00", "departure_from_terminal": "14:15"}, "15:45"]`
- `departure` extracted from `departure_from_terminal` in first cell: "14:15"
- `arrival` extracted from second element: "15:45"
```
(Galle)-[:Schedule {
  departure: "14:15",
  arrival: "15:45",
  departure_from_terminal: "14:15",
  arrival_to_terminal: "15:45",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Kadawatha)
```

#### Schedule 4:
**Source Data:** `[{"arrival_to_terminal": "16:15", "departure_from_terminal": "16:30"}, "18:00"]`
- `departure` extracted from `departure_from_terminal` in first cell: "16:30"
- `arrival` extracted from second element: "18:00"
```
(Galle)-[:Schedule {
  departure: "16:30",
  arrival: "18:00",
  departure_from_terminal: "16:30",
  arrival_to_terminal: "18:00",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Kadawatha)
```

### Table 2: Multiple Routes

Based on the second table, the following routes will be created:

#### Route 1: Negombo → Kadawatha
**Source Data:** `["05:30", {"arrival_to_terminal": "7:30", "departure_from_terminal": "7:45"}, "9:15"]`
- `departure` extracted from first element: "05:30"
- `arrival` extracted from last element (final destination): "09:15"
- `departure_from_terminal` extracted from intermediate cell's `departure_from_terminal`: "07:45"
- `arrival_to_terminal` extracted from intermediate cell's `arrival_to_terminal`: "07:30"
```
(Negombo)-[:Schedule {
  departure: "05:30",
  arrival: "09:15",
  departure_from_terminal: "07:45",
  arrival_to_terminal: "07:30",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Kadawatha)
```

#### Route 2: Kadawatha → Galle
**Source Data:** `["05:30", {"arrival_to_terminal": "7:30", "departure_from_terminal": "7:45"}, "9:15"]`
- `departure` extracted from intermediate cell's `departure_from_terminal`: "07:45"
- `arrival` extracted from last element: "09:15"
- `departure_from_terminal`: "07:45"
- `arrival_to_terminal`: "09:15"
```
(Kadawatha)-[:Schedule {
  departure: "07:45",
  arrival: "09:15",
  departure_from_terminal: "07:45",
  arrival_to_terminal: "09:15",
  route_type: "Expressway",
  created_at: <timestamp>
}]->(Galle)
```

**Note:** For Table 2 (routes with intermediate stops):
- **First route (Negombo → Kadawatha)**: Uses first element as `departure`, last element as `arrival`, and extracts terminal times from intermediate cell
- **Second route (Kadawatha → Galle)**: Uses intermediate cell's `departure_from_terminal` as `departure`, last element as `arrival`

**Note:** The second table creates relationships for:
- Negombo → Kadawatha (4 schedules)
- Kadawatha → Galle (4 schedules)

## 📊 Visual Graph Representation

```
┌─────────┐                    ┌──────────┐                    ┌─────────┐
│ Galle   │                    │Kadawatha │                    │ Negombo │
│         │                    │          │                    │         │
│         │──Schedule (4x)───→│          │←──Schedule (4x)───│         │
│         │                    │          │                    │         │
│         │←──Schedule (4x)───│          │──Schedule (4x)───→│         │
└─────────┘                    └──────────┘                    └─────────┘
```

## 🔍 Example Cypher Queries

### View All Schedules from Galle to Kadawatha

```cypher
MATCH (from:Place {name: "Galle"})-[s:Schedule]->(to:Place {name: "Kadawatha"})
RETURN 
  from.name AS from_place,
  to.name AS to_place,
  s.departure AS departure,
  s.arrival AS arrival,
  s.departure_from_terminal AS departure_from_terminal,
  s.arrival_to_terminal AS arrival_to_terminal,
  s.route_type AS route_type
ORDER BY s.departure
```

**Expected Output:**
```
from_place | to_place  | departure | arrival | departure_from_terminal | arrival_to_terminal | route_type
-----------|-----------|-----------|---------|------------------------|---------------------|------------
Galle      | Kadawatha | 06:15     | 07:45   | 06:15                  | 07:45              | Expressway
Galle      | Kadawatha | 06:30     | 08:00   | 06:30                  | 08:00              | Expressway
Galle      | Kadawatha | 14:15     | 15:45   | 14:15                  | 15:45              | Expressway
Galle      | Kadawatha | 16:30     | 18:00   | 16:30                  | 18:00              | Expressway
```

### View All Schedules with Terminal Times

```cypher
MATCH (from:Place)-[s:Schedule]->(to:Place)
WHERE s.departure_from_terminal IS NOT NULL 
  AND s.arrival_to_terminal IS NOT NULL
RETURN 
  from.name AS from_place,
  to.name AS to_place,
  s.departure AS departure,
  s.arrival AS arrival,
  s.departure_from_terminal AS dep_terminal,
  s.arrival_to_terminal AS arr_terminal,
  s.route_type AS route_type
ORDER BY from.name, s.departure
LIMIT 20
```

### Find All Routes Through Kadawatha

```cypher
MATCH (from:Place)-[s:Schedule]->(k:Place {name: "Kadawatha"})-[s2:Schedule]->(to:Place)
RETURN 
  from.name AS origin,
  k.name AS intermediate,
  to.name AS destination,
  s.departure AS dep_from_origin,
  s.arrival AS arr_at_intermediate,
  s2.departure AS dep_from_intermediate,
  s2.arrival AS arr_at_destination
ORDER BY s.departure
```

**Expected Output:**
```
origin  | intermediate | destination | dep_from_origin | arr_at_intermediate | dep_from_intermediate | arr_at_destination
---------|--------------|-------------|-----------------|---------------------|----------------------|-------------------
Negombo  | Kadawatha    | Galle       | 05:30           | 07:30               | 07:45                | 09:15
Negombo  | Kadawatha    | Galle       | 05:00           | 07:45               | 08:00                | 09:30
Negombo  | Kadawatha    | Galle       | 16:30           | 18:00               | 18:15                | 19:45
Negombo  | Kadawatha    | Galle       | 15:00           | 18:15               | 18:30                | 20:00
```

**Note:** 
- The `dep_from_origin` is the departure from Negombo (first element)
- The `arr_at_intermediate` comes from the `arrival_to_terminal` property in the intermediate cell
- The `dep_from_intermediate` comes from the `departure_from_terminal` property in the intermediate cell
- The `arr_at_destination` is the arrival at Galle (last element)

### Count Schedules by Route

```cypher
MATCH (from:Place)-[s:Schedule]->(to:Place)
RETURN 
  from.name + " → " + to.name AS route,
  count(s) AS schedule_count,
  collect(s.departure) AS departure_times
ORDER BY schedule_count DESC
```

**Expected Output:**
```
route              | schedule_count | departure_times
-------------------|----------------|----------------------------------------
Galle → Kadawatha  | 4              | ["06:15", "06:30", "14:15", "16:30"]
Negombo → Kadawatha| 4              | ["05:30", "05:00", "16:30", "15:00"]
Kadawatha → Galle  | 4              | ["07:45", "08:00", "18:15", "18:30"]
```

**Note:** For Negombo → Kadawatha route, the `departure` times are from the first element, and the `arrival` times are from the last element (Galle's arrival time), with terminal times extracted from the intermediate cell.

## 📋 Complete Data Structure Summary

After ingestion, you will have:

- **3 Place nodes**: Galle, Kadawatha, Negombo
- **12 Schedule relationships** total:
  - 4 from Galle to Kadawatha
  - 4 from Negombo to Kadawatha
  - 4 from Kadawatha to Galle

Each Schedule relationship contains:
- `departure`: Main departure time
  - For direct routes (2 locations): Extracted from `departure_from_terminal` in first cell, or first cell value if string
  - For routes with intermediate stops: First element (origin departure time)
- `arrival`: Main arrival time
  - For direct routes (2 locations): Extracted from second element (destination cell)
  - For routes with intermediate stops: Last element (final destination arrival time)
- `departure_from_terminal`: When bus departs from origin/intermediate terminal
  - For direct routes: Equals `departure`
  - For routes with intermediate stops: Extracted from intermediate cell's `departure_from_terminal`
- `arrival_to_terminal`: When bus arrives at intermediate/destination terminal
  - For direct routes: Equals `arrival`
  - For routes with intermediate stops: Extracted from intermediate cell's `arrival_to_terminal`
- `route_type`: "Expressway" (or custom value if specified)
- `created_at`: Timestamp when relationship was created
- Any additional optional properties you specify via `--property` arguments

## 🎯 Key Features

1. **Extraction Logic**:
   - **For direct routes (2 locations)**:
     - `departure`: Extracted from `departure_from_terminal` in first cell (or first cell value if string)
     - `arrival`: Extracted from second element (destination cell)
     - `departure_from_terminal`: Equals `departure`
     - `arrival_to_terminal`: Equals `arrival`
   - **For routes with intermediate stops (3+ locations)**:
     - `departure`: First element (origin departure time)
     - `arrival`: Last element (final destination arrival time)
     - `departure_from_terminal`: Extracted from intermediate cell's `departure_from_terminal`
     - `arrival_to_terminal`: Extracted from intermediate cell's `arrival_to_terminal`

2. **Terminal Time Preservation**: Both `departure_from_terminal` and `arrival_to_terminal` are preserved from the nested JSON objects or extracted from string values

3. **Multiple Schedules**: Multiple Schedule relationships can exist between the same two places with different times

4. **Safe Merging**: Place nodes are merged (won't create duplicates), but Schedule relationships are created (allowing multiple schedules)

5. **Flexible Properties**: Additional properties can be added via command-line arguments

## 📝 Data Extraction Rules

### Rule 1: Direct Routes (2 Locations)
- **Departure**: Extract from `departure_from_terminal` in first cell (or first cell value if string)
- **Arrival**: Extract from second element (destination cell)
- **Terminal Properties**: `departure_from_terminal` = `departure`, `arrival_to_terminal` = `arrival`

### Rule 2: Routes with Intermediate Stops (3+ Locations)
- **Departure**: First element (origin departure time)
- **Arrival**: Last element (final destination arrival time)
- **Terminal Properties**: Extract from intermediate cell's `departure_from_terminal` and `arrival_to_terminal`

### Example Transformations:

**Example 1 (Direct Route):** `[{"departure_from_terminal": "6:15"}, "7.45"]`
- `departure` = "06:15" (from `departure_from_terminal`)
- `arrival` = "07:45" (from second element)
- `departure_from_terminal` = "06:15"
- `arrival_to_terminal` = "07:45"

**Example 2 (Route with Intermediate Stop):** `["05:30", {"arrival_to_terminal": "7:30", "departure_from_terminal": "7:45"}, "9:15"]`
- `departure` = "05:30" (from first element)
- `arrival` = "09:15" (from last element)
- `departure_from_terminal` = "07:45" (from intermediate cell's `departure_from_terminal`)
- `arrival_to_terminal` = "07:30" (from intermediate cell's `arrival_to_terminal`)

