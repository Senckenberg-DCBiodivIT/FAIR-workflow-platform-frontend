from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import FileResponse
from drf_spectacular.utils import extend_schema

from uuid import uuid4

from cwr_frontend.rocrate_utils import get_crate_workflow_from_zip
from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector
from cwr_frontend.api.serializers import WorkflowStatusSerializer
from rest_framework_api_key.permissions import HasAPIKey

def workflow_status_response(workflow_id, status, status_code=200):
    data = {"workflow_id": workflow_id, "status": status}
    serializer = WorkflowStatusSerializer(data)
    return Response(serializer.data, status=status_code)


class SubmitWorkflowView(APIView):

    _connector = WorkflowServiceConnector()
    permission_classes = [HasAPIKey]
    
    @extend_schema(
        responses={200: WorkflowStatusSerializer}
    )
    def post(self, request):
        workflow_id = str(uuid4())
        file = request.FILES.get('rocratefile')
        dry_run = request.query_params.get('dry_run')

        crate, workflow = get_crate_workflow_from_zip(file = file)

        # check if workflow is valid
        workflow_lint_status, workflow_lint_result = self._connector.check_workflow(workflow)

        if not workflow_lint_status:
            # Or better return BadRequest?
            # Migh be useful to include result/details here
            status = "Invalid ROCrate"
            return workflow_status_response(workflow_id, status)
        
        override_parameters = {}
        for key, value in request.POST.items():
            if key.startswith("param-"):
                param_name = key[len("param-"):]
                override_parameters[param_name] = value
        
        submit_status, submit_result = self._connector.submit_workflow(
            workflow=workflow,
            title=workflow_id,
            description="empty description",
            # keywords=request.POST["keywords"].split(","),
            # license=request.POST["license"],
            override_parameters=override_parameters,
            submitter_name='Lena',
            submitter_orcid='123',
            dry_run=dry_run,
        )

        if not submit_status:
            status = "Failed"
            return workflow_status_response(workflow_id, status)

        if dry_run:
            status = "Valid Request"            
            return workflow_status_response(workflow_id, status)
        
        status = "Submitted"        
        return workflow_status_response(workflow_id, status)

class WorkflowStatusView(APIView):
    @extend_schema(
        responses={200: WorkflowStatusSerializer}
    )
    def get(self, request, workflow_id):

        status = 'placeholder'

        return workflow_status_response(workflow_id, status)


class WorkflowDownloadView(APIView):
    def get(self, request, workflow_id):

        file_path = '/home/lena/Downloads/cwr_0ea7316aa449cf745efc.zip'
        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="ro-crate.zip"'

        return response