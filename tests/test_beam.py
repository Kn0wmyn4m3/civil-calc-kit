import pytest

from civil_calc import AppliedMoment, PointLoad, SectionCapacity, UniformLoad, analyze_beam


def test_center_point_load_matches_textbook():
    length, force = 7.0, 28.0
    result = analyze_beam(length, point_loads=[PointLoad(force, length / 2)], samples=2)
    assert result.reaction_a == result.reaction_b == force / 2
    assert result.max_moment.moment == force * length / 4
    assert result.max_moment.x == length / 2
    limits = [station for station in result.stations if station.x == length / 2]
    assert [(s.side, s.shear, s.moment) for s in limits] == [
        ("Left", force / 2, force * length / 4), ("Right", -force / 2, force * length / 4)
    ]


def test_full_span_udl_has_exact_peak_even_with_two_samples():
    length, intensity = 9.0, 15.0
    result = analyze_beam(length, udls=[UniformLoad(intensity)], samples=2)
    assert result.reaction_a == result.reaction_b == intensity * length / 2
    assert result.max_moment.moment == pytest.approx(intensity * length**2 / 8)
    assert result.max_moment.x == length / 2
    assert result.max_moment.shear == pytest.approx(0)
    assert len(result.chart_stations) == 2
    assert result.udls[0].end == length


def test_partial_udl_and_interior_zero_shear():
    result = analyze_beam(10, udls=[UniformLoad(6, 2, 6)], samples=2)
    assert (result.reaction_a, result.reaction_b) == pytest.approx((14.4, 9.6))
    assert result.max_moment.x == pytest.approx(4.4)
    assert result.max_moment.moment == pytest.approx(46.08)
    assert {2, 6} <= {station.x for station in result.stations}


def test_overlapping_udls():
    result = analyze_beam(10, udls=[UniformLoad(4), UniformLoad(6, 2, 6)], samples=2)
    x = 4.64
    assert result.max_moment.x == pytest.approx(x)
    assert result.max_moment.moment == pytest.approx(34.4 * x - 2 * x**2 - 3 * (x - 2)**2)


def test_off_center_load_reports_signed_governing_shear():
    result = analyze_beam(8, point_loads=[PointLoad(32, 6)])
    assert result.max_shear.shear == -24
    assert result.max_shear.x == 6
    assert result.max_shear.side == "Right"
    assert result.max_moment.moment == 48


def test_concentrated_couple_creates_a_moment_jump():
    result = analyze_beam(8, moments=[AppliedMoment(24, 3)], samples=2)
    assert (result.reaction_a, result.reaction_b) == (3, -3)
    before, after = [s for s in result.stations if s.x == 3]
    assert before.shear == after.shear == 3
    assert (before.moment, after.moment) == (9, -15)
    assert result.max_moment == after


def test_mixed_loads_satisfy_force_and_moment_equilibrium():
    length = 8.0
    result = analyze_beam(
        length, point_loads=[PointLoad(31, 1.25), PointLoad(-9, 7.25)],
        udls=[UniformLoad(6, 2, 5), UniformLoad(2)],
        moments=[AppliedMoment(18, 3), AppliedMoment(-5, 7)],
    )
    assert result.reaction_a + result.reaction_b - 31 + 9 - 18 - 16 == pytest.approx(0)
    moment_about_a = result.reaction_b * length - 31 * 1.25 + 9 * 7.25 - 18 * 3.5 - 16 * 4 + 18 - 5
    assert moment_about_a == pytest.approx(0)
    assert result.stations[0].moment == result.stations[-1].moment == 0


def test_point_loads_directly_over_supports_do_not_load_the_span():
    result = analyze_beam(6, point_loads=[PointLoad(5, 0), PointLoad(7, 6)])
    assert (result.reaction_a, result.reaction_b) == (5, 7)
    assert result.max_shear.shear == result.max_moment.moment == 0


@pytest.mark.parametrize(("position", "side", "peak"), [(0, "Right", -18), (6, "Left", 18)])
def test_end_couples_keep_the_internal_moment_limit(position, side, peak):
    result = analyze_beam(6, moments=[AppliedMoment(18, position)])
    assert (result.max_moment.x, result.max_moment.side, result.max_moment.moment) == (position, side, peak)


def test_capacity_ratios_use_absolute_peak_and_are_optional():
    result = analyze_beam(
        8, point_loads=[PointLoad(-32, 6)], capacity=SectionCapacity(shear=20, moment=60),
    )
    assert result.max_moment.moment == -48
    assert result.shear_utilization == pytest.approx(1.2)
    assert result.moment_utilization == pytest.approx(0.8)
    empty = analyze_beam(8)
    assert empty.shear_utilization is None and empty.moment_utilization is None


@pytest.mark.parametrize(("length", "kwargs", "error"), [
    (float("nan"), {}, "Beam length"),
    (0, {}, "Beam length"),
    (6, {"point_loads": [PointLoad(1, 7)]}, "Point loads"),
    (6, {"udls": [UniformLoad(1, 3, 3)]}, "UDLs"),
    (6, {"moments": [AppliedMoment(float("inf"), 2)]}, "Applied moments"),
    (6, {"capacity": SectionCapacity(shear=0)}, "Shear capacity"),
    (6, {"samples": 1}, "Samples"),
])
def test_invalid_beam_inputs(length, kwargs, error):
    with pytest.raises(ValueError, match=error):
        analyze_beam(length, **kwargs)
