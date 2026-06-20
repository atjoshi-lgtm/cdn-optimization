"""
discover_analyzable_paths.py

Scans the local database, topology map, and file system to output a list of 
all valid Client -> Edge -> Parent paths that have enough data for pairwise analysis.
Filters out noise by applying a configured traffic volume threshold.
"""

import sqlite3
import json
from pathlib import Path

from cdn_optimizer.core.config_loader import load_config
from cdn_optimizer.data_access.csv_parser import load_metro_maps, load_traffic_matrix
from cdn_optimizer.data_access.sqlite_client import SQLiteClient
from cdn_optimizer.core.exceptions import MissingDataError

def main():
    config = load_config()
    
    # 1. Load topology, DB client, and the Traffic Matrix
    name_to_id, id_to_name, name_to_airport = load_metro_maps(config.metro_areas_csv)
    traffic_matrix = load_traffic_matrix(config.served_from_csv)
    db_client = SQLiteClient(config.db_path)
    
    # 2. Find which Edge Metros actually have Footprint Descriptors
    available_fds_airports = {f.stem.upper() for f in config.fds_dir.glob("*.txt")}

    # 3. Query the Database for existing Client -> Edge latency pairs
    query = f"""
        SELECT DISTINCT client_metro, region_metro 
        FROM netopt_perf_edge_rtt_ansabni 
        WHERE pdate IN ('2026-02-07', '2026-02-08', '2026-02-09')
    """
    
    valid_paths = []
    parent_cache = {}
    
    try:
        with sqlite3.connect(config.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for client_id_str, edge_metro_name in rows:
                try:
                    client_id = int(client_id_str)
                except ValueError:
                    continue
                
                # Resolvers
                if client_id not in id_to_name: continue
                edge_airport_code = name_to_airport.get(edge_metro_name)
                if not edge_airport_code: continue
                client_name = id_to_name[client_id]
                
                # Check 1: Traffic Threshold Filter (Is this a SIGNIFICANT relationship?)
                traffic_mbps = traffic_matrix.get((client_name, edge_metro_name), 0.0)
                if traffic_mbps <= config.traffic_threshold_mbps:
                    continue

                # Check 2: FDS availability
                if edge_airport_code in available_fds_airports:
                    
                    # Dynamically resolve the active Parent Metro
                    if edge_metro_name not in parent_cache:
                        try:
                            parent = db_client.get_active_parent_for_edge(edge_metro_name)
                            parent_cache[edge_metro_name] = parent
                        except MissingDataError:
                            parent_cache[edge_metro_name] = "UNKNOWN"
                            
                    valid_paths.append({
                        "client": client_name,
                        "edge_name": edge_metro_name,
                        "edge_airport": edge_airport_code,
                        "parent": parent_cache[edge_metro_name],
                        "traffic_mbps": traffic_mbps
                    })
                    
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        return

    # 4. Structure the output
    paths_by_edge = {}
    for path in valid_paths:
        edge_key = f"{path['edge_name']} ({path['edge_airport']})"
        if edge_key not in paths_by_edge:
            paths_by_edge[edge_key] = {"active_parent": path["parent"], "serves_clients": []}
            
        paths_by_edge[edge_key]["serves_clients"].append({
            "client_name": path["client"],
            "traffic_mbps": path["traffic_mbps"]
        })
        
    for edge_key in paths_by_edge:
        paths_by_edge[edge_key]["serves_clients"].sort(key=lambda x: x["traffic_mbps"], reverse=True)

    # 5. Output to JSON
    output_file = Path("data/analyzable_paths.json")
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(paths_by_edge, f, indent=4, sort_keys=True)

    print(f"Discovered {len(valid_paths)} significant Client -> Edge -> Parent paths (> {config.traffic_threshold_mbps} Mbps).")
    print(f"Results written to: {output_file.resolve()}")

if __name__ == "__main__":
    main()