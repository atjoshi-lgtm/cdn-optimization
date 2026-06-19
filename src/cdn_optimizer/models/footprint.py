"""
footprint.py

Models the cache-efficiency curve (Footprint Descriptor).
Strictly decoupled from file I/O and visualization.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping
from bisect import bisect_left


@dataclass(frozen=True)
class FootprintPoint:
    """A single cache space (MB) and hit-rate (%) observation."""
    cache_space: int
    hitrate: float


class FootprintDescriptor:
    """
    Footprint descriptor lookups for cache space and hit-rate values.
    Maps provisioned disk space to expected cache hit rates.
    """

    def __init__(self, points: Iterable[FootprintPoint]) -> None:
        """
        Initialize the descriptor with raw points.
        
        Args:
            points: An iterable of FootprintPoint objects.
        """
        unique_by_cache: MutableMapping[int, FootprintPoint] = {}

        for point in points:
            unique_by_cache.setdefault(point.cache_space, point)

        if not unique_by_cache:
            raise ValueError("FootprintDescriptor requires at least one data point")

        self._points_by_cache: Mapping[int, FootprintPoint] = dict(
            sorted(unique_by_cache.items(), key=lambda item: item[0])
        )

        points_by_hitrate: Dict[float, FootprintPoint] = {}
        for point in self._points_by_cache.values():
            existing = points_by_hitrate.get(point.hitrate)
            if existing is None or point.cache_space < existing.cache_space:
                points_by_hitrate[point.hitrate] = point

        self._points_sorted_by_cache: List[FootprintPoint] = list(self._points_by_cache.values())
        self._cache_spaces: List[int] = [p.cache_space for p in self._points_sorted_by_cache]

        self._points_sorted_by_hitrate: List[FootprintPoint] = sorted(
            points_by_hitrate.values(), key=lambda p: p.hitrate
        )
        self._hitrates: List[float] = [p.hitrate for p in self._points_sorted_by_hitrate]

    def hitrate_for_cache(self, cache_space: int) -> float:
        """Return the hit-rate corresponding to cache_space (MB)."""
        point = self._points_by_cache.get(cache_space)
        if point is None:
            point = self.nearest_point_for_cache(cache_space)
        return point.hitrate

    def nearest_point_for_cache(self, cache_space: int) -> FootprintPoint:
        """Return the FootprintPoint closest to cache_space."""
        if not self._points_sorted_by_cache:
            raise ValueError("Descriptor contains no cache space data")

        index = bisect_left(self._cache_spaces, cache_space)

        if index <= 0:
            return self._points_sorted_by_cache[0]
        if index >= len(self._cache_spaces):
            return self._points_sorted_by_cache[-1]

        next_point = self._points_sorted_by_cache[index]
        prev_point = self._points_sorted_by_cache[index - 1]

        next_delta = abs(next_point.cache_space - cache_space)
        prev_delta = abs(cache_space - prev_point.cache_space)

        if prev_delta < next_delta:
            return prev_point
        if next_delta < prev_delta:
            return next_point

        return prev_point

    def nearest_cache_for_hitrate(self, hitrate: float) -> int:
        """Return the cache space with the nearest available hit-rate value."""
        point = self.nearest_point_for_hitrate(hitrate)
        return point.cache_space

    def nearest_point_for_hitrate(self, hitrate: float) -> FootprintPoint:
        """Return the FootprintPoint closest to hitrate."""
        if not self._points_sorted_by_hitrate:
            raise ValueError("Descriptor contains no hit-rate data")

        index = bisect_left(self._hitrates, hitrate)

        if index <= 0:
            return self._points_sorted_by_hitrate[0]
        if index >= len(self._hitrates):
            return self._points_sorted_by_hitrate[-1]

        next_point = self._points_sorted_by_hitrate[index]
        prev_point = self._points_sorted_by_hitrate[index - 1]

        next_delta = abs(next_point.hitrate - hitrate)
        prev_delta = abs(hitrate - prev_point.hitrate)

        if prev_delta < next_delta:
            return prev_point
        if next_delta < prev_delta:
            return next_point

        if prev_point.hitrate == next_point.hitrate:
            return prev_point if prev_point.cache_space <= next_point.cache_space else next_point

        return prev_point

    def find_max_possible_hitrate(self) -> FootprintPoint:
        """Return the FootprintPoint with the maximum hit-rate."""
        if not self._points_sorted_by_hitrate:
            raise ValueError("Descriptor contains no hit-rate data")
        return self._points_sorted_by_hitrate[-1]

    def smooth_by_cache_bucket(self, bucket_size_mb: int = 10 * 1024) -> "FootprintDescriptor":
        """
        Return a rebucketed/smoothed descriptor on fixed cache-size buckets.
        
        Args:
            bucket_size_mb: Bucket size in MB. Defaults to 10 GB (10 * 1024 MB).
        """
        if bucket_size_mb <= 0:
            raise ValueError("bucket_size_mb must be positive")

        bucket_to_hitrate: Dict[int, float] = {}
        for point in self._points_sorted_by_cache:
            bucket_cache_space = (point.cache_space // bucket_size_mb) * bucket_size_mb
            existing = bucket_to_hitrate.get(bucket_cache_space)
            if existing is None or point.hitrate < existing:
                bucket_to_hitrate[bucket_cache_space] = point.hitrate

        if not bucket_to_hitrate:
            raise ValueError("Descriptor contains no cache space data")

        sorted_bucket_points = sorted(bucket_to_hitrate.items(), key=lambda item: item[0])
        smoothed_points: List[FootprintPoint] = []

        for index, (cache_space, hitrate) in enumerate(sorted_bucket_points):
            smoothed_points.append(FootprintPoint(cache_space=cache_space, hitrate=hitrate))

            if index == len(sorted_bucket_points) - 1:
                continue

            next_cache_space, next_hitrate = sorted_bucket_points[index + 1]
            gap_buckets = ((next_cache_space - cache_space) // bucket_size_mb) - 1
            if gap_buckets <= 0:
                continue

            for gap_index in range(1, gap_buckets + 1):
                fraction = gap_index / (gap_buckets + 1)
                interpolated_hitrate = hitrate + (next_hitrate - hitrate) * fraction
                interpolated_cache_space = cache_space + gap_index * bucket_size_mb
                smoothed_points.append(
                    FootprintPoint(cache_space=interpolated_cache_space, hitrate=interpolated_hitrate)
                )

        smoothed_points.sort(key=lambda p: p.cache_space)

        plateau_smoothed_points: List[FootprintPoint] = list(smoothed_points)
        index = 0
        while index < len(plateau_smoothed_points):
            run_end = index
            current_hitrate = plateau_smoothed_points[index].hitrate

            while (
                run_end + 1 < len(plateau_smoothed_points)
                and plateau_smoothed_points[run_end + 1].hitrate == current_hitrate
            ):
                run_end += 1

            if run_end > index and index > 0:
                previous_hitrate = plateau_smoothed_points[index - 1].hitrate
                delta = current_hitrate - previous_hitrate
                run_length = run_end - index + 1

                for offset in range(run_length):
                    point = plateau_smoothed_points[index + offset]
                    adjusted_hitrate = previous_hitrate + delta * ((offset + 1) / run_length)
                    plateau_smoothed_points[index + offset] = FootprintPoint(
                        cache_space=point.cache_space,
                        hitrate=adjusted_hitrate,
                    )

            index = run_end + 1

        return FootprintDescriptor(plateau_smoothed_points)

    def __len__(self) -> int:
        return len(self._points_by_cache)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(points={len(self)})"