from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

import pytest
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]

env = Environment(
    loader=FileSystemLoader(ROOT),
    extensions=["jinja2.ext.do"],
)

env.filters["as_local"] = lambda value: value
env.filters["regex_match"] = lambda value, pattern: (
    re.match(pattern, value or "") is not None
)

template = env.get_template("uebermorgen.jinja")


def render(value, now_value):
    module = template.make_module({
        "states": lambda entity_id: value,
        "now": lambda: now_value,
        "as_datetime": lambda value: datetime.fromisoformat(value),
        "as_local": lambda value: value,
        "as_timestamp": lambda value: value.timestamp(),
        "timedelta": timedelta,
    })

    return module.uebermorgen("sensor.test").strip()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-09-24", "vorgestern"),
        ("2026-09-25", "gestern"),
        ("2026-09-26", "heute"),
        ("2026-09-27", "morgen"),
        ("2026-09-28", "übermorgen"),
    ],
)
def test_relative_days(value, expected):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=timezone.utc,
    )

    assert render(value, now_value) == expected