"""Configuration models for the Strands Bedrock AgentCore deployment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CognitoConfig:
    """Stores Cognito authentication configuration required by Chainlit."""

    user_pool_id: str
    user_pool_client_id: str
    user_pool_domain: str
    required_mfa: bool = True


@dataclass(frozen=True)
class ECSConfig:
    """Describes the ECS service that will host Chainlit."""

    cluster_name: str
    service_name: str
    task_definition: str
    container_name: str
    cpu: int = 1024
    memory: int = 2048


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    """Represents a Bedrock Knowledge Base configuration for RAG."""

    knowledge_base_id: str
    retrieval_filter_json: Optional[Dict[str, str]] = None
    top_k: int = 5


@dataclass(frozen=True)
class PromptTemplateConfig:
    """Represents metadata required to fetch a prompt template."""

    prompt_arn: str
    version: Optional[str] = None


@dataclass(frozen=True)
class GuardrailConfig:
    """References a Bedrock guardrail resource."""

    guardrail_arn: str
    guardrail_version: Optional[str] = None


@dataclass(frozen=True)
class MCPRepositoryConfig:
    """Configuration for MCP repositories deployed alongside the agent."""

    name: str
    git_url: str
    revision: str = "main"
    startup_command: Optional[List[str]] = None


@dataclass(frozen=True)
class ObservabilityConfig:
    """Configuration for observability and feedback pipelines."""

    namespace: str
    enable_cloudwatch_metrics: bool = True
    enable_cloudwatch_logs: bool = True
    feedback_table_name: Optional[str] = None


@dataclass(frozen=True)
class AgentCoreConfig:
    """Aggregates all configuration inputs required to run the agent."""

    bedrock_agent_id: str
    bedrock_agent_alias_id: str
    role_arn: str
    knowledge_base: KnowledgeBaseConfig
    prompt_template: PromptTemplateConfig
    guardrail: GuardrailConfig
    mcp_repositories: List[MCPRepositoryConfig] = field(default_factory=list)
    observability: Optional[ObservabilityConfig] = None


@dataclass(frozen=True)
class DeploymentBundle:
    """Container for deployment-time configuration."""

    ecs: ECSConfig
    cognito: CognitoConfig
    agent_core: AgentCoreConfig
