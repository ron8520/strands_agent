"""AWS CDK stack provisioning Chainlit on ECS with Cognito authentication."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aws_cdk import (  # type: ignore
    Duration,
    Stack,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct  # type: ignore

from agentcore.config import DeploymentBundle


@dataclass(frozen=True)
class ChainlitEcsProps:
    """Properties required to render the ECS deployment."""

    deployment: DeploymentBundle
    container_image: ecs.ContainerImage
    desired_count: int = 2
    public_load_balancer: bool = True


class ChainlitEcsStack(Stack):
    """Provisions ECS, Cognito, and supporting resources for Chainlit."""

    def __init__(self, scope: Construct, construct_id: str, *, props: ChainlitEcsProps, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)
        deployment = props.deployment

        vpc = ec2.Vpc(self, "ChainlitVpc", max_azs=2)
        cluster = ecs.Cluster(self, "ChainlitCluster", vpc=vpc)

        log_group = logs.LogGroup(self, "ChainlitLogGroup", retention=logs.RetentionDays.ONE_MONTH)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ChainlitService",
            cluster=cluster,
            cpu=deployment.ecs.cpu,
            memory_limit_mib=deployment.ecs.memory,
            desired_count=props.desired_count,
            public_load_balancer=props.public_load_balancer,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                container_name=deployment.ecs.container_name,
                image=props.container_image,
                container_port=8000,
                environment={
                    "BEDROCK_AGENT_ID": deployment.agent_core.bedrock_agent_id,
                    "BEDROCK_AGENT_ALIAS_ID": deployment.agent_core.bedrock_agent_alias_id,
                    "AGENT_EXECUTION_ROLE": deployment.agent_core.role_arn,
                    "KNOWLEDGE_BASE_ID": deployment.agent_core.knowledge_base.knowledge_base_id,
                    "PROMPT_ARN": deployment.agent_core.prompt_template.prompt_arn,
                    "GUARDRAIL_ARN": deployment.agent_core.guardrail.guardrail_arn,
                },
                log_driver=ecs.AwsLogDriver(log_group=log_group, stream_prefix="chainlit"),
            ),
        )

        user_pool = cognito.UserPool(
            self,
            "ChainlitUserPool",
            mfa=cognito.Mfa.REQUIRED if deployment.cognito.required_mfa else cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=True),
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
        )

        user_pool_client = cognito.UserPoolClient(
            self,
            "ChainlitUserPoolClient",
            user_pool=user_pool,
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True),
        )

        domain = cognito.UserPoolDomain(
            self,
            "ChainlitDomain",
            user_pool=user_pool,
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=deployment.cognito.user_pool_domain),
        )

        oauth_scope = cognito.OAuthScope.OPENID
        service.listener.add_action(
            "Authenticate",
            action=elbv2.AuthenticateCognitoAction(
                next=elbv2.ListenerAction.forward([service.target_group]),
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                user_pool_domain=domain,
                scope=[oauth_scope],
                session_timeout=Duration.hours(12),
            ),
        )

        service.task_definition.add_to_task_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeAgent",
                    "bedrock:InvokeAgentRuntime",
                    "bedrock:GetPrompt",
                    "bedrock:GetGuardrail",
                    "bedrock:Retrieve",
                ],
                resources=["*"],
            )
        )

        self.url = service.load_balancer.load_balancer_dns_name
        self.user_pool_id = user_pool.user_pool_id
        self.user_pool_client_id = user_pool_client.user_pool_client_id
