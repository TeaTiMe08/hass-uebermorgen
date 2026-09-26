from datetime import datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pytest
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
BERLIN = ZoneInfo("Europe/Berlin")


def as_datetime(value, default=None):
    if isinstance(value, datetime):
        return value

    try:
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except (ValueError, TypeError, AttributeError):
        return default


def as_local(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=BERLIN)

    return value.astimezone(BERLIN)


def as_timestamp(value):
    if isinstance(value, str):
        value = as_local(as_datetime(value))

    return value.timestamp()


env = Environment(
    loader=FileSystemLoader(ROOT)
)

env.filters["as_local"] = as_local
env.filters["regex_match"] = lambda value, pattern: (
    re.match(pattern, value or "") is not None
)

template = env.get_template("uebermorgen.jinja")


def render(value):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    module = template.make_module({
        "states": lambda entity_id: value,
        "now": lambda: now_value,
        "as_datetime": as_datetime,
        "as_timestamp": as_timestamp,
        "timedelta": timedelta,
    })

    return module.uebermorgen("sensor.test").strip()


# ---------------------------------------------------------------------------
# Valid date formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-09-26",
        "2026-01-01",
        "2026-12-31",
        "2028-02-29",
    ],
)
def test_valid_date_formats(value):
    assert render(value) != "unbekannt"


# ---------------------------------------------------------------------------
# Valid datetime formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-09-26T08:30",
        "2026-09-26T08:30:00",
        "2026-09-26T08:30:00.123",
        "2026-09-26 08:30",
        "2026-09-26 08:30:00",
        "2026-09-26T08:30:00+02:00",
        "2026-09-26T08:30:00+01:00",
        "2026-09-26T06:30:00Z",
        "2026-09-26T06:30:00+00:00",
    ],
)
def test_valid_datetime_formats(value):
    assert render(value) != "unbekannt"


# ---------------------------------------------------------------------------
# Home Assistant invalid states
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "",
        "unknown",
        "unavailable",
        "none",
    ],
)
def test_home_assistant_invalid_states(value):
    assert render(value) == "unbekannt"


# ---------------------------------------------------------------------------
# Obviously invalid formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "hello",
        "foo-bar",
        "123",
        "26.09.2026",
        "26/09/2026",
        "09/26/2026",
        "2026/09/26",
        "20260926",
        "2026-9-26",
        "2026-09-2",
        "26-09-2026",
        "sensor.foo",
        "true",
        "false",
        "null",
        "None",
        "NaN",
    ],
)
def test_invalid_formats(value):
    assert render(value) == "falsches_format"


# ---------------------------------------------------------------------------
# Invalid times
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-09-26T24:00",
        "2026-09-26T25:00",
        "2026-09-26T12:60",
        "2026-09-26T12:30:60",
        "2026-09-26T99:99",
        "2026-09-26 24:00",
        "2026-09-26T12",
        "2026-09-26T12:",
        "2026-09-26T12:3",
    ],
)
def test_invalid_times(value):
    assert render(value) == "falsches_format"


# ---------------------------------------------------------------------------
# Invalid date syntax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-00-01",
        "2026-13-01",
        "2026-01-00",
        "2026-01-32",
        "0000-01-01",
    ],
)
def test_invalid_date_syntax(value):
    assert render(value) == "falsches_format"


# ---------------------------------------------------------------------------
# Calendar-invalid dates
#
# These are structurally valid, but must still be rejected by as_datetime().
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-02-29",
        "2026-02-30",
        "2026-02-31",
        "2026-04-31",
        "2026-06-31",
        "2026-09-31",
        "2026-11-31",
    ],
)
def test_calendar_invalid_dates(value):
    assert render(value) == "falsches_format"


# ---------------------------------------------------------------------------
# Valid leap year
# ---------------------------------------------------------------------------

def test_valid_leap_day():
    assert render("2028-02-29") != "falsches_format"


# ---------------------------------------------------------------------------
# Broken timezone syntax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "2026-09-26T12:00+2:00",
        "2026-09-26T12:00+0200",
        "2026-09-26T12:00+25:00",
        "2026-09-26T12:00+02:60",
        "2026-09-26T12:00Z+02:00",
    ],
)
def test_invalid_timezone_formats(value):
    assert render(value) == "falsches_format"


# ---------------------------------------------------------------------------
# Whitespace / junk around otherwise valid dates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        " 2026-09-26",
        "2026-09-26 ",
        "\t2026-09-26",
        "2026-09-26\n",
        "abc2026-09-26",
        "2026-09-26abc",
    ],
)
def test_rejects_surrounding_junk(value):
    assert render(value) == "falsches_format"