# serializers.py

from rest_framework import serializers
import re


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
    webhook_url = serializers.URLField(
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
        PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
        ALLOWED_WEBHOOK_PLACEHOLDERS = {"workflow_id"}
        fields = set(PLACEHOLDER_RE.findall(value))

        unknown = fields - ALLOWED_WEBHOOK_PLACEHOLDERS
        if unknown:
            raise serializers.ValidationError(
                f"Unsupported webhook URL placeholders: {', '.join(sorted(unknown))}. Please use a supported placeholder from the list: {ALLOWED_WEBHOOK_PLACEHOLDERS}"
            )
        return value
