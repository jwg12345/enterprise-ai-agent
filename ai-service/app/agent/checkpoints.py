"""agent 계정/스키마에 한정한 PostgreSQL 체크포인트 연결."""
#LangGraph 상태를 PostgreSQL에 저장 -> 사람이 승인을 기다리는 동안 그래프의 실행 상태를 유지하고 나중에 이어서 실행 할 수 있도록하는 체크포인트 저장소 제공
import os
from contextlib import asynccontextmanager #비동기 리소스를 열고 사용이 끝나면 정리할 수 있도록 


@asynccontextmanager 
async def open_checkpointer(initialize=True):
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    password = os.environ.get("AGENT_DB_PASSWORD", "")
    if not password:
        raise RuntimeError("AGENT_DB_PASSWORD 설정이 필요합니다.")

    #PostgreSQL 연결
    conn = await AsyncConnection.connect(
        host=os.environ.get("AGENT_DB_HOST", "postgres"), port=5432,
        dbname="enterprise", user="agent_app", password=password,
        options="-c search_path=agent", autocommit=True, row_factory=dict_row,
        connect_timeout=5,
    )
    try:
        #DB계정과 스키마 분리 검증
        cursor = await conn.execute("SELECT current_user AS role, current_schema() AS schema, "
                                    "has_schema_privilege(current_user, 'business', 'USAGE') AS business_access")
        row = await cursor.fetchone()

        #현재 DB연결이 다음 조건을 만족하는지 확인
        if row != {"role": "agent_app", "schema": "agent", "business_access": False}:
            raise RuntimeError("Agent DB 계정/스키마 격리 조건이 맞지 않습니다.")

        #LangGraph에서 제공하는 PostgreSQL 체크포인트 저장소 생성
        saver = AsyncPostgresSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
        # setup의 migration과 CREATE INDEX CONCURRENTLY를 위해 autocommit 연결을 사용합니다.
        # 여러 프로세스의 초기 migration은 세션 잠금으로 직렬화합니다.

        #초기화 작업의 중복 실행 방지
        #여러 프로세스가 동시에 초기화하면 충돌할 수 있기 때문에 advisory_lock으로 작업 직렬화
        #즉, 한 프로세스가 초기화를 수행하는 동안 같은 잠금을 사용하는 다른 프로세스는 기다리도록 설계
        if initialize:
            await conn.execute("SELECT pg_advisory_lock(7303001)")
            try:
                await saver.setup()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(7303001)")
        yield saver
    finally:
        await conn.close()
