from datetime import datetime, timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pytest
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
BERLIN = ZoneInfo("Europe/Berlin")


# ---------------------------------------------------------------------------
# Home Assistant mocks
# ---------------------------------------------------------------------------

def as_datetime(value):
    if isinstance(value, datetime):
        return value

    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def as_local(value):
    """
    Approximate Home Assistant's as_local filter.

    Date-only / naive values are interpreted as local Berlin time.
    Aware datetimes are converted to Berlin time.
    """
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

# Home Assistant filter used by the template
env.filters["as_local"] = as_local
env.filters["regex_match"] = lambda value, pattern: (
    re.match(pattern, value or "") is not None
)

template = env.get_template("uebermorgen.jinja")


def render(value, now_value):
    """
    Render the real macro while mocking the small part of the
    Home Assistant template environment it depends on.
    """

    if now_value.tzinfo is None:
        now_value = now_value.replace(tzinfo=BERLIN)

    module = template.make_module({
        "states": lambda entity_id: value,
        "now": lambda: now_value,
        "as_datetime": as_datetime,
        "as_timestamp": as_timestamp,
        "timedelta": timedelta,
    })

    return module.uebermorgen("sensor.test").strip()


# ---------------------------------------------------------------------------
# Invalid / unavailable entity states
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        "unknown",
        "unavailable",
        "none",
        "",
    ],
)
def test_invalid_states(value):
    now_value = datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN)

    assert render(value, now_value) == "unbekannt"


# ---------------------------------------------------------------------------
# Date-only: vorgestern -> übermorgen
# ---------------------------------------------------------------------------

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
def test_relative_days_without_time(value, expected):
    now_value = datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN)

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# "gerade eben"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "now_value"),
    [
        (
            "2026-09-26T12:00:00+02:00",
            datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN),
        ),
        (
            "2026-09-26T11:59:00+02:00",
            datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN),
        ),
        (
            "2026-09-26T11:55:00+02:00",
            datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN),
        ),
        (
            "2026-09-26T11:50:00+02:00",
            datetime(2026, 9, 26, 12, 0, tzinfo=BERLIN),
        ),
    ],
)
def test_gerade_eben_up_to_10_minutes(value, now_value):
    assert render(value, now_value) == "gerade eben"


def test_gerade_eben_stops_after_10_minutes():
    now_value = datetime(
        2026, 9, 26, 12, 0, 1,
        tzinfo=BERLIN,
    )

    value = "2026-09-26T11:50:00+02:00"

    assert render(value, now_value) == "heute Vormittag"


def test_future_time_is_not_gerade_eben():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = "2026-09-26T12:05:00+02:00"

    assert render(value, now_value) == "heute Mittag"


