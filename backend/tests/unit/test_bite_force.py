"""The bite force fit reproduces the Wroe et al. 2005 table it is built from."""

import pytest

from app.research.bite_force import (
    EXPONENT,
    SCALE,
    WROE_2005_LIVING,
    average_carnivore_bite_n,
)


def test_the_table_has_the_31_living_species() -> None:
    assert len(WROE_2005_LIVING) == 31


def test_the_fit_over_the_31_table_rows_is_pinned() -> None:
    assert SCALE == pytest.approx(50.57, abs=0.01)
    assert EXPONENT == pytest.approx(0.6072, abs=0.0001)


@pytest.mark.parametrize(
    ("mass", "quotient", "table_force"),
    [(34.7, 136, 593), (128.8, 78, 751), (11.4, 109, 244)],
)
def test_scaled_by_quotient_it_reproduces_table_rows(
    mass: float, quotient: float, table_force: float
) -> None:
    assert average_carnivore_bite_n(mass) * quotient / 100 == pytest.approx(table_force, rel=0.02)


def test_every_living_species_is_within_16_percent() -> None:
    for mass, force, quotient in WROE_2005_LIVING:
        assert average_carnivore_bite_n(mass) * quotient / 100 == pytest.approx(force, rel=0.16)


def test_a_16_kg_carnivore_bites_about_272_n() -> None:
    assert round(average_carnivore_bite_n(16)) == 272


def test_mass_must_be_positive() -> None:
    with pytest.raises(ValueError):
        average_carnivore_bite_n(0)
