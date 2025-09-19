"""Deployment helpers for Bedrock AgentCore."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import boto3

from .config import AgentCoreConfig, KnowledgeBaseConfig, PromptTemplateConfig


@dataclass
class AgentCoreDeployer:
    """Creates or updates the Bedrock AgentCore resources."""

    config: AgentCoreConfig
    region_name: str

    def __post_init__(self) -> None:
        self.agent_client = boto3.client("bedrock-agent", region_name=self.region_name)
        self.runtime_client = boto3.client("bedrock-agent-runtime", region_name=self.region_name)
        self.kb_client = boto3.client("bedrock-knowledge-base", region_name=self.region_name)

    def ensure_knowledge_base(self, config: KnowledgeBaseConfig) -> str:
        try:
            response = self.kb_client.get_knowledge_base(knowledgeBaseId=config.knowledge_base_id)
            return response["knowledgeBaseId"]
        except self.kb_client.exceptions.ResourceNotFoundException:
            raise ValueError(
                "Knowledge base must be created ahead of deployment. Use `create_knowledge_base.py`."
            )

    def register_prompt_template(self, config: PromptTemplateConfig) -> Dict[str, str]:
        response = self.agent_client.get_prompt(
            promptIdentifier=config.prompt_arn,
            promptVersion=config.version or "$LATEST",
        )
        return {
            "promptIdentifier": response["promptArn"],
            "promptVersion": response["version"] if "version" in response else "$LATEST",
        }

    def deploy(self, agent_name: str, instruction: str, foundation_model: str) -> Dict:
        knowledge_base_id = self.ensure_knowledge_base(self.config.knowledge_base)
        prompt_reference = self.register_prompt_template(self.config.prompt_template)

        create_response = self.agent_client.create_agent(
            agentName=agent_name,
            foundationModel=foundation_model,
            instruction=instruction,
            agentResourceRoleArn=self.config.role_arn,
            guardrailConfiguration={
                "guardrailIdentifier": self.config.guardrail.guardrail_arn,
                "guardrailVersion": self.config.guardrail.guardrail_version or "$LATEST",
            },
            knowledgeBaseConfigurations=[
                {
                    "knowledgeBaseId": knowledge_base_id,
                    "description": "Primary knowledge base for retrieval augmented generation",
                }
            ],
            promptOverrideConfiguration={
                "promptConfigurations": [
                    {
                        "promptType": "ORCHESTRATION",
                        "promptSource": "PROMPT_LIBRARY",
                        "promptTemplate": prompt_reference,
                    }
                ]
            },
        )

        agent_id = create_response["agentId"]
        alias_response = self.agent_client.create_agent_alias(
            agentId=agent_id,
            agentAliasName="prod",
            description="Production alias deployed by automation",
        )

        self.agent_client.update_agent_action_group(
            agentId=agent_id,
            agentActionGroupId="orchestration",
            actionGroupState="ENABLED",
        )

        return {
            "agent_id": agent_id,
            "agent_alias_id": alias_response["agentAliasId"],
        }


def create_knowledge_base(
    region_name: str,
    name: str,
    description: str,
    embeddings_model_arn: str,
    role_arn: str,
    s3_uri: str,
) -> Dict:
    """Creates a Bedrock knowledge base used for RAG."""

    kb_client = boto3.client("bedrock-knowledge-base", region_name=region_name)
    response = kb_client.create_knowledge_base(
        name=name,
        description=description,
        roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": embeddings_model_arn,
            },
        },
        storageConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": s3_uri,
            },
        },
    )
    return response