# ---------------------------------------------------------------------------
# Time-of-day boundaries
#
# < 10:00  Morgen
# < 12:00  Vormittag
# < 14:30  Mittag
# < 17:00  Nachmittag
# < 22:00  Abend
# otherwise Nacht
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Morgen
        ("2026-09-26T00:00:00+02:00", "heute Morgen"),
        ("2026-09-26T09:59:59+02:00", "heute Morgen"),

        # Vormittag
        ("2026-09-26T10:00:00+02:00", "heute Vormittag"),
        ("2026-09-26T11:59:59+02:00", "heute Vormittag"),

        # Mittag
        ("2026-09-26T12:00:00+02:00", "heute Mittag"),
        ("2026-09-26T14:29:59+02:00", "heute Mittag"),

        # Nachmittag
        ("2026-09-26T14:30:00+02:00", "heute Nachmittag"),
        ("2026-09-26T16:59:59+02:00", "heute Nachmittag"),

        # Abend
        ("2026-09-26T17:00:00+02:00", "heute Abend"),
        ("2026-09-26T21:59:59+02:00", "heute Abend"),

        # Nacht
        ("2026-09-26T22:00:00+02:00", "heute Nacht"),
        ("2026-09-26T23:59:59+02:00", "heute Nacht"),
    ],
)
def test_time_of_day_boundaries(value, expected):
    # Late enough that none of the timestamps qualify as "gerade eben"
    now_value = datetime(
        2026, 9, 26, 11,
        tzinfo=BERLIN,
    )

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Time-of-day labels apply to vorgestern -> übermorgen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # vorgestern
        ("2026-09-24T08:00:00+02:00", "vorgestern Morgen"),
        ("2026-09-24T11:00:00+02:00", "vorgestern Vormittag"),
        ("2026-09-24T13:00:00+02:00", "vorgestern Mittag"),
        ("2026-09-24T15:00:00+02:00", "vorgestern Nachmittag"),
        ("2026-09-24T19:00:00+02:00", "vorgestern Abend"),
        ("2026-09-24T23:00:00+02:00", "vorgestern Nacht"),

        # gestern
        ("2026-09-25T08:00:00+02:00", "gestern Morgen"),
        ("2026-09-25T11:00:00+02:00", "gestern Vormittag"),
        ("2026-09-25T13:00:00+02:00", "gestern Mittag"),
        ("2026-09-25T15:00:00+02:00", "gestern Nachmittag"),
        ("2026-09-25T19:00:00+02:00", "gestern Abend"),
        ("2026-09-25T23:00:00+02:00", "gestern Nacht"),

        # heute
        ("2026-09-26T08:00:00+02:00", "heute Morgen"),
        ("2026-09-26T11:00:00+02:00", "heute Vormittag"),
        ("2026-09-26T13:00:00+02:00", "heute Mittag"),
        ("2026-09-26T15:00:00+02:00", "heute Nachmittag"),
        ("2026-09-26T19:00:00+02:00", "heute Abend"),
        ("2026-09-26T23:00:00+02:00", "heute Nacht"),

        # morgen
        ("2026-09-27T08:00:00+02:00", "morgen Morgen"),
        ("2026-09-27T11:00:00+02:00", "morgen Vormittag"),
        ("2026-09-27T13:00:00+02:00", "morgen Mittag"),
        ("2026-09-27T15:00:00+02:00", "morgen Nachmittag"),
        ("2026-09-27T19:00:00+02:00", "morgen Abend"),
        ("2026-09-27T23:00:00+02:00", "morgen Nacht"),

        # übermorgen
        ("2026-09-28T08:00:00+02:00", "übermorgen Morgen"),
        ("2026-09-28T11:00:00+02:00", "übermorgen Vormittag"),
        ("2026-09-28T13:00:00+02:00", "übermorgen Mittag"),
        ("2026-09-28T15:00:00+02:00", "übermorgen Nachmittag"),
        ("2026-09-28T19:00:00+02:00", "übermorgen Abend"),
        ("2026-09-28T23:00:00+02:00", "übermorgen Nacht"),
    ],
)
def test_time_periods_for_relative_days(value, expected):
    now_value = datetime(
        2026, 9, 26, 23, 59, 59,
        tzinfo=BERLIN,
    )

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Input datetime syntax
# ---------------------------------------------------------------------------

def test_datetime_with_space_instead_of_t():
    now_value = datetime(
        2026, 9, 26, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-09-26 19:00:00+02:00", now_value)
        == "heute Abend"
    )


def test_utc_datetime_is_converted_to_local_time():
    now_value = datetime(
        2026, 9, 26, 23, 0,
        tzinfo=BERLIN,
    )

    # 17:00 UTC = 19:00 Berlin
    assert (
        render("2026-09-26T17:00:00+00:00", now_value)
        == "heute Abend"
    )


def test_zulu_datetime_is_supported():
    now_value = datetime(
        2026, 9, 26, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-09-26T17:00:00Z", now_value)
        == "heute Abend"
    )


# ---------------------------------------------------------------------------
# Weekday wording
# Reference:
#
# today = Saturday 2026-09-26
# current week starts Monday 2026-09-21
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Current week, already passed
        ("2026-09-23", "diesen Mittwoch"),

        # Last calendar week
        ("2026-09-20", "letzten Sonntag"),

        # Two calendar weeks ago, while still < 14 days away
        ("2026-09-13", "vorletzten Sonntag"),

        # Next calendar week
        ("2026-10-02", "nächsten Freitag"),

        # Following calendar week, while still < 14 days away
        ("2026-10-05", "übernächsten Montag"),
    ],
)
def test_weekday_relative_wording(value, expected):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Week conversion boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (14, "in zwei Wochen"),
        (15, "in zwei Wochen"),
        (20, "in drei Wochen"),
        (21, "in drei Wochen"),
        (27, "in vier Wochen"),
        (28, "in vier Wochen"),
        (34, "in fünf Wochen"),
        (35, "in fünf Wochen"),
        (41, "in sechs Wochen"),
        (42, "in sechs Wochen"),

        (-14, "vor zwei Wochen"),
        (-15, "vor zwei Wochen"),
        (-20, "vor drei Wochen"),
        (-21, "vor drei Wochen"),
        (-27, "vor vier Wochen"),
        (-28, "vor vier Wochen"),
        (-34, "vor fünf Wochen"),
        (-35, "vor fünf Wochen"),
        (-41, "vor sechs Wochen"),
        (-42, "vor sechs Wochen"),
    ],
)
def test_week_ranges(days, expected):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (now_value.date() + timedelta(days=days)).isoformat()

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Exact transition between weekday wording and weeks
# ---------------------------------------------------------------------------

def test_13_days_does_not_use_weeks():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    assert render("2026-10-09", now_value) == "übernächsten Freitag"


def test_14_days_uses_weeks():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    assert render("2026-10-10", now_value) == "in zwei Wochen"


