# serializers.py

from rest_framework import serializers
import re
from urllib.parse import urlparse


class WorkflowStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    workflow_id = serializers.CharField(required=False)
    details = serializers.DictField(required=False)


class WorkflowSubmissionSerializer(serializers.Serializer):
    rocratefile = serializers.FileField(
        required=True,
        help_text="The RO-Crate ZIP file containing a workflow.yaml file.",
    )
    dry_run = serializers.BooleanField(
        required=False,
        default=False,
        help_text="If true, the workflow is validated but not executed.",
    )
    webhook_url = serializers.CharField(
        required=False,
        default=None,
        help_text=(
            "Webhook URL template to be called once the workflow completes. The URL may contain a placeholder, that will be substituted at delivery time.\n\n"
            "Supported placeholder: \n"
            "- `{workflow_id}`: the assigned workflow identifier\n\n"
            "Example:\n"
            "`https://example.com/webhooks/workflows/{workflow_id}`"
        ),
    )
    force = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Force re-execution if the same workflow was already submitted.",
    )

    def validate_webhook_url(self, value):
        if value is None:
            return value
        
        # valid url
        parsed = urlparse(value)

        if parsed.scheme not in ('http', 'https'):
            raise serializers.ValidationError("Only http and https are allowed")

        if not parsed.hostname:
            raise serializers.ValidationError("URL must include a host")

        # valid placeholder
        PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
        ALLOWED_WEBHOOK_PLACEHOLDERS = {"workflow_id"}
        fields = set(PLACEHOLDER_RE.findall(value))

        unknown = fields - ALLOWED_WEBHOOK_PLACEHOLDERS
        if unknown:
            raise serializers.ValidationError(
                f"Unsupported webhook URL placeholders: {', '.join(sorted(unknown))}. Please use a supported placeholder from the list: {ALLOWED_WEBHOOK_PLACEHOLDERS}"
            )
        return value


class WorkflowGraphRequestSerializer(serializers.Serializer):
    file = serializers.FileField(
        required=False,
        help_text="Workflow YAML file upload.",
    )
    url = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="URL to a workflow YAML/JSON resource.",
        default="",
    )
    workflow = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Raw workflow YAML/JSON string.",
        default="",
    )

    def validate_url(self, value):
        if value == "":
            return ""

        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            raise serializers.ValidationError("Only http and https are allowed")
        if not parsed.hostname:
            raise serializers.ValidationError("URL must include a host")
        return value

    def validate(self, attrs):
        provided_count = sum(
            [
                attrs.get("file") is not None,
                bool(attrs.get("url")),
                bool(attrs.get("workflow")),
            ]
        )
        if provided_count != 1:
            raise serializers.ValidationError(
                "Provide exactly one input source: file, url, or workflow."
            )
        return attrs


class WorkflowGraphElementsSerializer(serializers.Serializer):
    nodes = serializers.ListField(child=serializers.DictField())
    edges = serializers.ListField(child=serializers.DictField())


class WorkflowGraphResponseSerializer(serializers.Serializer):
    directed = serializers.BooleanField()
    multigraph = serializers.BooleanField()
    elements = WorkflowGraphElementsSerializer()

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if "data" in instance:
            representation["data"] = instance["data"]
        return representation
