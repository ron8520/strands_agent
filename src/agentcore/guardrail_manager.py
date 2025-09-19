"""Guardrail enforcement utilities for Bedrock guardrails."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .bedrock_clients import BedrockClientFactory
from .config import GuardrailConfig


@dataclass(frozen=True)
class GuardrailApplicationResult:
    """Represents the outcome of applying a guardrail to a text payload."""

    action: str
    reason: Optional[str]
    outputs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def intervened(self) -> bool:
        """Return ``True`` when the guardrail blocked or redacted content."""

        return self.action.upper() == "GUARDRAIL_INTERVENED"

    def resolved_text(self, original: str) -> str:
        """Return the guardrail-adjusted text, falling back to ``original``."""

        if self.outputs:
            sanitized = "".join(self.outputs).strip()
            if sanitized:
                return sanitized
        return original


@dataclass(frozen=True)
class GuardrailManager:
    """Provides helpers to configure and actively enforce guardrails."""

    client_factory: BedrockClientFactory
    config: GuardrailConfig

    def runtime_parameters(self) -> Dict[str, str]:
        """Return the parameters expected by ``invoke_agent``.

        Keeping the method tiny avoids the indirection of mutating request
        dictionaries in-place and makes the service layer code easier to read.
        """

        params = {"guardrailIdentifier": self.config.guardrail_arn}
        if self.config.guardrail_version:
            params["guardrailVersion"] = self.config.guardrail_version
        return params

    def apply_to_output(self, content: str) -> GuardrailApplicationResult:
        """Run ``ApplyGuardrail`` on generated content.

        The Strands agent uses this to selectively evaluate MCP sourced
        information without imposing the guardrail on trusted knowledge base
        snippets.
        """

        client = self.client_factory.bedrock_guardrails()
        version = self.config.guardrail_version or "DRAFT"
        response = client.apply_guardrail(
            guardrailIdentifier=self.config.guardrail_arn,
            guardrailVersion=version,
            content=[
                {
                    "text": {
                        "text": content,
                        "qualifiers": ["guard_content"],
                    }
                }
            ],
            source="OUTPUT",
            outputScope="FULL",
        )

        outputs: List[str] = []
        for block in response.get("outputs", []):
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text:
                    outputs.append(text)

        metadata: Dict[str, Any] = {}
        coverage = response.get("guardrailCoverage")
        if coverage:
            metadata["guardrailCoverage"] = coverage
        assessments = response.get("assessments")
        if assessments:
            metadata["assessments"] = assessments

        return GuardrailApplicationResult(
            action=response.get("action", "NONE"),
            reason=response.get("actionReason"),
            outputs=outputs,
            metadata=metadata,
        )
