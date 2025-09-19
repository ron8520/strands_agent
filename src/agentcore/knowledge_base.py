"""Knowledge base retrieval for RAG using Bedrock Knowledge Bases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .bedrock_clients import BedrockClientFactory
from .config import KnowledgeBaseConfig


@dataclass
class KnowledgeBaseRetriever:
    """Retrieves documents from Bedrock Knowledge Bases."""

    client_factory: BedrockClientFactory
    config: KnowledgeBaseConfig

    def retrieve(self, query: str) -> List[Dict]:
        client = self.client_factory.bedrock_knowledge_base()
        response = client.retrieve(
            knowledgeBaseId=self.config.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": self.config.top_k,
                    "overrideSearchType": "SEMANTIC",
                }
            },
            filters=self.config.retrieval_filter_json or {},
        )
        return response.get("retrievedResults", [])

    @staticmethod
    def to_citations(results: List[Dict]) -> List[str]:
        citations: List[str] = []
        for item in results:
            doc = item.get("content", {}).get("document", {})
            title = doc.get("title", "Document")
            source = doc.get("sourceUri") or doc.get("s3Uri", "")
            citations.append(f"{title} ({source})")
        return citations
