"""What a run costs, read from OpenRouter's answers."""

from langchain_core.callbacks import BaseCallbackHandler


class CostCounter(BaseCallbackHandler):
    """A LangChain callback that adds up the dollars OpenRouter charges for every model call of a run.

    Pass it in a run's config, e.g. `agent.ainvoke(..., config={"callbacks": [counter]})`,
    then read `counter.usd`.
    """

    def __init__(self) -> None:
        self.usd = 0.0

    def on_llm_end(self, response, **kwargs) -> None:
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                if message is not None:
                    self.usd += message.response_metadata.get("cost", 0)
