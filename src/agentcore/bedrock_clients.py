"""Factory classes for AWS clients used by the Strands AgentCore runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import boto3

from .config import AgentCoreConfig


class BedrockRuntimeProtocol(Protocol):
    """Minimal protocol for the Bedrock Runtime client."""

    def invoke_model(self, **kwargs):
        ...


@dataclass(frozen=True)
class BedrockClientFactory:
    """Creates typed boto3 clients required by the agent."""

    region_name: str

    def bedrock_runtime(self) -> BedrockRuntimeProtocol:
        return boto3.client("bedrock-runtime", region_name=self.region_name)

    def bedrock_agent(self):
        return boto3.client("bedrock-agent", region_name=self.region_name)

    def bedrock_agent_runtime(self):
        return boto3.client("bedrock-agent-runtime", region_name=self.region_name)

    def bedrock_knowledge_base(self):
        return boto3.client("bedrock-knowledge-base", region_name=self.region_name)

    def bedrock_guardrails(self):
        return boto3.client("bedrock-guardrails", region_name=self.region_name)


@dataclass(frozen=True)
class BedrockDependencyContainer:
    """Provides dependency injection for AWS client factories."""

    config: AgentCoreConfig
    region_name: str

    def factory(self) -> BedrockClientFactory:
        return BedrockClientFactory(region_name=self.region_name)
