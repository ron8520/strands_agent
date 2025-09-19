"""Command line utilities for deploying the Strands Bedrock AgentCore."""
from __future__ import annotations

import argparse

from .config import AgentCoreConfig, GuardrailConfig, KnowledgeBaseConfig, PromptTemplateConfig
from .deployment import AgentCoreDeployer, create_knowledge_base


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentCore deployment utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    kb = subparsers.add_parser("create-knowledge-base", help="Create a Bedrock knowledge base")
    kb.add_argument("--region", required=True)
    kb.add_argument("--name", required=True)
    kb.add_argument("--description", default="Strands knowledge base")
    kb.add_argument("--embeddings-model", required=True)
    kb.add_argument("--role-arn", required=True)
    kb.add_argument("--s3-uri", required=True)

    deploy = subparsers.add_parser("deploy-agent", help="Deploy Bedrock AgentCore")
    deploy.add_argument("--region", required=True)
    deploy.add_argument("--agent-name", required=True)
    deploy.add_argument("--instruction", required=True)
    deploy.add_argument("--foundation-model", required=True)
    deploy.add_argument("--execution-role", required=True)
    deploy.add_argument("--knowledge-base-id", required=True)
    deploy.add_argument("--prompt-arn", required=True)
    deploy.add_argument("--prompt-version", default=None)
    deploy.add_argument("--guardrail-arn", required=True)
    deploy.add_argument("--guardrail-version", default=None)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "create-knowledge-base":
        response = create_knowledge_base(
            region_name=args.region,
            name=args.name,
            description=args.description,
            embeddings_model_arn=args.embeddings_model,
            role_arn=args.role_arn,
            s3_uri=args.s3_uri,
        )
        print(response)
        return

    if args.command == "deploy-agent":
        config = AgentCoreConfig(
            bedrock_agent_id="",
            bedrock_agent_alias_id="",
            role_arn=args.execution_role,
            knowledge_base=KnowledgeBaseConfig(knowledge_base_id=args.knowledge_base_id),
            prompt_template=PromptTemplateConfig(
                prompt_arn=args.prompt_arn,
                version=args.prompt_version,
            ),
            guardrail=GuardrailConfig(
                guardrail_arn=args.guardrail_arn,
                guardrail_version=args.guardrail_version,
            ),
        )
        deployer = AgentCoreDeployer(config=config, region_name=args.region)
        response = deployer.deploy(
            agent_name=args.agent_name,
            instruction=args.instruction,
            foundation_model=args.foundation_model,
        )
        print(response)
        return

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
