"""模型 Provider 基类 + OpenAI 兼容实现（Ollama/vLLM/LM Studio/云端）。"""
from typing import AsyncIterator


class BaseProvider:
    name = "base"

    async def generate(self, messages: list[dict], model: str = "") -> str:
        raise NotImplementedError

    async def stream(self, messages: list[dict], model: str = "") -> AsyncIterator[str]:
        yield await self.generate(messages, model)


class OpenAICompatProvider(BaseProvider):
    """复用现有 services/llm 的 OpenAI 兼容调用。"""

    name = "openai-compat"

    async def generate(self, messages: list[dict], model: str = "") -> str:
        from app.services.llm import LLMUnavailable, llm_stream

        pieces = []
        try:
            async for piece in llm_stream(messages):
                pieces.append(piece)
        except LLMUnavailable:
            raise
        return "".join(pieces)

    async def stream(self, messages: list[dict], model: str = "") -> AsyncIterator[str]:
        from app.services.llm import llm_stream

        async for piece in llm_stream(messages):
            yield piece
