# serializers.py

from rest_framework import serializers

class WorkflowStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    workflow_id = serializers.UUIDField(required = False)
    details = serializers.DictField(required = False)


class WorkflowSubmissionSerializer(serializers.Serializer):
    rocratefile = serializers.FileField(required=True )
    dry_run = serializers.BooleanField(required = False, default = False)
    webhook_url = serializers.URLField(required = False, default = None)