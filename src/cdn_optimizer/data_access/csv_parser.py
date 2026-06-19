"""
csv_parser.py

Handles reading and parsing of tabular metadata files (e.g., metro_areas.csv).
"""

import csv
from pathlib import Path
from typing import Dict, Tuple


def load_metro_maps(csv_path: str | Path) -> Tuple[Dict[str, int], Dict[int, str]]:
    """
    Parse the metro_areas.csv file to map metro names to IDs, and IDs to names.
    
    The file is expected to have a header, with Column 0 as the ID and Column 1 as the Name.

    Args:
        csv_path: Path to the metro_areas.csv file.
        
    Returns:
        A tuple containing:
        - name_to_id: Dict[str, int]
        - id_to_name: Dict[int, str]
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Metro areas CSV not found: {path}")

    name_to_id: Dict[str, int] = {}
    id_to_name: Dict[int, str] = {}
    
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header row
        
        for row in reader:
            if len(row) >= 2:
                metro_id = int(row[0].strip())
                metro_name = row[1].strip().strip('"')
                
                name_to_id[metro_name] = metro_id
                id_to_name[metro_id] = metro_name
                
    return name_to_id, id_to_name