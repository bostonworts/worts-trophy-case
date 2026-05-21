from app.db.models import CompetitionType


HIGH_PROFILE_TYPES = {
    CompetitionType.MCAB_QUALIFIER.value,
    CompetitionType.MCAB_FINALS.value,
    CompetitionType.NHC_QUALIFIER.value,
    CompetitionType.NHC_FINALS.value,
}


def competition_type_value(competition_type: CompetitionType | str) -> str:
    if isinstance(competition_type, CompetitionType):
        return competition_type.value
    return competition_type


def gives_leaderboard_points(competition_type: CompetitionType | str) -> bool:
    return competition_type_value(competition_type) != CompetitionType.CLUB_ONLY.value


def is_high_profile(competition_type: CompetitionType | str) -> bool:
    return competition_type_value(competition_type) in HIGH_PROFILE_TYPES


def describe_competition_type(competition_type: CompetitionType | str) -> str:
    words = competition_type_value(competition_type).replace("_", " ").split()
    if not words:
        return ""
    first, *rest = words
    if rest:
        return " ".join([first.upper(), *rest]).title().replace("Mcab", "MCAB").replace("Nhc", "NHC")
    return first.title()

