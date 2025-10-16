from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404, StreamingHttpResponse
from django.conf import settings
from django.shortcuts import render
from django.views import View
from django.core.exceptions import ValidationError
from requests import HTTPError

from cwr_frontend.rocrate_io import get_crate_workflow_from_zip, as_ROCrate
from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector
from cwr_frontend.cordra.CordraConnector import CordraConnector
from cwr_frontend.api.serializers import WorkflowStatusSerializer, WorkflowSubmissionSerializer
from rest_framework_api_key.permissions import HasAPIKey

def workflow_status_response(status:str, workflow_id:str = None, details:dict = None, status_code:int=200):
    data = { "status": status}
    if workflow_id is not None:
        data['workflow_id'] = workflow_id  
    if details is not None:
        data['details'] = details    
    serializer = WorkflowStatusSerializer(data)
    return Response(serializer.data, status=status_code)

def swagger_ui_view(request):
    return render(request, 'swagger_ui.html')

class SubmitWorkflowView(APIView):

    _connector = WorkflowServiceConnector()
    permission_classes = [HasAPIKey]

    def post(self, request):
        serializer = WorkflowSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['rocratefile']
        dry_run = serializer.validated_data['dry_run']
        webhook_url = serializer.validated_data['webhook_url']

        try:
            crate, workflow = get_crate_workflow_from_zip(file = file)
        except ValidationError as e:
            return workflow_status_response(status = "Invalid RO-Crate", details = {'message':e.message}, status_code=400)
        

        # check if workflow is valid
        workflow_lint_status, workflow_lint_result = self._connector.check_workflow(workflow)

        if not workflow_lint_status:
            status = "Invalid workflow"
            return workflow_status_response(status, details=workflow_lint_result, status_code=400)
        
        override_parameters = {}
        for key, value in request.POST.items():
            if key.startswith("param-"):
                param_name = key[len("param-"):]
                override_parameters[param_name] = value

        license = crate.root_dataset["license"]
        workflow_license = license if isinstance(license, str) else license.id
        
        submit_status, submit_result = self._connector.submit_workflow(
            workflow=workflow,
            title=crate.root_dataset.get("name", "Workflow"),
            description=crate.root_dataset.get("description", None),
            keywords=crate.root_dataset.get("keywords", []),
            license=workflow_license,
            override_parameters=override_parameters,
            submitter_name='Lena',
            submitter_orcid='0000-0002-0487-2151',
            dry_run=dry_run,
            webhook_url=webhook_url,
        )

        if not submit_status:
            status = "Submission Failed"
            return workflow_status_response(status, details = submit_result, status_code=400)
        
        workflow_id = submit_result['workflow_id']

        if dry_run:
            status = "Valid Request"            
            return workflow_status_response(status, workflow_id)
        
        status = "Submitted"        
        return workflow_status_response(status, workflow_id)

class WorkflowStatusView(APIView):
    _connector = WorkflowServiceConnector()

    def get(self, request, workflow_id):

        wfl = self._connector.get_workflow_detail(workflow_id)
        status = wfl['status']

        return workflow_status_response(status, workflow_id)


class WorkflowDownloadView(View):
    def __init__(self, prefix=settings.CORDRA["PREFIX"], user=settings.CORDRA["USER"], password=settings.CORDRA["PASSWORD"]):
        self.user = user
        self.password = password
        self.prefix = prefix
        self._connector = CordraConnector(user = user, password=password)

    def get(self, request, workflow_id)->StreamingHttpResponse:
        workflow_id = f"{self.prefix}/{workflow_id}"
        try:
            self._connector.get_object_by_id(workflow_id)

        except HTTPError as e:
            # Cordra responds with 401 if not a public object is not found.
            if e.response.status_code == 401 or e.response.status_code == 404:
                raise Http404
            raise

        objects = self._connector.resolve_objects(workflow_id, nested=False, workflow_only=False)
        return as_ROCrate(request, workflow_id, objects, download=True, connector=self._connector)