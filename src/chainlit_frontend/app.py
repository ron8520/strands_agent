"""Chainlit application entry point deployed on ECS."""
from __future__ import annotations

import json
import os
from typing import Optional
from uuid import uuid4

import chainlit as cl

from agentcore.bedrock_clients import BedrockDependencyContainer
from agentcore.strands_agent_service import StrandsAgentService

from .config_loader import EnvironmentLoader


def _format_citations(citations: list[str]) -> str:
    if not citations:
        return "No citations returned by the knowledge base."
    joined = "\n".join(f"- {citation}" for citation in citations)
    return f"**Sources**\n{joined}"


@cl.on_chat_start
async def on_chat_start() -> None:
    loader = EnvironmentLoader()
    bundle = loader.bundle()
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    dependencies = BedrockDependencyContainer(
        config=bundle.agent_core,
        region_name=region,
    )
    service = StrandsAgentService.create(dependencies)
    cl.user_session.set("service", service)
    cl.user_session.set("conversation_id", str(uuid4()))

    await cl.Message(
        content=(
            "✅ Cognito MFA validation complete. The Strands agent is ready to assist.\n"
            "Ask me anything about your infrastructure or DevOps pipelines."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    service: Optional[StrandsAgentService] = cl.user_session.get("service")
    conversation_id: Optional[str] = cl.user_session.get("conversation_id")
    if not service or not conversation_id:
        await cl.Message(content="Session not initialized. Please refresh the page.").send()
        return

    async with cl.Step(name="Retrieve context from Bedrock Knowledge Base") as retrieve_step:
        agent_request, citations = service.build_agent_request(message.content)
        preview = {
            "promptPreview": agent_request["prompt"][:160],
            "references": citations,
        }
        retrieve_step.output = json.dumps(preview, indent=2)

    async with cl.Step(name="Invoke Bedrock AgentCore via Strands") as invoke_step:
        result = service.invoke_prepared(conversation_id, agent_request, citations)
        invoke_step.output = json.dumps(result["metrics"], indent=2)

    final_step = cl.Step(name="Final agent response")
    async with final_step:
        final_text = f"{result['response']}\n\n{_format_citations(result['citations'])}"
        await final_step.send(content=final_text, author="Strands Agent")

    if service.observability:
        await cl.AskActionMessage(
            content="How helpful was this response?",
            actions=[
                cl.Action(name="feedback_positive", value="positive", label="👍 Helpful"),
                cl.Action(name="feedback_neutral", value="neutral", label="😐 Neutral"),
                cl.Action(name="feedback_negative", value="negative", label="👎 Needs work"),
            ],
        ).send()

    cl.user_session.set("pending_feedback", {"conversation_id": conversation_id})


@cl.action_callback("feedback_positive")
@cl.action_callback("feedback_neutral")
@cl.action_callback("feedback_negative")
async def on_feedback(action: cl.Action) -> None:
    service: Optional[StrandsAgentService] = cl.user_session.get("service")
    pending = cl.user_session.get("pending_feedback", {})
    if not service or not service.observability:
        await cl.Message(content="Feedback recorded. Thank you!").send()
        return

    service.observability.record_feedback(
        conversation_id=pending.get("conversation_id", str(uuid4())),
        rating=action.value,
        notes="collected-via-chainlit",
    )
    await cl.Message(content="🙏 Feedback captured. This helps improve the agent!").send()
