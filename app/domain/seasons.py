from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import date


STARTING_MONTH = 7
STARTING_DAY = 1


@dataclass(frozen=True, order=True)
class Season:
    start_year: int
    end_year: int
    start_month: int = field(default=STARTING_MONTH, compare=False)
    start_day: int = field(default=STARTING_DAY, compare=False)

    @classmethod
    def current(
        cls,
        today: date | None = None,
        *,
        start_month: int = STARTING_MONTH,
        start_day: int = STARTING_DAY,
    ) -> Season:
        return cls.for_date(
            today or date.today(),
            start_month=start_month,
            start_day=start_day,
        )

    @classmethod
    def for_date(
        cls,
        value: date,
        *,
        start_month: int = STARTING_MONTH,
        start_day: int = STARTING_DAY,
    ) -> Season:
        season_start = date(value.year, start_month, start_day)
        if value < season_start:
            return cls(value.year - 1, value.year, start_month, start_day)
        return cls(value.year, value.year + 1, start_month, start_day)

    @classmethod
    def from_param(
        cls,
        value: str,
        *,
        start_month: int = STARTING_MONTH,
        start_day: int = STARTING_DAY,
    ) -> Season:
        start_year, end_year = value.split("-", maxsplit=1)
        return cls(int(start_year), int(end_year), start_month, start_day)

    @property
    def label(self) -> str:
        return f"{self.start_year}-{self.end_year}"

    @property
    def start_date(self) -> date:
        return date(self.start_year, self.start_month, self.start_day)

    @property
    def end_boundary(self) -> date:
        return date(self.end_year, self.start_month, self.start_day)

    def contains_date(self, value: date) -> bool:
        return self.start_date <= value < self.end_boundary
