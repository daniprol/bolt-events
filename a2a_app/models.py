"""Django models for A2A tasks."""

from django.db import models


class A2ATask(models.Model):
    """Django model for storing A2A tasks.

    Represents a single A2A task with all its state, history, and artifacts.
    """

    task_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique task identifier",
    )
    context_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Context ID for grouping related tasks",
    )
    status_state = models.CharField(
        max_length=50,
        db_index=True,
        default="submitted",
        help_text="Current state of the task",
    )
    status_message = models.JSONField(
        null=True,
        blank=True,
        help_text="Status message as JSON",
    )
    history = models.JSONField(
        default=list,
        help_text="Message history for this task",
    )
    artifacts = models.JSONField(
        default=list,
        help_text="List of artifacts produced by the task",
    )
    metadata = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Additional task metadata",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        app_label = "a2a_app"
        db_table = "a2a_tasks"
        indexes = [
            models.Index(fields=["context_id", "created_at"]),
            models.Index(fields=["status_state", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"A2ATask({self.task_id}, {self.status_state})"

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.task_id,
            "contextId": self.context_id,
            "status": {
                "state": self.status_state,
                "message": self.status_message,
            },
            "history": self.history or [],
            "artifacts": self.artifacts or [],
            "metadata": self.metadata or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class Conversation(models.Model):
    """Django model for A2A conversations.

    Represents a conversation (context) that can contain multiple tasks.
    """

    context_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique conversation/context identifier",
    )
    agent_id = models.CharField(
        max_length=255,
        help_text="Agent identifier",
    )
    metadata = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Additional conversation metadata",
    )
    is_streaming = models.BooleanField(
        default=False,
        help_text="Whether this conversation has an active stream",
    )
    stream_url = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL to connect to the stream",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        app_label = "a2a_app"
        db_table = "a2a_conversations"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Conversation({self.context_id})"


class PushNotificationConfig(models.Model):
    """Django model for push notification configurations."""

    task = models.ForeignKey(
        A2ATask,
        on_delete=models.CASCADE,
        related_name="push_configs",
    )
    config_id = models.CharField(
        max_length=255,
        help_text="Configuration identifier",
    )
    url = models.URLField(
        max_length=500,
        help_text="Webhook URL for notifications",
    )
    authentication = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Authentication configuration",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        app_label = "a2a_app"
        db_table = "a2a_push_configs"
        unique_together = [["task", "config_id"]]

    def __str__(self) -> str:
        return f"PushConfig({self.task.task_id}, {self.config_id})"
