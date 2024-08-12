import logging

from django.views.generic import TemplateView

from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector


class WorkflowListView(TemplateView):
    template_name = "workflow_list.html"

    _logger = logging.getLogger(__name__)
    _connector = WorkflowServiceConnector()

    def get(self, request):
        raise Exception()
