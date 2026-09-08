"""두 개의 별도 컨테이너 프로세스에서 저장/재개. 티켓은 생성하지 않습니다."""
import argparse
import asyncio
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from app.agent.checkpoints import open_checkpointer


class Probe(TypedDict, total=False):
    status: str


async def run(phase, run_id):
    def wait(state):
        interrupt({"purpose": "합성 PostgreSQL 영속성 검사"})
        return {"status": "RESUMED"}

    async with open_checkpointer() as saver:
        graph = StateGraph(Probe)
        graph.add_node("wait", wait)
        graph.add_edge(START, "wait")
        graph.add_edge("wait", END)
        compiled = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "checkpoint-probe:" + run_id}}
        previous = await compiled.aget_state(config)
        if phase == "pause":
            if previous.values:
                raise RuntimeError("새 검사 ID가 필요합니다.")
            result = await compiled.ainvoke({"status": "WAITING"}, config)
            if not result.get("__interrupt__"):
                raise RuntimeError("승인 대기 저장 실패")
        else:
            if previous.values.get("status") != "WAITING" or previous.next != ("wait",):
                raise RuntimeError("이전 프로세스의 대기 상태를 찾지 못했습니다.")
            result = await compiled.ainvoke(Command(resume="wake"), config)
            if result.get("status") != "RESUMED" or (await compiled.aget_state(config)).next:
                raise RuntimeError("저장된 실행 재개 실패")
        print("PASS:", phase, "— agent 스키마 격리 및 PostgreSQL 체크포인트")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["pause", "resume"])
    parser.add_argument("run_id", type=UUID)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.phase, str(args.run_id)))
    except Exception:
        # DB 연결 정보/비밀이 포함될 수 있는 원시 예외는 출력하지 않습니다.
        raise SystemExit("FAIL: PostgreSQL 체크포인트 검사 실패. DB 상태·계정·패키지 설정을 확인하세요.") from None
