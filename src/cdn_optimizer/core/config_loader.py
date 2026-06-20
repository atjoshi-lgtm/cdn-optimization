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
    traffic_threshold_mbps: float
    db_path: Path
    metro_areas_csv: Path
    fds_dir: Path
    served_from_csv: Path


def load_config(config_path: str | Path = "config/default_config.yaml") -> CDNConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    bucket_name = data.get("bucket", "AkamaiHD")
    traffic_threshold = float(data.get("traffic_threshold_mbps", 20000.0))
    data_paths = data.get("data_paths", {})

    raw_fds_dir = data_paths.get("fds_dir", "data/FDS_{bucket}")
    raw_served_from = data_paths.get("served_from_csv", "data/SERVEDFROM_DATA/served_from_{bucket}.csv")

    return CDNConfig(
        bucket=bucket_name,
        traffic_threshold_mbps=traffic_threshold,
        db_path=Path(data_paths.get("db_path", "data/PERF/perf_data.db")),
        metro_areas_csv=Path(data_paths.get("metro_areas_csv", "data/PERF/metro_areas.csv")),
        fds_dir=Path(raw_fds_dir.format(bucket=bucket_name)),
        served_from_csv=Path(raw_served_from.format(bucket=bucket_name))
    )