#장애 데이터 형식 정의
from datetime import timedelta
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

#Enum으로 허용값 제한 -> StrEnum은 문자열로 표현되는 열겨형
class Severity(StrEnum): #장애 심각도를 P1, P2, P3 중 하나로 제한
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Category(StrEnum): #장애 유형 : 네트워크, 서버, 애플리케이션
    NETWORK = "NETWORK"
    SERVER = "SERVER"
    APPLICATION = "APPLICATION"


class Status(StrEnum): #장애 처리 상태 : 미해결, 진행 중, 해결 완료
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"

#장애 조회 조건 (사용자가 장애 목록을 조회할 때, 전달하는 조건을 정의)
#AwareDatetime : 시간대 정보가 포함된 날짜와 시간을 요구
class IncidentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_time: AwareDatetime = Field(alias="from")
    to_time: AwareDatetime = Field(alias="to")
    severity: Severity | None = None
    category: Category | None = None
    status: Status | None = None
    page: int = Field(default=0, ge=0, le=100000)
    size: int = Field(default=20, ge=1, le=50) #기본 조회 건수 20건, 최소 1건, 최대 50건

    #날짜 범위 검증 (두 날짜가 각각 유효한지뿐 아니라, 날짜 사이의 관계가 올바른지 확인)
    #즉, 시작일보다 종료일이 늦어야 하고 조회기간은 366일 이하여야 함.
    @model_validator(mode="after")
    def validate_range(self) -> "IncidentQuery":
        span = self.to_time - self.from_time
        if not timedelta(0) < span <= timedelta(days=366):
            raise ValueError("조회 기간은 0일 초과 366일 이하여야 합니다.")
        return self

# 장애 기록 한 건을 나타냄
class Incident(BaseModel):
    id: str
    category: Category
    severity: Severity
    status: Status
    occurred_at: AwareDatetime
    cause: str
    version: int

#페이지 단위로 장애 기록을 반환하는 응답 모델
class IncidentPage(BaseModel):
    items: list[Incident]
    page: int
    size: int
    total: int = Field(ge=0)
