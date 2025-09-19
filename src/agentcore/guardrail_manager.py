"""Guardrail enforcement utilities for Bedrock guardrails."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .bedrock_clients import BedrockClientFactory
from .config import GuardrailConfig


@dataclass
class GuardrailManager:
    """Attaches guardrails to agent invocations."""

    client_factory: BedrockClientFactory
    config: GuardrailConfig

    def attach_to_request(self, request: Dict) -> Dict:
        request["guardrailIdentifier"] = self.config.guardrail_arn
        if self.config.guardrail_version:
            request["guardrailVersion"] = self.config.guardrail_version
        return request
