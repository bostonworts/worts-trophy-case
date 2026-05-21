from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models import CompetitionType, PlacementScope
from app.domain.competition_types import is_high_profile


BASE_POINTS = {
    1: Decimal("3"),
    2: Decimal("2"),
    3: Decimal("1"),
    4: Decimal("0.5"),
}

DEFAULT_COMPETITION_TYPE_WEIGHTS = {
    CompetitionType.BJCP_SANCTIONED.value: Decimal("1"),
    CompetitionType.MCAB_QUALIFIER.value: Decimal("1"),
    CompetitionType.MCAB_FINALS.value: Decimal("1"),
    CompetitionType.NHC_QUALIFIER.value: Decimal("1"),
    CompetitionType.NHC_FINALS.value: Decimal("1"),
    CompetitionType.OTHER.value: Decimal("1"),
    CompetitionType.CLUB_ONLY.value: Decimal("0"),
}


@dataclass(frozen=True)
class LeaderboardSettings:
    season_start_month: int = 7
    season_start_day: int = 1
    placement_points: dict[int, Decimal] = field(default_factory=lambda: dict(BASE_POINTS))
    best_of_show_multiplier: Decimal = Decimal("2")
    high_profile_bonus: Decimal = Decimal("0.5")
    minimum_bjcp_score: Decimal | None = None
    competition_type_weights: dict[str, Decimal] = field(
        default_factory=lambda: dict(DEFAULT_COMPETITION_TYPE_WEIGHTS)
    )


@dataclass(frozen=True)
class LeaderboardBreakdown:
    total: Decimal
    base_points: Decimal
    placement_multiplier: Decimal
    high_profile_bonus: Decimal
    competition_weight: Decimal
    eligible: bool
    reason: str


def placement_scope_value(placement_scope: PlacementScope | str | None) -> str | None:
    if placement_scope is None:
        return None
    if isinstance(placement_scope, PlacementScope):
        return placement_scope.value
    return placement_scope


def leaderboard_points(
    *,
    place: int | None,
    placement_scope: PlacementScope | str | None,
    competition_type: CompetitionType | str,
    bjcp_score: Decimal | None = None,
    settings: LeaderboardSettings | None = None,
) -> Decimal:
    return leaderboard_breakdown(
        place=place,
        placement_scope=placement_scope,
        competition_type=competition_type,
        bjcp_score=bjcp_score,
        settings=settings,
    ).total


def leaderboard_breakdown(
    *,
    place: int | None,
    placement_scope: PlacementScope | str | None,
    competition_type: CompetitionType | str,
    bjcp_score: Decimal | None = None,
    settings: LeaderboardSettings | None = None,
) -> LeaderboardBreakdown:
    settings = settings or LeaderboardSettings()
    if place is None or placement_scope is None:
        return empty_breakdown("No placement recorded.")
    if (
        settings.minimum_bjcp_score is not None
        and (bjcp_score is None or bjcp_score < settings.minimum_bjcp_score)
    ):
        return empty_breakdown("Below the minimum BJCP score for leaderboard points.")

    competition_type_value = (
        competition_type.value
        if isinstance(competition_type, CompetitionType)
        else competition_type
    )
    weight = settings.competition_type_weights.get(competition_type_value, Decimal("1"))
    if weight <= 0:
        return empty_breakdown("Competition type has zero leaderboard weight.")

    base = settings.placement_points.get(place)
    if base is None:
        return empty_breakdown("Placement does not have configured points.")

    multiplier = (
        settings.best_of_show_multiplier
        if placement_scope_value(placement_scope) == "best_of_show"
        else Decimal("1")
    )
    bonus = settings.high_profile_bonus if is_high_profile(competition_type) else Decimal("0")
    return LeaderboardBreakdown(
        total=((base * multiplier) + bonus) * weight,
        base_points=base,
        placement_multiplier=multiplier,
        high_profile_bonus=bonus,
        competition_weight=weight,
        eligible=True,
        reason="Eligible placement.",
    )


def empty_breakdown(reason: str) -> LeaderboardBreakdown:
    return LeaderboardBreakdown(
        total=Decimal("0"),
        base_points=Decimal("0"),
        placement_multiplier=Decimal("0"),
        high_profile_bonus=Decimal("0"),
        competition_weight=Decimal("0"),
        eligible=False,
        reason=reason,
    )
