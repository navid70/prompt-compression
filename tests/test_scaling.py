import pytest

from benchmarks.scaling import profile


@pytest.mark.parametrize(
    ("repetitions", "warmups"), [(0, 0), (True, 0), (1.5, 0), (1, -1), (1, False)]
)
def test_scaling_rejects_invalid_timing_configuration(repetitions, warmups):
    with pytest.raises(ValueError, match="timing"):
        profile(repetitions=repetitions, warmups=warmups)
