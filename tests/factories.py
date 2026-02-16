"""Factory Boy factories for test data."""

import factory
from factory.django import DjangoModelFactory
from a2a_app.models import A2ATask, Conversation, PushNotificationConfig


class TaskFactory(DjangoModelFactory):
    class Meta:
        model = A2ATask

    task_id = factory.Sequence(lambda n: f"task-{n:04d}")
    context_id = factory.LazyAttribute(lambda o: o.task_id)
    status_state = "submitted"
    history = []
    artifacts = []
    metadata = {}


class ConversationFactory(DjangoModelFactory):
    class Meta:
        model = Conversation

    context_id = factory.Sequence(lambda n: f"ctx-{n:04d}")
    agent_id = "default"
    is_streaming = False


class PushNotificationConfigFactory(DjangoModelFactory):
    class Meta:
        model = PushNotificationConfig

    task = factory.SubFactory(TaskFactory)
    config_id = factory.Sequence(lambda n: f"config-{n:04d}")
    url = "https://example.com/webhook"
    authentication = {}
