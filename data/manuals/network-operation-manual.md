---
document_id: network-operations
version: "1"
allowed_roles: [viewer, operator]
synthetic: true
---

# 네트워크 운영 매뉴얼

## P1 대응

P1 네트워크 장애는 Platform 팀에 상황을 공유하고 Gateway 상태, Load Balancer 연결 상태, Firewall 정책을 순서대로 확인합니다. 점검 결과와 관측 시각을 기록합니다. 이 문서는 가상 시연용이며 실제 시스템 변경을 승인하지 않습니다.

## 미해결 장애 후속 조치

미해결 장애는 장애 ID, 현재 증상, 확인할 항목을 포함한 후속 티켓을 제안합니다. 티켓 생성은 운영자의 명시적인 승인을 받은 뒤 수행합니다. 이미 해결된 장애에는 같은 목적의 후속 점검 티켓을 자동 제안하지 않습니다.
