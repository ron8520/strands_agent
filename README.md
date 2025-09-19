# Strands AgentCore on Bedrock with Chainlit Frontend

This repository demonstrates how to run a Strands-powered Bedrock AgentCore behind a Chainlit frontend hosted on Amazon ECS. The deployment integrates Amazon Cognito for MFA-secured access, Amazon Bedrock Guardrails, Bedrock Prompt Management templates, Bedrock Knowledge Bases for retrieval augmented generation (RAG), and Model Context Protocol (MCP) adapters for Microsoft Azure DevOps and Terraform.

## Repository layout

```
├── src
│   ├── agentcore              # Core orchestration, deployment, and AWS integrations
│   ├── chainlit_frontend      # Chainlit application entry point and configuration loader
│   └── infrastructure         # AWS CDK stack for ECS + Cognito hosting
├── docs                      # Additional deployment notes
└── README.md
```

## Chainlit frontend

* `src/chainlit_frontend/app.py` is the Chainlit entry point deployed into the ECS task. Every user interaction renders discrete `cl.Step()` elements for context retrieval, Bedrock AgentCore invocation, and the final agent answer (including citations). Human feedback is collected via Chainlit actions and persisted through the observability pipeline.
* `src/chainlit_frontend/config_loader.py` converts environment variables into strongly typed configuration objects (SOLID single-responsibility principle).

## AgentCore runtime

* `src/agentcore/config.py` defines immutable dataclasses used across the deployment pipeline.
* `src/agentcore/strands_agent_service.py` connects Strands AgentCore runtime with Bedrock Guardrails, Prompt Management, Knowledge Bases, MCP adapters, and the observability layer.
* `src/agentcore/mcp_manager.py` installs and registers the Azure DevOps and Terraform MCP servers.
* `src/agentcore/knowledge_base.py` performs RAG with Bedrock Knowledge Bases when AWS Kendra cannot be used.
* `src/agentcore/prompt_template_manager.py` fetches prompt templates from Bedrock Prompt Management.
* `src/agentcore/guardrail_manager.py` injects Bedrock Guardrails into every invocation.
* `src/agentcore/observability.py` emits CloudWatch metrics (latency, token usage) and optionally records human feedback in DynamoDB.
* `src/agentcore/deployment.py` contains helpers to provision Bedrock AgentCore resources and knowledge bases.

## Infrastructure

`src/infrastructure/ecs_chainlit_stack.py` implements an AWS CDK stack that deploys:

1. An ECS Fargate service fronted by an Application Load Balancer (ALB).
2. Amazon Cognito User Pool enforcing MFA and protecting the ALB listener.
3. IAM permissions allowing the Chainlit task to invoke Bedrock, retrieve prompts, guardrails, and knowledge base context.

The ECS task injects the environment variables required by `EnvironmentLoader` so the Chainlit service can bootstrap the Strands Agent runtime.

## Deployment workflow

1. **Provision RAG knowledge base**
   ```bash
   python -m agentcore.deployment create_knowledge_base \
     --region us-east-1 \
     --name strands-knowledge-base \
     --description "Primary KB" \
     --embeddings-model arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-g1-text \
     --role-arn arn:aws:iam::<ACCOUNT_ID>:role/BedrockKnowledgeBaseRole \
     --s3-uri arn:aws:s3:::my-rag-documents
   ```

2. **Deploy Bedrock AgentCore**
   ```python
   from agentcore.config import AgentCoreConfig, KnowledgeBaseConfig, PromptTemplateConfig, GuardrailConfig
   from agentcore.deployment import AgentCoreDeployer

   config = AgentCoreConfig(
       bedrock_agent_id="",  # filled after first deployment
       bedrock_agent_alias_id="",
       role_arn="arn:aws:iam::<ACCOUNT_ID>:role/AgentExecutionRole",
       knowledge_base=KnowledgeBaseConfig(knowledge_base_id="kb-123"),
       prompt_template=PromptTemplateConfig(prompt_arn="arn:aws:bedrock:...:prompt/my-template"),
       guardrail=GuardrailConfig(guardrail_arn="arn:aws:bedrock:...:guardrail/my-guardrail"),
   )

   deployer = AgentCoreDeployer(config=config, region_name="us-east-1")
   result = deployer.deploy(
       agent_name="strands-agent", 
       instruction="Use Strands to orchestrate DevOps assistance", 
       foundation_model="arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet"
   )
   print(result)
   ```

3. **Build the Chainlit container image**
   ```dockerfile
   FROM public.ecr.aws/lambda/python:3.11
   COPY requirements.txt ./
   RUN pip install -r requirements.txt
   COPY src ./src
   ENV CHAINLIT_HOST=0.0.0.0 CHAINLIT_PORT=8000
   CMD ["python", "-m", "chainlit", "run", "src/chainlit_frontend/app.py", "-h", "0.0.0.0", "-p", "8000"]
   ```

4. **Deploy the ECS stack**
   ```bash
   cdk deploy ChainlitEcsStack \
     -c containerImage=<ECR_IMAGE_URI> \
     -c bedrockAgentId=<AGENT_ID> \
     -c bedrockAgentAliasId=<ALIAS_ID> \
     -c knowledgeBaseId=<KB_ID> \
     -c promptArn=<PROMPT_ARN> \
     -c guardrailArn=<GUARDRAIL_ARN>
   ```

5. **Grant access to Cognito users** and share the ALB URL exported by the stack.

## Observability

Metrics for token usage and latency are emitted to CloudWatch under the namespace supplied by `ObservabilityConfig`. If `feedback_table_name` is provided, user feedback from Chainlit is stored in DynamoDB.

## Extending MCP adapters

Add new MCP repositories by updating the environment variables consumed by `EnvironmentLoader`. The installer clones the repository, optionally runs startup commands, and registers the MCP manifest with Strands AgentCore.
