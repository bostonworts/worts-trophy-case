from datetime import date
from decimal import Decimal

from app.db.models import CompetitionType, PlacementScope
from app.domain.competition_types import describe_competition_type
from app.domain.scoring import LeaderboardSettings, leaderboard_points
from app.domain.seasons import Season
from app.services.display import humanize_label


def test_season_starts_on_july_first() -> None:
    assert Season.for_date(date(2026, 6, 30)).label == "2025-2026"
    assert Season.for_date(date(2026, 7, 1)).label == "2026-2027"


def test_season_contains_dates_until_next_july() -> None:
    season = Season(2025, 2026)

    assert season.contains_date(date(2025, 7, 1))
    assert season.contains_date(date(2026, 6, 30))
    assert not season.contains_date(date(2026, 7, 1))


def test_leaderboard_points_match_worts_rules() -> None:
    assert leaderboard_points(
        place=1,
        placement_scope=PlacementScope.CATEGORY,
        competition_type=CompetitionType.BJCP_SANCTIONED,
    ) == Decimal("3")
    assert leaderboard_points(
        place=2,
        placement_scope=PlacementScope.BEST_OF_SHOW,
        competition_type=CompetitionType.NHC_QUALIFIER,
    ) == Decimal("4.5")
    assert leaderboard_points(
        place=1,
        placement_scope=PlacementScope.CATEGORY,
        competition_type=CompetitionType.CLUB_ONLY,
    ) == Decimal("0")


def test_leaderboard_points_can_use_custom_settings() -> None:
    settings = LeaderboardSettings(
        placement_points={1: Decimal("10"), 2: Decimal("5"), 3: Decimal("2"), 4: Decimal("1")},
        best_of_show_multiplier=Decimal("3"),
        high_profile_bonus=Decimal("0"),
        minimum_bjcp_score=Decimal("40"),
        competition_type_weights={CompetitionType.BJCP_SANCTIONED.value: Decimal("1.5")},
    )

    assert leaderboard_points(
        place=1,
        placement_scope=PlacementScope.CATEGORY,
        competition_type=CompetitionType.BJCP_SANCTIONED,
        bjcp_score=Decimal("41"),
        settings=settings,
    ) == Decimal("15.0")
    assert leaderboard_points(
        place=1,
        placement_scope=PlacementScope.CATEGORY,
        competition_type=CompetitionType.BJCP_SANCTIONED,
        bjcp_score=Decimal("39"),
        settings=settings,
    ) == Decimal("0")


def test_season_can_use_custom_start_date() -> None:
    assert Season.for_date(date(2026, 4, 30), start_month=5, start_day=1).label == "2025-2026"
    assert Season.for_date(date(2026, 5, 1), start_month=5, start_day=1).label == "2026-2027"


def test_display_labels_preserve_acronyms_and_special_casing() -> None:
    assert describe_competition_type(CompetitionType.BJCP_SANCTIONED) == "BJCP Sanctioned"
    assert describe_competition_type(CompetitionType.NHC_QUALIFIER) == "NHC Qualifier"
    assert describe_competition_type(CompetitionType.MCAB_FINALS) == "MCAB Finals"
    assert humanize_label(PlacementScope.BEST_OF_SHOW) == "Best of Show"
    assert humanize_label("paypal") == "PayPal"
