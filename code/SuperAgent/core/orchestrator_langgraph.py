
from langgraph.graph import StateGraph, END
from app.schemas import OrchestratorState
from core.tracer import OrchestratorTracer

def build_graph(agents, reflector, log_dir="runs"):
    tracer = OrchestratorTracer(log_dir=log_dir)
    g = StateGraph(OrchestratorState)

    def wrap(name, func):
        def f(state, *args, **kwargs):
            import copy
            # 新版 LangGraph 以 dict 传递状态，先还原为 Pydantic 对象
            if isinstance(state, dict):
                state = OrchestratorState(**state)
            before = copy.deepcopy(state)
            after = func(state, *args, **kwargs)
            tracer.log(name, before, after)
            # 返回 dict 以兼容 LangGraph 的状态更新机制
            return after.model_dump() if isinstance(after, OrchestratorState) else after
        return f

    g.add_node("planner", wrap("planner", agents["planner"].plan))
    g.add_node("researcher", wrap("researcher", agents["researcher"].run))
    g.add_node("analyst", wrap("analyst", agents["analyst"].run))
    g.add_node("writer", wrap("writer", agents["writer"].run))
    g.add_node("reflect", wrap("reflect", reflector.evaluate_and_maybe_retry))

    g.add_edge("planner", "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", "reflect")
    g.add_edge("reflect", END)

    g.set_entry_point("planner")

    compiled = g.compile()

    def save_trace():
        return tracer.save()
    compiled.save_trace = save_trace

    return compiled
