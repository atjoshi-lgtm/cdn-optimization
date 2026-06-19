"""
exceptions.py

Custom exception classes for the CDN Optimizer.
"""

class MissingDataError(ValueError):
    """Raised when a required dataset (e.g., a latency PDF) is missing from the data source."""
    pass