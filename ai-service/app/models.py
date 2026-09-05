from datetime import timedelta
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Severity(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Category(StrEnum):
    NETWORK = "NETWORK"
    SERVER = "SERVER"
    APPLICATION = "APPLICATION"


class Status(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class IncidentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_time: AwareDatetime = Field(alias="from")
    to_time: AwareDatetime = Field(alias="to")
    severity: Severity | None = None
    category: Category | None = None
    status: Status | None = None
    page: int = Field(default=0, ge=0, le=100000)
    size: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_range(self) -> "IncidentQuery":
        span = self.to_time - self.from_time
        if not timedelta(0) < span <= timedelta(days=366):
            raise ValueError("조회 기간은 0일 초과 366일 이하여야 합니다.")
        return self


class Incident(BaseModel):
    id: str
    category: Category
    severity: Severity
    status: Status
    occurred_at: AwareDatetime
    cause: str
    version: int


class IncidentPage(BaseModel):
    items: list[Incident]
    page: int
    size: int
    total: int = Field(ge=0)
