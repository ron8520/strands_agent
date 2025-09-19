"""Observability utilities for Strands AgentCore."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Protocol

import boto3

from .config import AgentCoreConfig, ObservabilityConfig


class MetricSink(Protocol):
    """Interface for metric sinks."""

    def put_metric(self, name: str, value: float, unit: str = "Count") -> None:
        ...

    def put_property(self, name: str, value: str) -> None:
        ...


@dataclass
class CloudWatchMetricSink:
    """Sends metrics to CloudWatch."""

    namespace: str
    client: any = field(default_factory=lambda: boto3.client("cloudwatch"))

    def put_metric(self, name: str, value: float, unit: str = "Count") -> None:
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[{"MetricName": name, "Value": value, "Unit": unit}],
        )

    def put_property(self, name: str, value: str) -> None:
        self.put_metric(name=name, value=1.0, unit="Count")


@dataclass
class FeedbackCollector:
    """Persists human feedback for later review."""

    table_name: str
    client: any = field(default_factory=lambda: boto3.client("dynamodb"))

    def record_feedback(self, conversation_id: str, rating: str, notes: str) -> None:
        self.client.put_item(
            TableName=self.table_name,
            Item={
                "conversationId": {"S": conversation_id},
                "rating": {"S": rating},
                "notes": {"S": notes},
                "timestamp": {"S": datetime.utcnow().isoformat()},
            },
        )


@dataclass
class ObservabilityManager:
    """Coordinates metric and feedback instrumentation."""

    config: AgentCoreConfig
    sinks: List[MetricSink]
    feedback_collector: FeedbackCollector | None = None

    def emit_metrics(self, metrics: Dict[str, float]) -> None:
        for name, value in metrics.items():
            for sink in self.sinks:
                sink.put_metric(name, value)

    def add_properties(self, props: Dict[str, str]) -> None:
        for name, value in props.items():
            for sink in self.sinks:
                sink.put_property(name, value)

    def record_feedback(self, conversation_id: str, rating: str, notes: str) -> None:
        if self.feedback_collector:
            self.feedback_collector.record_feedback(conversation_id, rating, notes)


def create_observability_manager(config: AgentCoreConfig) -> ObservabilityManager | None:
    """Factory that respects the SOLID dependency inversion principle."""

    obs_config = config.observability
    if not obs_config:
        return None

    sinks: List[MetricSink] = []
    if obs_config.enable_cloudwatch_metrics:
        sinks.append(CloudWatchMetricSink(namespace=obs_config.namespace))

    feedback_collector = None
    if obs_config.feedback_table_name:
        feedback_collector = FeedbackCollector(table_name=obs_config.feedback_table_name)

    return ObservabilityManager(
        config=config,
        sinks=sinks,
        feedback_collector=feedback_collector,
    )
