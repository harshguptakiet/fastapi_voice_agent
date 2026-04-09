from abc import ABC, abstractmethod

class LLMProvider(ABC):

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Return a full LLM response"""
        pass

    @abstractmethod
    async def stream(self, prompt: str, on_token):
        """Stream tokens to callback function"""
        pass
