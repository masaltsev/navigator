"""Pydantic models for FPG (Presidential Grants Foundation) data.

Based on the official data passport (version 1.1):
https://президентскиегранты.рф/public/open-data

XLSX columns (17 total):
  0: Номер заявки       1: Конкурс            2: Организация
  3: ОГРН               4: ИНН                5: Регион
  6: Название проекта   7: Грантовое направление
  8: Запрошенная сумма   9: Общая сумма расходов
  10: Начало реализации  11: Окончание реализации
  12: Статус проекта     13: Дата решения о гранте
  14: Размер гранта      15: Оценка результатов
  16: Информация о нарушениях
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FPGProject(BaseModel):
    """One project entry from the FPG open data XLSX."""

    application_number: str = Field(description="Регистрационный номер заявки, e.g. '17-1-000383'")
    contest: str = Field(description="Конкурс, e.g. 'Первый конкурс 2017 г.'")
    organization_name: str = Field(description="Полное наименование организации-заявителя")
    ogrn: str = Field(default="", description="ОГРН организации (13 или 15 цифр)")
    inn: str = Field(default="", description="ИНН организации (10 или 12 цифр)")
    region: str = Field(description="Субъект РФ регистрации организации")
    project_title: str = Field(description="Название проекта")
    grant_direction: str = Field(description="Грантовое направление")
    budget_requested: Optional[float] = Field(default=None, description="Запрошенная сумма гранта, руб.")
    budget_total: Optional[float] = Field(default=None, description="Общая сумма расходов, руб.")
    start_date: Optional[date] = Field(default=None, description="Начало реализации проекта")
    end_date: Optional[date] = Field(default=None, description="Окончание реализации проекта")
    status: str = Field(description="Статус проекта")
    grant_decision_date: Optional[date] = Field(default=None, description="Дата решения о предоставлении гранта")
    grant_amount: Optional[float] = Field(default=None, description="Размер гранта, руб.")
    evaluation: Optional[str] = Field(default=None, description="Оценка результатов проекта")
    violations: Optional[str] = Field(default=None, description="Информация о допущенных нарушениях")

    @field_validator("ogrn", "inn", mode="before")
    @classmethod
    def coerce_to_str(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("start_date", "end_date", "grant_decision_date", mode="before")
    @classmethod
    def coerce_datetime_to_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        return None

    @property
    def is_winner(self) -> bool:
        return "победитель" in self.status.lower()

    @property
    def source_reference(self) -> str:
        return f"fpg_{self.application_number}"


class FPGOrganization(BaseModel):
    """Aggregated organization data from one or more FPG projects."""

    inn: str
    ogrn: str = ""
    name: str
    region: str
    projects: list[FPGProject] = Field(default_factory=list)

    @property
    def has_winning_project(self) -> bool:
        return any(p.is_winner for p in self.projects)

    @property
    def project_count(self) -> int:
        return len(self.projects)

    @property
    def best_project(self) -> FPGProject:
        """Return the most significant project (winner first, then by budget)."""
        winners = [p for p in self.projects if p.is_winner]
        if winners:
            return max(winners, key=lambda p: p.grant_amount or 0)
        return max(self.projects, key=lambda p: p.budget_requested or 0)

    @property
    def source_reference(self) -> str:
        return f"fpg_org_{self.inn}" if self.inn else f"fpg_org_{self.ogrn}"

    @property
    def all_directions(self) -> set[str]:
        return {p.grant_direction for p in self.projects}

    @property
    def all_project_titles(self) -> list[str]:
        return [p.project_title for p in self.projects]
