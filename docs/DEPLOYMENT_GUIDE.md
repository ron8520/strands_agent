# Deployment Guide

This guide explains how to deploy the Strands AgentCore runtime on Amazon Bedrock with a Chainlit frontend running inside ECS.

## Prerequisites

* AWS account with Bedrock, Cognito, ECS, and DynamoDB access.
* `aws` CLI configured.
* `cdk` CLI installed (v2).
* Docker for building the Chainlit container.

## Step 1: Prepare Bedrock knowledge base (RAG)

Use the command line utility to create a knowledge base when Kendra is not available:

```bash
python -m agentcore create-knowledge-base \
  --region us-east-1 \
  --name strands-knowledge-base \
  --description "Primary KB" \
  --embeddings-model arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-g1-text \
  --role-arn arn:aws:iam::<ACCOUNT_ID>:role/BedrockKnowledgeBaseRole \
  --s3-uri arn:aws:s3:::my-rag-documents
```

## Step 2: Deploy Bedrock AgentCore

```bash
python -m agentcore deploy-agent \
  --region us-east-1 \
  --agent-name strands-agent \
  --instruction "Use Strands to orchestrate DevOps assistance" \
  --foundation-model arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet \
  --execution-role arn:aws:iam::<ACCOUNT_ID>:role/AgentExecutionRole \
  --knowledge-base-id kb-123456 \
  --prompt-arn arn:aws:bedrock:us-east-1:<ACCOUNT_ID>:prompt/strands-orchestration \
  --guardrail-arn arn:aws:bedrock:us-east-1:<ACCOUNT_ID>:guardrail/devops-guardrail
```

The command prints the `agent_id` and `agent_alias_id` required by the Chainlit frontend.

## Step 3: Build the Chainlit image

```bash
docker build -t strands-chainlit .
```

## Step 4: Deploy the ECS stack

```bash
cdk deploy ChainlitEcsStack \
  -c containerImage=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/strands-chainlit:latest \
  -c bedrockAgentId=<AGENT_ID> \
  -c bedrockAgentAliasId=<ALIAS_ID> \
  -c knowledgeBaseId=<KB_ID> \
  -c promptArn=<PROMPT_ARN> \
  -c guardrailArn=<GUARDRAIL_ARN>
```

## Step 5: Validate Cognito + MFA

Create users in the Cognito User Pool exported by the CDK stack, enforce MFA, and distribute the Chainlit ALB URL.

## Observability and feedback

* Metrics for latency and token usage are published to CloudWatch.
* Feedback is collected via the Chainlit UI and stored in DynamoDB when configured.
