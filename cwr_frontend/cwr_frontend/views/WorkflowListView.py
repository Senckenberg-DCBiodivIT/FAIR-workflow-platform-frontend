import logging

from django.views.generic import TemplateView
from django.shortcuts import render
from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector


class WorkflowListView(TemplateView):
    template_name = "workflow_list.html"

    _logger = logging.getLogger(__name__)
    _connector = WorkflowServiceConnector()

    def get(self, request):
        workflows = self._connector.list_workflows()
        return render(request, self.template_name, context={"workflows": workflows})
