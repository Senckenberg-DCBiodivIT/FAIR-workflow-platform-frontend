from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse, HttpResponseBase
from django.conf import settings
from django.shortcuts import render
from django.core.exceptions import ValidationError
from requests import HTTPError, ConnectionError
from typing import Optional, Any

from cwr_frontend.rocrate_io import get_crate_workflow_from_zip, as_ROCrate
from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector
from cwr_frontend.cordra.CordraConnector import CordraConnector
from .serializers import WorkflowStatusSerializer, WorkflowSubmissionSerializer
from .models import ApiKeyIdentity, CustomAPIKey
from .permissions import HasCustomAPIKey


def workflow_status_response(
    status: str, workflow_id: Optional[str] = None, details: Optional[dict] = None, status_code: int = 200
):
    data: dict[str, Any] = {"status": status}
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
    permission_classes = [HasCustomAPIKey]

    def post(self, request):
        serializer = WorkflowSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['rocratefile']
        dry_run = serializer.validated_data['dry_run']
        webhook_url = serializer.validated_data['webhook_url']
        force = serializer.validated_data['force']

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

        # Get submitter information from api key
        api_key = request.META["HTTP_API_KEY"]
        api_key_obj = CustomAPIKey.objects.get_from_key(api_key)
        submitter = ApiKeyIdentity.objects.get(id = api_key_obj.identity_id)

        submit_status, submit_result = self._connector.submit_workflow(
            workflow=workflow,
            title=crate.root_dataset.get("name", "Workflow"),
            description=crate.root_dataset.get("description", None),
            keywords=crate.root_dataset.get("keywords", []),
            license=workflow_license,
            override_parameters=override_parameters,
            submitter_name=submitter.name,
            submitter_id=submitter.get_url(),
            dry_run=dry_run,
            webhook_url=webhook_url,
            force=force,
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
    permission_classes = [HasCustomAPIKey]
    def __init__(self, prefix=settings.CORDRA["PREFIX"], user=settings.CORDRA["USER"], password=settings.CORDRA["PASSWORD"]):
        self.user = user
        self.password = password
        self.prefix = prefix
        self._cordra_connector = CordraConnector(user = user, password=password)
        self._argo_connector = WorkflowServiceConnector()

    def get(self, request, workflow_id):

        try:
            obj = self._cordra_connector.search_for_ids(ids=[self.prefix + "/" + workflow_id])
        except ConnectionError:
            return workflow_status_response(status = 'Server Error', details={'message': 'Object store not available'}, status_code=500)
        if len(obj) == 1:
            status = 'Succeeded'
        else:
            wfl = self._argo_connector.get_workflow_detail(workflow_id)
            status = wfl['status']
            if status == 'Succeeded' and len(obj) == 0:
                status = 'Ingestion pending'
        return workflow_status_response(status, workflow_id)


class WorkflowDownloadView(APIView):
    permission_classes = [HasCustomAPIKey]
    def __init__(self, prefix=settings.CORDRA["PREFIX"], user=settings.CORDRA["USER"], password=settings.CORDRA["PASSWORD"]):
        self.user = user
        self.password = password
        self.prefix = prefix
        self._connector = CordraConnector(user = user, password=password)

    def get(self, request, workflow_id) -> HttpResponseBase:
        workflow_id = f"{self.prefix}/{workflow_id}"
        try:
            self._connector.get_object_by_id(workflow_id)

        except HTTPError as e:
            # Cordra responds with 401 if not a public object is not found.
            if e.response.status_code == 401 or e.response.status_code == 404:
                return JsonResponse({"detail": f"Workflow {workflow_id} not found"}, status=404)
            return JsonResponse({"detail": e.response.text}, status=500)
        except ConnectionError:
            return JsonResponse({'detail': 'Object store not available'}, status=500)

        return as_ROCrate(request, workflow_id, download=True, connector=self._connector, workflow_only=False, nested=False)