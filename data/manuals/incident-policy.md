---
document_id: incident-policy
version: "1"
allowed_roles: [viewer, operator]
synthetic: true
---

# 장애 기록 정책

## 상태와 기록

OPEN은 미해결, IN_PROGRESS는 조치 중, RESOLVED는 해결 완료입니다. 장애 기록에는 발생 시각, 등급, 분류, 관측된 원인을 기록합니다. 확인되지 않은 원인은 추정이라고 표시합니다.

## 승인과 감사

후속 티켓 생성에는 유효한 운영자 승인이 필요합니다. 거절되거나 만료된 초안으로 티켓을 생성하지 않습니다. 승인자, 결정 시각, 장애 ID, 생성 결과를 감사 기록으로 남깁니다.
