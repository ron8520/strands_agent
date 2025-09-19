"""Prompt template utilities that leverage Bedrock Prompt Management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .bedrock_clients import BedrockClientFactory
from .config import PromptTemplateConfig


@dataclass
class PromptTemplateManager:
    """Downloads prompt templates from Bedrock Prompt Management."""

    client_factory: BedrockClientFactory
    config: PromptTemplateConfig

    def fetch(self) -> Dict[str, str]:
        client = self.client_factory.bedrock_agent()
        params = {"promptIdentifier": self.config.prompt_arn}
        if self.config.version:
            params["promptVersion"] = self.config.version
        response = client.get_prompt(**params)
        return {
            "name": response["name"],
            "template": response["prompt"]
            if "prompt" in response
            else response["promptTemplate"]["textTemplate"],
            "modelArn": response.get("modelArn"),
        }
