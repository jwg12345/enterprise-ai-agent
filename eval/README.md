# 평가 준비 자료

`dataset.jsonl`은 실행기 개발용 초기 사례 8건이며 평가 완료 결과가 아닙니다. 각 행의 id는 고유하고 expected_sources는 원본 문서의 document_id를 참조합니다.

expected_tools는 해당 사례 전체 실행에서 허용/기대되는 도구 집합입니다. decision이 없는 조회 사례는 쓰기를 수행하지 않습니다. 상태를 넣은 사례는 실행기가 해당 승인 조건을 준비해야 하며 query만으로 만료·경합 테스트를 대체할 수 없습니다.

M4에서 개발셋과 고정 평가셋을 분리하고 실제 검색·Agent 실행기로 측정합니다. 안전성 사례는 pytest/JUnit의 DB 변경 건수 assertion으로도 검증합니다. 결과 규격은 [운영 문서](../docs/operations.md)를 따릅니다.
