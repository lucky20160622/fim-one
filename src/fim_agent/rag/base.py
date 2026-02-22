"""Abstract base for RAG retrievers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """A retrieved document chunk.

    Attributes:
        content: The textual content of the document chunk.
        metadata: Arbitrary key-value metadata associated with the chunk
            (e.g. source file, page number, chunk index).
        score: Optional relevance score assigned by the retriever.
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None


class BaseRetriever(ABC):
    """Abstract interface for document retrieval.

    Concrete implementations should connect to a vector store, search
    index, or other backend and return ranked ``Document`` instances.
    """

    @abstractmethod
    async def retrieve(self, query: str, *, top_k: int = 5) -> list[Document]:
        """Retrieve relevant documents for a query.

        Args:
            query: The natural-language search query.
            top_k: Maximum number of documents to return.

        Returns:
            A list of ``Document`` objects ranked by relevance.
        """
        ...
