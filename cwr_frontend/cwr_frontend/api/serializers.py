# serializers.py

from rest_framework import serializers

class WorkflowStatusSerializer(serializers.Serializer):
    workflow_id = serializers.UUIDField()
    status = serializers.CharField()
