# serializers.py

from rest_framework import serializers


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
        help_text="URL to be notified once the processing is complete.",
    )
    force = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Force re-execution if the same workflow was already submitted.",
    )
