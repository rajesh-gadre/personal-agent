from abc import ABC, abstractmethod

from langgraph.graph import StateGraph


class BaseAgent(ABC):
    """Minimal interface every agent must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def build_graph(self) -> StateGraph:
        ...

    @abstractmethod
    def init_storage(self) -> None:
        ...
