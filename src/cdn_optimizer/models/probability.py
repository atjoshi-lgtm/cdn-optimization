"""
probability.py

Mathematical probability distributions and convolutions for latency modeling.
Strictly decoupled from data fetching and plotting.
"""

from dataclasses import dataclass
from math import erf, sqrt
from typing import Dict, Iterable, Iterator, List, Mapping, Tuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PdfBucket:
    """Represents a latency bucket covering [lower_ms, upper_ms)."""
    lower_ms: int
    upper_ms: int
    count: float

    @property
    def width_ms(self) -> int:
        return max(0, self.upper_ms - self.lower_ms)

    def to_millisecond_counts(self) -> Iterator[Tuple[int, float]]:
        """Evenly distribute the count across each millisecond in the bucket."""
        width = self.width_ms
        if width <= 0 or self.count <= 0:
            return iter(())
        per_ms = self.count / width
        return ((ms, per_ms) for ms in range(self.lower_ms, self.upper_ms))


class ProbabilityDensityFunction:
    """Stores and manipulates a probability distribution function."""

    def __init__(self, buckets: Iterable[PdfBucket]) -> None:
        self._buckets: List[PdfBucket] = sorted(
            (b for b in buckets if b.count > 0 and b.width_ms > 0),
            key=lambda b: b.lower_ms,
        )
        self._probability_series: pd.Series | None = None

    def total_count(self) -> float:
        return sum(b.count for b in self._buckets)

    @property
    def probability_series(self) -> pd.Series:
        """Cached probability series built at millisecond resolution."""
        if self._probability_series is not None:
            return self._probability_series

        tally: Dict[int, float] = {}
        for bucket in self._buckets:
            for ms, count in bucket.to_millisecond_counts():
                tally[ms] = tally.get(ms, 0.0) + count

        if not tally:
            self._probability_series = pd.Series(dtype=float)
            return self._probability_series

        series = pd.Series(tally, dtype=float).sort_index()
        self._probability_series = series
        return series

    def with_fraction_at(self, millisecond: int, fraction: float) -> "ProbabilityDensityFunction":
        """Scale existing mass to (1 - fraction) and add fraction at the specified millisecond."""
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("fraction must be between 0 and 1 inclusive")

        millisecond = int(millisecond)
        series = self.probability_series.astype(float)
        total = float(series.sum())

        if total <= 0.0:
            if fraction <= 0.0:
                return ProbabilityDensityFunction([])
            return ProbabilityDensityFunction.from_millisecond_series(
                pd.Series({millisecond: 1.0}, dtype=float)
            )

        if fraction >= 1.0:
            scaled = pd.Series(dtype=float)
        else:
            scale = (1.0 - fraction) / total
            scaled = (series * scale).astype(float)

        scaled.loc[millisecond] = scaled.get(millisecond, 0.0) + fraction
        scaled = scaled.clip(lower=0).sort_index()

        return ProbabilityDensityFunction.from_millisecond_series(scaled)

    def millisecond_at_percentile(self, percentile: float) -> int:
        """Return the smallest millisecond whose cumulative probability meets the percentile."""
        if not 0.0 <= percentile <= 100.0:
            raise ValueError("percentile must be between 0 and 100 inclusive")

        series = self.probability_series.astype(float)
        total = float(series.sum())
        if total <= 0.0:
            raise ValueError("Cannot compute percentile for a PDF with zero total mass")

        cdf = (series.cumsum() / total).astype(float)
        fraction = percentile / 100.0

        if fraction <= 0.0:
            return int(cdf.index.min())
        if fraction >= 1.0:
            return int(cdf.index.max())

        meeting = cdf[cdf >= fraction]
        if not meeting.empty:
            return int(meeting.index[0])

        return int(cdf.index.max())

    def to_microsecond_pdf(self, step_us: int = 10) -> "ProbabilityDensityFunction":
        """Distribute mass uniformly within each millisecond and return a microsecond PDF."""
        series = self.probability_series.astype(float)
        if series.empty:
            return ProbabilityDensityFunction([])

        micro_values: Dict[int, float] = {}
        steps_per_ms = 1_000 // step_us
        
        for millisecond, probability in series.items():
            if probability <= 0.0:
                continue
            base_microsecond = int(millisecond) * 1_000
            share = probability / steps_per_ms
            for i in range(steps_per_ms):
                micro_values[base_microsecond + (i * step_us)] = share

        micro_series = pd.Series(micro_values, dtype=float).sort_index()
        total = float(micro_series.sum())
        
        return ProbabilityDensityFunction.from_millisecond_series(micro_series / total if total > 0 else micro_series)

    @classmethod
    def from_millisecond_series(cls, series: pd.Series) -> "ProbabilityDensityFunction":
        """Create a PDF from a millisecond-indexed series."""
        buckets = []
        if series is not None:
            series = series.dropna().astype(float)
            for millisecond, count in series.items():
                if count > 0:
                    ms = int(millisecond)
                    buckets.append(PdfBucket(lower_ms=ms, upper_ms=ms + 1, count=float(count)))

        pdf = cls(buckets)
        pdf._probability_series = series.sort_index()
        return pdf

    def normalised_clone(self) -> "ProbabilityDensityFunction":
        series = self.probability_series
        total = float(series.sum())
        if total <= 0:
            return ProbabilityDensityFunction([])
        return ProbabilityDensityFunction.from_millisecond_series(series / total)


