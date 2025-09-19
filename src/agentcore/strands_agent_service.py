"""Implements the Strands-powered Bedrock AgentCore runtime."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .bedrock_clients import BedrockDependencyContainer
from .config import AgentCoreConfig
from .guardrail_manager import GuardrailManager
from .knowledge_base import KnowledgeBaseRetriever
from .mcp_manager import MCPBootstrapper
from .observability import ObservabilityManager, create_observability_manager
from .prompt_template_manager import PromptTemplateManager

try:  # pragma: no cover - illustrative import
    from strands.agent import AgentCoreRuntime, AgentConversation
except ImportError:  # pragma: no cover - fallback for documentation
    AgentCoreRuntime = object  # type: ignore
    AgentConversation = dict  # type: ignore


@dataclass
class StrandsAgentService:
    """Coordinates request flow across Bedrock and Strands components."""

    config: AgentCoreConfig
    dependencies: BedrockDependencyContainer
    guardrail_manager: GuardrailManager
    prompt_manager: PromptTemplateManager
    knowledge_retriever: KnowledgeBaseRetriever
    observability: ObservabilityManager | None
    mcp_bootstrapper: MCPBootstrapper

    def __post_init__(self) -> None:
        self._prompt_cache: Dict[str, str] | None = None
        self._agent_runtime = self._create_agent_runtime()

    def _create_agent_runtime(self) -> AgentCoreRuntime:
        descriptors = self.mcp_bootstrapper.bootstrap()
        runtime = AgentCoreRuntime(
            agent_id=self.config.bedrock_agent_id,
            alias_id=self.config.bedrock_agent_alias_id,
            execution_role_arn=self.config.role_arn,
            mcps=descriptors,
        )
        return runtime

    def _load_prompt(self) -> Dict[str, str]:
        if not self._prompt_cache:
            self._prompt_cache = self.prompt_manager.fetch()
        return self._prompt_cache

    def build_agent_request(self, user_input: str) -> Tuple[Dict, List[str]]:
        prompt_metadata = self._load_prompt()
        retrieved_docs = self.knowledge_retriever.retrieve(user_input)
        citations = self.knowledge_retriever.to_citations(retrieved_docs)
        agent_request = {
            "inputText": user_input,
            "prompt": prompt_metadata["template"],
            "sessionState": {
                "invocationAttributes": {
                    "knowledgeBaseConfigurations": [
                        {
                            "knowledgeBaseId": self.config.knowledge_base.knowledge_base_id,
                            "modelArn": prompt_metadata.get("modelArn"),
                        }
                    ],
                    "retrievedReferences": retrieved_docs,
                }
            },
        }
        agent_request = self.guardrail_manager.attach_to_request(agent_request)
        return agent_request, citations

    def invoke_prepared(self, conversation_id: str, agent_request: Dict, citations: List[str]) -> Dict:
        start_time = time.perf_counter()
        runtime_client = self.dependencies.factory().bedrock_agent_runtime()
        params = {
            "agentId": self.config.bedrock_agent_id,
            "agentAliasId": self.config.bedrock_agent_alias_id,
            "sessionId": conversation_id,
            "endSession": False,
            "inputText": agent_request["inputText"],
            "sessionState": agent_request["sessionState"],
            "guardrailIdentifier": agent_request["guardrailIdentifier"],
        }
        if agent_request.get("guardrailVersion"):
            params["guardrailVersion"] = agent_request["guardrailVersion"]
        stream = runtime_client.invoke_agent(**params)

        response_chunks: List[str] = []
        total_tokens = 0
        for event in stream.get("completion", []):
            chunk = event.get("delta", {}).get("text", "")
            response_chunks.append(chunk)
            total_tokens += event.get("metrics", {}).get("outputTokens", 0)
        response_text = "".join(response_chunks)

        elapsed = time.perf_counter() - start_time
        if self.observability:
            self.observability.emit_metrics(
                {
                    "LatencyMs": elapsed * 1000,
                    "OutputTokens": float(total_tokens),
                }
            )
            self.observability.add_properties({"agentId": self.config.bedrock_agent_id})

        return {
            "response": response_text,
            "citations": citations,
            "metrics": {"latency_seconds": elapsed, "output_tokens": total_tokens},
        }

    def invoke(self, conversation_id: str, user_input: str) -> Dict:
        agent_request, citations = self.build_agent_request(user_input)
        return self.invoke_prepared(conversation_id, agent_request, citations)

    @classmethod
    def create(cls, dependencies: BedrockDependencyContainer, install_dir: str = "/opt/mcp") -> "StrandsAgentService":
        config = dependencies.config
        prompt_manager = PromptTemplateManager(
            client_factory=dependencies.factory(),
            config=config.prompt_template,
        )
        guardrail_manager = GuardrailManager(
            client_factory=dependencies.factory(),
            config=config.guardrail,
        )
        knowledge_retriever = KnowledgeBaseRetriever(
            client_factory=dependencies.factory(),
            config=config.knowledge_base,
        )
        observability = create_observability_manager(config)
        from pathlib import Path
        from .mcp_manager import MCPRepositoryInstaller

        installer = MCPRepositoryInstaller(
            repositories=config.mcp_repositories,
            install_dir=Path(install_dir),
        )
        mcp_bootstrapper = MCPBootstrapper(installer=installer)

        return cls(
            config=config,
            dependencies=dependencies,
            guardrail_manager=guardrail_manager,
            prompt_manager=prompt_manager,
            knowledge_retriever=knowledge_retriever,
            observability=observability,
            mcp_bootstrapper=mcp_bootstrapper,
        )
