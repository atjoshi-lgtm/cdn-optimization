"""
config_loader.py

Parses YAML configuration files into strictly typed Python dataclasses.
"""

import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CDNConfig:
    """Strictly typed configuration object for the CDN Optimizer."""
    bucket: str
    db_path: Path
    metro_areas_csv: Path
    fds_dir: Path


def load_config(config_path: str | Path = "config/default_config.yaml") -> CDNConfig:
    """
    Load and parse the YAML configuration file.
    
    Args:
        config_path: Path to the YAML config file.
        
    Returns:
        A populated CDNConfig dataclass.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    bucket_name = data.get("bucket", "AkamaiHD")
    data_paths = data.get("data_paths", {})

    # Dynamically inject the bucket name into the FDS directory path
    raw_fds_dir = data_paths.get("fds_dir", "data/FDS_{bucket}")
    formatted_fds_dir = raw_fds_dir.format(bucket=bucket_name)

    return CDNConfig(
        bucket=bucket_name,
        db_path=Path(data_paths.get("db_path", "data/PERF/perf_data.db")),
        metro_areas_csv=Path(data_paths.get("metro_areas_csv", "data/PERF/metro_areas.csv")),
        fds_dir=Path(formatted_fds_dir)
    )