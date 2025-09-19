"""Loads deployment configuration for the Chainlit frontend."""
from __future__ import annotations

import os
from dataclasses import dataclass

from agentcore.config import (
    AgentCoreConfig,
    CognitoConfig,
    DeploymentBundle,
    ECSConfig,
    GuardrailConfig,
    KnowledgeBaseConfig,
    MCPRepositoryConfig,
    ObservabilityConfig,
    PromptTemplateConfig,
)


@dataclass(frozen=True)
class EnvironmentLoader:
    """Translates environment variables into configuration objects."""

    def bundle(self) -> DeploymentBundle:
        mcp_repositories = [
            MCPRepositoryConfig(
                name="azure-devops-mcp",
                git_url=os.environ.get(
                    "AZURE_DEVOPS_MCP_REPO", "https://github.com/microsoft/azure-devops-mcp.git"
                ),
                revision=os.environ.get("AZURE_DEVOPS_MCP_REVISION", "main"),
                startup_command=["pip", "install", "-r", "requirements.txt"],
            ),
            MCPRepositoryConfig(
                name="terraform-mcp",
                git_url=os.environ.get(
                    "TERRAFORM_MCP_REPO", "https://github.com/hashicorp/terraform-mcp.git"
                ),
                revision=os.environ.get("TERRAFORM_MCP_REVISION", "main"),
                startup_command=["pip", "install", "-r", "requirements.txt"],
            ),
        ]
        observability = ObservabilityConfig(
            namespace=os.environ.get("OBS_NAMESPACE", "Strands/Agent"),
            enable_cloudwatch_metrics=True,
            enable_cloudwatch_logs=True,
            feedback_table_name=os.environ.get("FEEDBACK_TABLE"),
        )
        agent_core = AgentCoreConfig(
            bedrock_agent_id=os.environ["BEDROCK_AGENT_ID"],
            bedrock_agent_alias_id=os.environ["BEDROCK_AGENT_ALIAS_ID"],
            role_arn=os.environ["AGENT_EXECUTION_ROLE"],
            knowledge_base=KnowledgeBaseConfig(
                knowledge_base_id=os.environ["KNOWLEDGE_BASE_ID"],
            ),
            prompt_template=PromptTemplateConfig(
                prompt_arn=os.environ["PROMPT_ARN"],
                version=os.environ.get("PROMPT_VERSION"),
            ),
            guardrail=GuardrailConfig(
                guardrail_arn=os.environ["GUARDRAIL_ARN"],
                guardrail_version=os.environ.get("GUARDRAIL_VERSION"),
            ),
            mcp_repositories=mcp_repositories,
            observability=observability,
        )
        ecs = ECSConfig(
            cluster_name=os.environ.get("ECS_CLUSTER", "chainlit-cluster"),
            service_name=os.environ.get("ECS_SERVICE", "chainlit-service"),
            task_definition=os.environ.get("ECS_TASK_DEFINITION", "chainlit-task"),
            container_name=os.environ.get("CONTAINER_NAME", "chainlit"),
        )
        cognito = CognitoConfig(
            user_pool_id=os.environ["COGNITO_USER_POOL_ID"],
            user_pool_client_id=os.environ["COGNITO_USER_POOL_CLIENT_ID"],
            user_pool_domain=os.environ["COGNITO_USER_POOL_DOMAIN"],
        )
        return DeploymentBundle(ecs=ecs, cognito=cognito, agent_core=agent_core)
