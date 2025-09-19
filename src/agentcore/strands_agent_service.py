"""Strands Agent runtime helpers used by the Chainlit frontend."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .bedrock_clients import BedrockDependencyContainer
from .config import AgentCoreConfig
from .guardrail_manager import GuardrailApplicationResult, GuardrailManager
from .knowledge_base import KnowledgeBaseRetriever
from .mcp_manager import MCPBootstrapper
from .observability import ObservabilityManager, create_observability_manager
from .prompt_template_manager import PromptTemplateManager

try:  # pragma: no cover - illustrative import
    from strands.agent import AgentCoreRuntime
except ImportError:  # pragma: no cover - fallback for documentation
    AgentCoreRuntime = object  # type: ignore


@dataclass(frozen=True)
class AgentResponseMetrics:
    """Captures latency and token usage for a model invocation."""

    latency_seconds: float
    output_tokens: int

    def to_dict(self) -> Dict[str, float | int]:
        return {
            "latency_seconds": self.latency_seconds,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True)
class AgentResponse:
    """Represents the processed output returned to the caller."""

    text: str
    citations: List[str]
    metrics: AgentResponseMetrics
    guardrail_action: Optional[str] = None
    guardrail_reason: Optional[str] = None
    guardrail_metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PreparedAgentRequest:
    """A lightweight container for the runtime payload."""

    input_text: str
    prompt: str
    session_state: Dict[str, Any]
    citations: List[str]

    def runtime_parameters(
        self,
        config: AgentCoreConfig,
        conversation_id: str,
        guardrail_params: Dict[str, str],
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "agentId": config.bedrock_agent_id,
            "agentAliasId": config.bedrock_agent_alias_id,
            "sessionId": conversation_id,
            "endSession": False,
            "inputText": self.input_text,
            "sessionState": self.session_state,
        }
        params.update(guardrail_params)
        return params


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
        self._client_factory = self.dependencies.factory()
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

    def prepare(self, user_input: str) -> PreparedAgentRequest:
        prompt_metadata = self._load_prompt()
        retrieved_docs = self.knowledge_retriever.retrieve(user_input)
        citations = self.knowledge_retriever.to_citations(retrieved_docs)

        kb_config = {
            "knowledgeBaseId": self.config.knowledge_base.knowledge_base_id,
        }
        model_arn = prompt_metadata.get("modelArn")
        if model_arn:
            kb_config["modelArn"] = model_arn

        session_state = {
            "invocationAttributes": {
                "knowledgeBaseConfigurations": [kb_config],
                "retrievedReferences": retrieved_docs,
            }
        }

        return PreparedAgentRequest(
            input_text=user_input,
            prompt=prompt_metadata["template"],
            session_state=session_state,
            citations=citations,
        )

    def complete(self, conversation_id: str, prepared: PreparedAgentRequest) -> AgentResponse:
        start_time = time.perf_counter()
        runtime_client = self._client_factory.bedrock_agent_runtime()
        params = prepared.runtime_parameters(
            config=self.config,
            conversation_id=conversation_id,
            guardrail_params=self.guardrail_manager.runtime_parameters(),
        )
        stream = runtime_client.invoke_agent(**params)

        response_text, total_tokens, used_mcp = self._collect_response(stream)
        elapsed = time.perf_counter() - start_time
        metrics = AgentResponseMetrics(latency_seconds=elapsed, output_tokens=total_tokens)

        guardrail_result: Optional[GuardrailApplicationResult] = None
        if used_mcp and response_text:
            guardrail_result = self.guardrail_manager.apply_to_output(response_text)
            if guardrail_result.intervened:
                response_text = guardrail_result.resolved_text(
                    "⚠️ Guardrail prevented sharing unsafe MCP-sourced content."
                )

        if self.observability:
            self.observability.emit_metrics(
                {
                    "LatencyMs": metrics.latency_seconds * 1000,
                    "OutputTokens": float(metrics.output_tokens),
                }
            )
            self.observability.add_properties({"agentId": self.config.bedrock_agent_id})

        return AgentResponse(
            text=response_text,
            citations=prepared.citations,
            metrics=metrics,
            guardrail_action=guardrail_result.action if guardrail_result else None,
            guardrail_reason=guardrail_result.reason if guardrail_result else None,
            guardrail_metadata=guardrail_result.metadata if guardrail_result and guardrail_result.metadata else None,
        )

    def respond(self, conversation_id: str, user_input: str) -> AgentResponse:
        prepared = self.prepare(user_input)
        return self.complete(conversation_id, prepared)

    @staticmethod
    def _collect_response(stream: Dict[str, Any]) -> tuple[str, int, bool]:
        response_chunks: List[str] = []
        total_tokens = 0
        for event in stream.get("completion", []):
            chunk = event.get("delta", {}).get("text", "")
            if chunk:
                response_chunks.append(chunk)
            metrics = event.get("metrics", {})
            if metrics:
                total_tokens += int(metrics.get("outputTokens", 0))
        used_mcp = StrandsAgentService._detect_mcp_usage(stream)
        return "".join(response_chunks), total_tokens, used_mcp

    @staticmethod
    def _contains_keyword(payload: Any, keywords: set[str]) -> bool:
        if isinstance(payload, str):
            lowered = payload.lower()
            return any(keyword in lowered for keyword in keywords)
        if isinstance(payload, dict):
            return any(
                StrandsAgentService._contains_keyword(key, keywords)
                or StrandsAgentService._contains_keyword(value, keywords)
                for key, value in payload.items()
            )
        if isinstance(payload, list):
            return any(StrandsAgentService._contains_keyword(item, keywords) for item in payload)
        return False

    @staticmethod
    def _detect_mcp_usage(stream: Dict[str, Any]) -> bool:
        """Detect whether the agent trace includes MCP sourced content."""

        keywords = {"mcp://", "model context protocol", "mcp"}
        trace_events = stream.get("trace", [])
        for event in trace_events:
            if not isinstance(event, dict):
                continue
            detail = event.get("trace", event)
            if isinstance(detail, dict):
                type_hint = str(detail.get("type", "")).upper()
                if type_hint in {"ACTION_GROUP", "TOOL", "MCP"}:
                    return True
                provider = detail.get("provider")
                if isinstance(provider, str) and "mcp" in provider.lower():
                    return True
                metadata = detail.get("observationMetadata") or detail.get("metadata")
                if StrandsAgentService._contains_keyword(metadata, keywords):
                    return True
            if StrandsAgentService._contains_keyword(event, keywords):
                return True
        return StrandsAgentService._contains_keyword(stream, keywords)

    @classmethod
    def create(cls, dependencies: BedrockDependencyContainer, install_dir: str = "/opt/mcp") -> "StrandsAgentService":
        config = dependencies.config
        factory = dependencies.factory()
        prompt_manager = PromptTemplateManager(
            client_factory=factory,
            config=config.prompt_template,
        )
        guardrail_manager = GuardrailManager(
            client_factory=factory,
            config=config.guardrail,
        )
        knowledge_retriever = KnowledgeBaseRetriever(
            client_factory=factory,
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