def test_minus_13_days_does_not_use_weeks():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    assert render("2026-09-13", now_value) == "vorletzten Sonntag"


def test_minus_14_days_uses_weeks():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() - timedelta(days=14)
    ).isoformat()

    assert render(value, now_value) == "vor zwei Wochen"


# ---------------------------------------------------------------------------
# Month conversion
#
# Current implementation switches to months when abs(days) > 42
# and approximates a month as 30.44 days.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (43, "in einem Monat"),
        (45, "in einem Monat"),
        (46, "in zwei Monaten"),
        (60, "in zwei Monaten"),
        (90, "in drei Monaten"),
        (120, "in vier Monaten"),
        (180, "in sechs Monaten"),
        (365, "in zwölf Monaten"),
        (548, "in achtzehn Monaten"),

        (-43, "vor einem Monat"),
        (-45, "vor einem Monat"),
        (-46, "vor zwei Monaten"),
        (-60, "vor zwei Monaten"),
        (-90, "vor drei Monaten"),
        (-120, "vor vier Monaten"),
        (-180, "vor sechs Monaten"),
        (-365, "vor zwölf Monaten"),
        (-548, "vor achtzehn Monaten"),
    ],
)
def test_month_ranges(days, expected):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=days)
    ).isoformat()

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Exact week -> month transition
# ---------------------------------------------------------------------------

def test_42_days_is_still_weeks():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=42)
    ).isoformat()

    assert render(value, now_value) == "in sechs Wochen"


def test_43_days_switches_to_months():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=43)
    ).isoformat()

    assert render(value, now_value) == "in einem Monat"


# ---------------------------------------------------------------------------
# Year conversion
#
# Current implementation:
#   abs_days > 548
#   years = round(abs_days / 365.25)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (549, "in zwei Jahren"),
        (730, "in zwei Jahren"),
        (900, "in zwei Jahren"),
        (1000, "in drei Jahren"),
        (1096, "in drei Jahren"),

        (-549, "vor zwei Jahren"),
        (-730, "vor zwei Jahren"),
        (-900, "vor zwei Jahren"),
        (-1000, "vor drei Jahren"),
        (-1096, "vor drei Jahren"),
    ],
)
def test_year_ranges(days, expected):
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=days)
    ).isoformat()

    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Exact month -> year transition
# ---------------------------------------------------------------------------

def test_548_days_is_still_months():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=548)
    ).isoformat()

    assert render(value, now_value) == "in achtzehn Monaten"


def test_549_days_switches_to_years():
    now_value = datetime(
        2026, 9, 26, 12, 0,
        tzinfo=BERLIN,
    )

    value = (
        now_value.date() + timedelta(days=549)
    ).isoformat()

    assert render(value, now_value) == "in zwei Jahren"


# ---------------------------------------------------------------------------
# Year boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("now_value", "value", "expected"),
    [
        (
            datetime(2026, 12, 31, 12, 0, tzinfo=BERLIN),
            "2027-01-01",
            "morgen",
        ),
        (
            datetime(2027, 1, 1, 12, 0, tzinfo=BERLIN),
            "2026-12-31",
            "gestern",
        ),
        (
            datetime(2026, 12, 31, 12, 0, tzinfo=BERLIN),
            "2027-01-02",
            "übermorgen",
        ),
    ],
)
def test_calendar_year_boundaries(now_value, value, expected):
    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# Leap year
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("now_value", "value", "expected"),
    [
        (
            datetime(2028, 2, 28, 12, 0, tzinfo=BERLIN),
            "2028-02-29",
            "morgen",
        ),
        (
            datetime(2028, 2, 29, 12, 0, tzinfo=BERLIN),
            "2028-02-28",
            "gestern",
        ),
        (
            datetime(2028, 2, 29, 12, 0, tzinfo=BERLIN),
            "2028-03-01",
            "morgen",
        ),
    ],
)
def test_leap_year(now_value, value, expected):
    assert render(value, now_value) == expected


# ---------------------------------------------------------------------------
# DST changes in Germany
# ---------------------------------------------------------------------------

def test_summer_time_date():
    now_value = datetime(
        2026, 7, 15, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-07-15T19:00:00+02:00", now_value)
        == "heute Abend"
    )


def test_winter_time_date():
    now_value = datetime(
        2026, 12, 15, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-12-15T19:00:00+01:00", now_value)
        == "heute Abend"
    )


def test_dst_start_day():
    # Germany switches to CEST on 2026-03-29.
    now_value = datetime(
        2026, 3, 29, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-03-29T08:00:00+02:00", now_value)
        == "heute Morgen"
    )


def test_dst_end_day():
    # Germany switches back to CET on 2026-10-25.
    now_value = datetime(
        2026, 10, 25, 23, 0,
        tzinfo=BERLIN,
    )

    assert (
        render("2026-10-25T19:00:00+01:00", now_value)
        == "heute Abend"
    )