"""
fds_loader.py

Handles reading and parsing Footprint Descriptor (FDS) text files.
Translates text rows into mathematical FootprintDescriptor models.
"""

from pathlib import Path
from typing import List

from cdn_optimizer.models.footprint import FootprintPoint, FootprintDescriptor


def load_footprint_descriptor(file_path: str | Path, encoding: str = "utf-8") -> FootprintDescriptor:
    """
    Read an FDS text file and return a populated FootprintDescriptor.

    The FDS files are expected to be whitespace-separated with at least 5 columns.
    Column 0: Cache Space (MB)
    Column 4: Expected Hit Rate (%)

    Args:
        file_path: Path to the FDS .txt file.
        encoding: Text encoding (defaults to utf-8).

    Returns:
        A mathematically pure FootprintDescriptor object.
        
    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If a row has fewer than 5 columns or cannot be parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Footprint descriptor file not found: {path}")

    points: List[FootprintPoint] = []

    with path.open(encoding=encoding) as handle:
        iterator = iter(handle)
        
        # Skip the first line (header/metadata as per the FDS convention)
        next(iterator, None)

        for line_number, raw_line in enumerate(iterator, start=2):
            stripped = raw_line.strip()
            
            # Ignore empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            columns = stripped.split()
            
            # We need at least 5 columns to access index 4 (the hit rate)
            if len(columns) < 5:
                raise ValueError(
                    f"Expected at least 5 columns on line {line_number} of {path}, "
                    f"found {len(columns)}"
                )

            # Parse cache space (MB) and hit rate (%)
            cache_space = int(float(columns[0]))
            hitrate = float(columns[4])

            points.append(FootprintPoint(cache_space=cache_space, hitrate=hitrate))

    return FootprintDescriptor(points)