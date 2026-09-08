"""M2 읽기 요청 분류. 실제 보안 경계는 쓰기 도구를 제공하지 않는 구조입니다."""
import re


def guard(query: str) -> str:
    text = re.sub(r"\s+", " ", query).strip()
    if re.search(r"(drop\s+table|delete\s+from|승인.{0,8}무시|ignore.{0,20}instructions)", text, re.I):
        return "DENIED"

    write_topic = re.search(r"티켓.{0,40}(만들|생성)|삭제해|서버.{0,8}재시작", text, re.I)
    if not write_topic:
        return "READ"

    # 설명 요청이 함께 있더라도 명시적 실행 지시와 특정 티켓 작업은 먼저 차단합니다.
    execution = re.search(
        r"만들어|생성해|생성\s*해|생성\s*하(?:세요|십시오|라|자|고)|"
        r"삭제해|삭제\s*해|재시작해|재시작\s*해|실행해|실행\s*해|처리해|처리\s*해|INC-\d+", text, re.I
    )
    if execution:
        return "WRITE_UNSUPPORTED"

    # 정책 문맥과 설명/질문 종결이 모두 있어야 읽기로 허용합니다.
    # '정책' 한 단어만 덧붙여 실행 요청을 읽기로 바꾸지는 않습니다.
    policy_context = re.search(r"승인|초안|정책|규정|절차", text)
    inquiry = re.search(
        r"(?:필요한가요|필요하나요|필요합니까|있나요|있습니까|되나요|됩니까|인가요|무엇인가요)\s*[?.!]*$|"
        r"(?:정책|규정|절차).{0,20}(?:설명해\s*주세요|알려\s*주세요|알려줘)\s*[?.!]*$", text
    )
    if policy_context and inquiry:
        return "READ"
    return "WRITE_UNSUPPORTED"
