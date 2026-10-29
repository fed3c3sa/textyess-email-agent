from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.agentic_infra.cost import CostCounter


def model_answer(cost: float | None) -> LLMResult:
    metadata = {"cost": cost} if cost is not None else {}
    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok", response_metadata=metadata))]])


def test_cost_counter_adds_up_every_model_call():
    counter = CostCounter()
    counter.on_llm_end(model_answer(0.002))
    counter.on_llm_end(model_answer(0.001))
    counter.on_llm_end(model_answer(None))  # a provider that reports no cost
    assert round(counter.usd, 6) == 0.003