class Convolution:
    """Convolve two probability density functions using FFT."""

    def convolve(self, lhs: ProbabilityDensityFunction, rhs: ProbabilityDensityFunction) -> ProbabilityDensityFunction:
        lhs_series = lhs.probability_series.astype(float)
        rhs_series = rhs.probability_series.astype(float)

        if lhs_series.empty or rhs_series.empty:
            return ProbabilityDensityFunction.from_millisecond_series(pd.Series(dtype=float))

        lhs_min, lhs_max = int(lhs_series.index.min()), int(lhs_series.index.max())
        rhs_min, rhs_max = int(rhs_series.index.min()), int(rhs_series.index.max())

        lhs_length = lhs_max - lhs_min + 1
        rhs_length = rhs_max - rhs_min + 1

        lhs_array = np.zeros(lhs_length, dtype=float)
        rhs_array = np.zeros(rhs_length, dtype=float)

        lhs_array[(lhs_series.index.to_numpy(dtype=int) - lhs_min)] = lhs_series.to_numpy(dtype=float)
        rhs_array[(rhs_series.index.to_numpy(dtype=int) - rhs_min)] = rhs_series.to_numpy(dtype=float)

        result_length = lhs_length + rhs_length - 1
        fft_size = 1 << (result_length - 1).bit_length()

        convolved = np.fft.irfft(np.fft.rfft(lhs_array, fft_size) * np.fft.rfft(rhs_array, fft_size), fft_size)[:result_length]

        result_start = lhs_min + rhs_min
        result_series = pd.Series(convolved, index=np.arange(result_start, result_start + result_length, dtype=int), dtype=float)

        return ProbabilityDensityFunction.from_millisecond_series(result_series)


def gaussian_pdf(mean: float, stddev: float, lower_ms: int, upper_ms: int) -> ProbabilityDensityFunction:
    """Create a PDF approximating a truncated Gaussian distribution."""
    if stddev <= 0 or upper_ms <= lower_ms:
        raise ValueError("Invalid parameters for Gaussian PDF")

    sqrt_two = sqrt(2.0)
    def _cdf(x: float) -> float:
        return 0.5 * (1.0 + erf((x - float(mean)) / (float(stddev) * sqrt_two)))

    masses = {}
    for ms in range(int(lower_ms), int(upper_ms)):
        mass = _cdf(ms + 1.0) - _cdf(ms)
        if mass > 0.0:
            masses[ms] = mass

    total_mass = sum(masses.values())
    if total_mass <= 0.0:
        raise ValueError("Gaussian mass within bounds is numerically zero")

    series = pd.Series({ms: mass / total_mass for ms, mass in masses.items()}, dtype=float)
    return ProbabilityDensityFunction.from_millisecond_series(series)


def weighted_pdf_sum(pdfs: Iterable[ProbabilityDensityFunction], weights: Iterable[float]) -> ProbabilityDensityFunction:
    """Combine multiple PDFs using the supplied weights."""
    pdf_list, weight_list = list(pdfs), list(weights)
    if not pdf_list or len(pdf_list) != len(weight_list):
        raise ValueError("Invalid PDF or weight lists")

    accumulator = pd.Series(dtype=float)
    total_weight = 0.0

    for pdf, weight in zip(pdf_list, weight_list, strict=True):
        if weight <= 0 or pdf.probability_series.empty:
            continue
        accumulator = accumulator.add(pdf.probability_series.astype(float) * float(weight), fill_value=0.0)
        total_weight += float(weight)

    if total_weight <= 0 or accumulator.empty:
        raise ValueError("Combined PDF has zero total weight or mass")

    return ProbabilityDensityFunction.from_millisecond_series(accumulator / accumulator.sum())