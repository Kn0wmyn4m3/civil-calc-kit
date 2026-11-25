"""Static analysis of a pin-and-roller beam in kN and m."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from math import fsum, isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class PointLoad:
    force: float
    position: float


@dataclass(frozen=True, slots=True)
class UniformLoad:
    intensity: float
    start: float = 0.0
    end: float | None = None


@dataclass(frozen=True, slots=True)
class AppliedMoment:
    moment: float
    position: float


@dataclass(frozen=True, slots=True)
class SectionCapacity:
    shear: float | None = None
    moment: float | None = None


@dataclass(frozen=True, slots=True)
class BeamStation:
    x: float
    shear: float
    moment: float
    side: Literal["Left", "Right"] | None = None


@dataclass(frozen=True, slots=True)
class BeamResult:
    length: float
    point_loads: tuple[PointLoad, ...]
    udls: tuple[UniformLoad, ...]
    moments: tuple[AppliedMoment, ...]
    reaction_a: float
    reaction_b: float
    stations: tuple[BeamStation, ...]
    chart_stations: tuple[BeamStation, ...]
    max_shear: BeamStation
    max_moment: BeamStation
    capacity: SectionCapacity

    @property
    def shear_utilization(self) -> float | None:
        if self.capacity.shear is not None:
            return abs(self.max_shear.shear) / self.capacity.shear
        return None

    @property
    def moment_utilization(self) -> float | None:
        if self.capacity.moment is not None:
            return abs(self.max_moment.moment) / self.capacity.moment
        return None


def analyze_beam(
    length: float,
    *,
    point_loads: Iterable[PointLoad] = (),
    udls: Iterable[UniformLoad] = (),
    moments: Iterable[AppliedMoment] = (),
    samples: int = 101,
    capacity: SectionCapacity = SectionCapacity(),
) -> BeamResult:
    """Return diagrams and absolute peaks with signed values at their locations.

    Positive input forces act down. Positive applied couples act counterclockwise.
    Reactions are positive up and internal bending is positive in sagging.
    """
    if not isfinite(length) or length <= 0:
        raise ValueError("Beam length must be positive and finite.")
    if not isinstance(samples, int) or samples < 2:
        raise ValueError("Samples must be an integer of at least 2.")
    for label, limit in (("Shear", capacity.shear), ("Moment", capacity.moment)):
        if limit is not None and (not isfinite(limit) or limit <= 0):
            raise ValueError(f"{label} capacity must be positive and finite.")

    point_loads = tuple(point_loads)
    moments = tuple(moments)
    spans = [
        (load.intensity, load.start, length if load.end is None else load.end)
        for load in udls
    ]
    for intensity, start, end in spans:
        if not isfinite(intensity) or not 0 <= start < end <= length:
            raise ValueError("UDLs need a finite intensity and 0 ≤ start < end ≤ length.")
    for load in point_loads:
        if not isfinite(load.force) or not 0 <= load.position <= length:
            raise ValueError("Point loads need a finite force and a position on the beam.")
    for load in moments:
        if not isfinite(load.moment) or not 0 <= load.position <= length:
            raise ValueError("Applied moments need a finite moment and a position on the beam.")

    # Distributed loads contribute their resultant at the midpoint of their run.
    forces = [(load.force, load.position) for load in point_loads]
    forces.extend((w * (end - start), start + (end - start) / 2) for w, start, end in spans)
    couple_reaction = fsum(load.moment / length for load in moments)
    reaction_a = fsum([couple_reaction, *(p * ((length - x) / length) for p, x in forces)])
    reaction_b = fsum([-couple_reaction, *(p * (x / length) for p, x in forces)])

    def section(x: float, side: Literal["Left", "Right"]) -> BeamStation:
        # Use the adjacent support for the internal limit at each end.
        if x == 0 and side == "Right":
            shear = fsum([reaction_a, *(-p.force for p in point_loads if p.position == 0)])
            moment = -fsum(m.moment for m in moments if m.position == 0)
        elif x == length and side == "Left":
            shear = fsum([-reaction_b, *(p.force for p in point_loads if p.position == length)])
            moment = fsum(m.moment for m in moments if m.position == length)
        else:
            shear_terms = [reaction_a]
            moment_terms = [reaction_a * x]
            for p in point_loads:
                if p.position < x or (side == "Right" and p.position == x):
                    shear_terms.append(-p.force)
                    moment_terms.append(-p.force * (x - p.position))
            for m in moments:
                if m.position < x or (side == "Right" and m.position == x):
                    moment_terms.append(-m.moment)
            for w, start, end in spans:
                covered = max(0.0, min(x, end) - start)
                force = w * covered
                shear_terms.append(-force)
                moment_terms.append(-force * (x - start - covered / 2))
            shear = fsum(shear_terms)
            moment = fsum(moment_terms)
        return BeamStation(x, shear, moment, side)

    breaks = {0.0, length, *(p.position for p in point_loads), *(m.position for m in moments)}
    for _, start, end in spans:
        breaks.update((start, end))
    cuts = sorted(breaks)
    boundary: dict[float, tuple[BeamStation, ...]] = {}
    for x in cuts:
        left = section(x, "Left") if x > 0 else BeamStation(x, 0.0, 0.0, "Left")
        right = section(x, "Right") if x < length else BeamStation(x, 0.0, 0.0, "Right")
        if (left.shear, left.moment) == (right.shear, right.moment):
            boundary[x] = (replace(right, side=None),)
        else:
            boundary[x] = (left, right)

    # Between breaks, shear is linear and dM/dx = V. Interpolate interior zeros
    # from the limits on that interval, then consider both sides of each jump.
    critical = set(cuts)
    for a, b in zip(cuts, cuts[1:]):
        va, vb = boundary[a][-1].shear, boundary[b][0].shear
        if va > 0 > vb or va < 0 < vb:
            critical.add(a + (b - a) * (va / (va - vb)))

    grid = tuple(length * (i / (samples - 1)) for i in range(samples))
    chart_stations = tuple(
        boundary[x][0 if x == length else -1] if x in boundary else section(x, "Right")
        for x in grid
    )
    values = {x: (replace(station, side=None),) for x, station in zip(grid, chart_stations)}
    values.update(boundary)
    for x in critical - breaks:
        values[x] = (replace(section(x, "Right"), side=None),)

    stations = tuple(station for x in sorted(values) for station in values[x])
    extrema = [station for x in sorted(critical) for station in values[x]]
    return BeamResult(
        length=length,
        point_loads=point_loads,
        udls=tuple(UniformLoad(*span) for span in spans),
        moments=moments,
        reaction_a=reaction_a,
        reaction_b=reaction_b,
        stations=stations,
        chart_stations=chart_stations,
        max_shear=max(extrema, key=lambda station: abs(station.shear)),
        max_moment=max(extrema, key=lambda station: abs(station.moment)),
        capacity=capacity,
    )
