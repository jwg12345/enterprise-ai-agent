"""agent 계정/스키마에 한정한 PostgreSQL 체크포인트 연결."""
import os
from contextlib import asynccontextmanager


@asynccontextmanager
async def open_checkpointer(initialize=True):
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    password = os.environ.get("AGENT_DB_PASSWORD", "")
    if not password:
        raise RuntimeError("AGENT_DB_PASSWORD 설정이 필요합니다.")
    conn = await AsyncConnection.connect(
        host=os.environ.get("AGENT_DB_HOST", "postgres"), port=5432,
        dbname="enterprise", user="agent_app", password=password,
        options="-c search_path=agent", autocommit=True, row_factory=dict_row,
        connect_timeout=5,
    )
    try:
        cursor = await conn.execute("SELECT current_user AS role, current_schema() AS schema, "
                                    "has_schema_privilege(current_user, 'business', 'USAGE') AS business_access")
        row = await cursor.fetchone()
        if row != {"role": "agent_app", "schema": "agent", "business_access": False}:
            raise RuntimeError("Agent DB 계정/스키마 격리 조건이 맞지 않습니다.")
        saver = AsyncPostgresSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
        # setup의 migration과 CREATE INDEX CONCURRENTLY를 위해 autocommit 연결을 사용합니다.
        # 여러 프로세스의 초기 migration은 세션 잠금으로 직렬화합니다.
        if initialize:
            await conn.execute("SELECT pg_advisory_lock(7303001)")
            try:
                await saver.setup()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(7303001)")
        yield saver
    finally:
        await conn.close()
