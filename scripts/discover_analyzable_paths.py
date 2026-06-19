"""
discover_analyzable_paths.py

Scans the local database, topology map, and file system to output a list of 
all valid Client -> Edge paths that have enough data for pairwise analysis.
"""

import sqlite3
from cdn_optimizer.core.config_loader import load_config
from cdn_optimizer.data_access.csv_parser import load_metro_maps

def main():
    config = load_config()
    
    # 1. Load topology mappings
    name_to_id, id_to_name, name_to_airport = load_metro_maps(config.metro_areas_csv)
    
    # 2. Find which Edge Metros actually have Footprint Descriptors
    available_fds_airports = {f.stem.upper() for f in config.fds_dir.glob("*.txt")}
    print(f"Found {len(available_fds_airports)} Edge Metros with Cache Footprint models in {config.fds_dir}.")

    # 3. Query the Database for existing Client -> Edge latency pairs
    query = f"""
        SELECT DISTINCT client_metro, region_metro 
        FROM netopt_perf_edge_rtt_ansabni 
        WHERE pdate IN ('2026-02-07', '2026-02-08', '2026-02-09')
    """
    
    valid_paths = []
    
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
                
                # Check 1: Can we resolve the Client ID to a Name?
                if client_id not in id_to_name:
                    continue
                    
                # Check 2: Can we resolve the Edge Metro Name to an Airport Code?
                edge_airport_code = name_to_airport.get(edge_metro_name)
                if not edge_airport_code:
                    continue
                    
                # Check 3: Does that Airport Code have an FDS file?
                if edge_airport_code in available_fds_airports:
                    client_name = id_to_name[client_id]
                    valid_paths.append((client_name, edge_metro_name, edge_airport_code))
                    
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}. Are you sure perf_data.db is in {config.db_path}?")
        return

    # 4. Output the results
    print(f"\nDiscovered {len(valid_paths)} fully analyzable Client -> Edge paths.\n")
    
    # Group by Edge Metro for cleaner output
    paths_by_edge = {}
    for client, edge_name, edge_airport in valid_paths:
        key = f"{edge_name} ({edge_airport})"
        paths_by_edge.setdefault(key, []).append(client)
        
    for edge_key, clients in sorted(paths_by_edge.items()):
        print(f"Edge Metro: {edge_key}")
        for client in sorted(clients):
            print(f"  └─ Serves Client: {client}")

if __name__ == "__main__":
    main()