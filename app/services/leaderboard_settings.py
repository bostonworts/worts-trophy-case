from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, CompetitionType
from app.domain.scoring import (
    DEFAULT_COMPETITION_TYPE_WEIGHTS,
    LeaderboardSettings,
)
from app.services.display import humanize_label


SETTING_PREFIX = "leaderboard."


def load_leaderboard_settings(db: Session) -> LeaderboardSettings:
    values = {
        setting.key: setting.value
        for setting in db.scalars(
            select(AppSetting).where(AppSetting.key.startswith(SETTING_PREFIX))
        ).all()
    }
    defaults = LeaderboardSettings()
    return LeaderboardSettings(
        season_start_month=parse_int(
            values.get("leaderboard.season_start_month"),
            defaults.season_start_month,
        ),
        season_start_day=parse_int(
            values.get("leaderboard.season_start_day"),
            defaults.season_start_day,
        ),
        placement_points={
            place: parse_decimal(
                values.get(f"leaderboard.place_{place}_points"),
                defaults.placement_points[place],
            )
            for place in range(1, 5)
        },
        best_of_show_multiplier=parse_decimal(
            values.get("leaderboard.best_of_show_multiplier"),
            defaults.best_of_show_multiplier,
        ),
        high_profile_bonus=parse_decimal(
            values.get("leaderboard.high_profile_bonus"),
            defaults.high_profile_bonus,
        ),
        minimum_bjcp_score=parse_optional_decimal(
            values.get("leaderboard.minimum_bjcp_score")
        ),
        competition_type_weights={
            competition_type.value: parse_decimal(
                values.get(f"leaderboard.weight.{competition_type.value}"),
                DEFAULT_COMPETITION_TYPE_WEIGHTS.get(competition_type.value, Decimal("1")),
            )
            for competition_type in CompetitionType
        },
    )


def save_leaderboard_settings(db: Session, settings: LeaderboardSettings) -> None:
    values = {
        "leaderboard.season_start_month": str(settings.season_start_month),
        "leaderboard.season_start_day": str(settings.season_start_day),
        "leaderboard.best_of_show_multiplier": str(settings.best_of_show_multiplier),
        "leaderboard.high_profile_bonus": str(settings.high_profile_bonus),
        "leaderboard.minimum_bjcp_score": (
            str(settings.minimum_bjcp_score)
            if settings.minimum_bjcp_score is not None
            else ""
        ),
    }
    for place, points in settings.placement_points.items():
        values[f"leaderboard.place_{place}_points"] = str(points)
    for competition_type, weight in settings.competition_type_weights.items():
        values[f"leaderboard.weight.{competition_type}"] = str(weight)

    for key, value in values.items():
        setting = db.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
        else:
            setting.value = value


def validate_leaderboard_settings_form(
    form: dict[str, str],
) -> tuple[LeaderboardSettings, list[str]]:
    errors = []
    season_start_month = parse_form_int(
        form,
        "season_start_month",
        "Season start month",
        errors,
        minimum=1,
        maximum=12,
    )
    season_start_day = parse_form_int(
        form,
        "season_start_day",
        "Season start day",
        errors,
        minimum=1,
        maximum=31,
    )
    if season_start_month is not None and season_start_day is not None:
        try:
            date(2026, season_start_month, season_start_day)
        except ValueError:
            errors.append("Season start month and day must make a valid date.")

    placement_points = {}
    for place in range(1, 5):
        value = parse_form_decimal(
            form,
            f"place_{place}_points",
            f"{place_label(place)} place points",
            errors,
        )
        placement_points[place] = value or Decimal("0")

    best_of_show_multiplier = parse_form_decimal(
        form,
        "best_of_show_multiplier",
        "Best of show multiplier",
        errors,
    )
    high_profile_bonus = parse_form_decimal(
        form,
        "high_profile_bonus",
        "High profile bonus",
        errors,
    )
    minimum_bjcp_score = parse_form_optional_decimal(
        form,
        "minimum_bjcp_score",
        "Minimum BJCP score",
        errors,
        maximum=Decimal("50"),
    )

    competition_type_weights = {}
    for competition_type in CompetitionType:
        value = parse_form_decimal(
            form,
            f"weight_{competition_type.value}",
            f"{humanize_label(competition_type)} weight",
            errors,
        )
        competition_type_weights[competition_type.value] = value or Decimal("0")

    settings = LeaderboardSettings(
        season_start_month=season_start_month or 7,
        season_start_day=season_start_day or 1,
        placement_points=placement_points,
        best_of_show_multiplier=best_of_show_multiplier or Decimal("0"),
        high_profile_bonus=high_profile_bonus or Decimal("0"),
        minimum_bjcp_score=minimum_bjcp_score,
        competition_type_weights=competition_type_weights,
    )
    return settings, errors


def leaderboard_settings_form(settings: LeaderboardSettings) -> dict[str, str]:
    form = {
        "season_start_month": str(settings.season_start_month),
        "season_start_day": str(settings.season_start_day),
        "best_of_show_multiplier": str(settings.best_of_show_multiplier),
        "high_profile_bonus": str(settings.high_profile_bonus),
        "minimum_bjcp_score": (
            str(settings.minimum_bjcp_score)
            if settings.minimum_bjcp_score is not None
            else ""
        ),
    }
    for place, points in settings.placement_points.items():
        form[f"place_{place}_points"] = str(points)
    for competition_type in CompetitionType:
        form[f"weight_{competition_type.value}"] = str(
            settings.competition_type_weights.get(competition_type.value, Decimal("1"))
        )
    return form


def parse_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return default


def parse_decimal(value: str | None, default: Decimal) -> Decimal:
    try:
        return Decimal((value or "").strip())
    except InvalidOperation:
        return default


def parse_optional_decimal(value: str | None) -> Decimal | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_form_int(
    form: dict[str, str],
    field_name: str,
    label: str,
    errors: list[str],
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    value = (form.get(field_name) or "").strip()
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if parsed < minimum or parsed > maximum:
        errors.append(f"{label} must be between {minimum} and {maximum}.")
    return parsed


def parse_form_decimal(
    form: dict[str, str],
    field_name: str,
    label: str,
    errors: list[str],
) -> Decimal | None:
    value = (form.get(field_name) or "").strip()
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{label} must be a number.")
        return None
    if parsed < 0:
        errors.append(f"{label} must be zero or greater.")
    return parsed


def parse_form_optional_decimal(
    form: dict[str, str],
    field_name: str,
    label: str,
    errors: list[str],
    *,
    maximum: Decimal,
) -> Decimal | None:
    value = (form.get(field_name) or "").strip()
    if not value:
        return None
    parsed = parse_form_decimal(form, field_name, label, errors)
    if parsed is not None and parsed > maximum:
        errors.append(f"{label} must be no more than {maximum}.")
    return parsed


def place_label(place: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "HM"}[place]
