import pytest

from game.settings import Settings
from game.squadrons.pilotnameformat import format_pilot_name


@pytest.mark.parametrize(
    "original, expected",
    [
        ("Иван Петров", "Ivan Petrov"),
        ("张琴", "Zhang Qin"),
        ("山田 太郎", "Yamada Taro"),
        ("José Đặng", "José Đặng"),
        ("Jose\u0301-Петров", "Jose\u0301-Petrov"),
    ],
)
def test_pilot_name_spelling_is_opt_in(original: str, expected: str) -> None:
    settings = Settings()
    assert format_pilot_name(original, settings) == original
    settings.latin_pilot_names = True
    assert format_pilot_name(original, settings) == expected
