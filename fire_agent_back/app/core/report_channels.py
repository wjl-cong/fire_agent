"""
任务级报告流式通道（进程内、易失、非持久）— P2#18

generate_report 节点流式产出报告时，通过本通道把增量内容实时推送给订阅该
任务的 SSE 连接（type=report_delta 帧）。

边界（与升级方案一致）：
- 通道是易失的：断线重连的客户端不会重放历史 delta，终态完整内容仍以
  DB（报告中心 / agent_tasks）为唯一事实源；
- 半截内容不落库：worker 只在节点完成后把完整报告写入状态/DB；
- 无订阅者时 push 为 no-op，worker 照常执行不受影响。
"""
import asyncio
import threading

_lock = threading.Lock()
_subs: dict[int, set] = {}  # task_id -> {(loop, queue), ...}
_runs: dict[int, int] = {}  # task_id -> 报告生成轮次（评审退回/驳回重写时递增）


def begin_generation(task_id: int) -> int:
    """开启新一轮报告生成（重写时再次调用，前端据此清空缓冲区），返回轮次号"""
    with _lock:
        _runs[task_id] = _runs.get(task_id, 0) + 1
        return _runs[task_id]


def subscribe(task_id: int) -> asyncio.Queue:
    """SSE 处理器（事件循环内）订阅某任务的增长流；返回供 await 的队列"""
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    loop = asyncio.get_running_loop()
    with _lock:
        _subs.setdefault(task_id, set()).add((loop, q))
    return q


def unsubscribe(task_id: int, q: asyncio.Queue) -> None:
    with _lock:
        subscribers = _subs.get(task_id)
        if subscribers:
            for pair in list(subscribers):
                if pair[1] is q:
                    subscribers.discard(pair)
            if not subscribers:
                _subs.pop(task_id, None)


def _safe_put(q: asyncio.Queue, item: dict) -> None:
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        pass  # 订阅端消费过慢时丢帧保活；终态完整内容以 DB 为准


def push_delta(task_id: int, run: int, text: str) -> None:
    """worker 线程调用：向该任务全部 SSE 订阅者投递增量（跨线程 loop 调度）"""
    with _lock:
        subscribers = list(_subs.get(task_id, ()))
    for loop, q in subscribers:
        try:
            loop.call_soon_threadsafe(_safe_put, q, {"type": "report_delta", "run": run, "text": text})
        except RuntimeError:
            pass  # 事件循环已关闭（连接方断开），忽略
