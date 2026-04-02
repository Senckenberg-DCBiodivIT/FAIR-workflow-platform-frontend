from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer, JSONRenderer
from django.http import JsonResponse, HttpResponseBase
from django.conf import settings
from django.core.exceptions import ValidationError
from requests import HTTPError, ConnectionError, RequestException
from urllib.parse import urlparse
import requests
from typing import Optional, Any
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from cwr_frontend.rocrate_io import get_crate_workflow_from_zip, as_ROCrate
from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector
from cwr_frontend.cordra.CordraConnector import CordraConnector
from .serializers import (
    WorkflowGraphRequestSerializer,
    WorkflowGraphResponseSerializer,
    WorkflowStatusSerializer,
    WorkflowSubmissionSerializer,
)
from .models import ApiKeyIdentity, CustomAPIKey
from .permissions import HasCustomAPIKey


def workflow_status_response(
    status: str,
    workflow_id: Optional[str] = None,
    details: Optional[dict] = None,
    status_code: int = 200,
) -> Response:
    data: dict[str, Any] = {"status": status}
    if workflow_id is not None:
        data['workflow_id'] = workflow_id  
    if details is not None:
        data['details'] = details    
    serializer = WorkflowStatusSerializer(data)
    return Response(serializer.data, status=status_code)


class ZipRenderer(BaseRenderer):
    media_type = "application/zip"
    format = "zip"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class SubmitWorkflowView(APIView):

    _connector = WorkflowServiceConnector()
    permission_classes = [HasCustomAPIKey]

    @extend_schema(
        description="Submit a new workflow RO-Crate for execution.",
        summary="Submit a new workflow RO-Crate for execution.",
        request={
            "multipart/form-data": WorkflowSubmissionSerializer,
        },
        parameters=[
            OpenApiParameter(
                name="param-*",
                location=OpenApiParameter.QUERY, # Or FORM if submitted in body
                description="Dynamic parameters to override workflow defaults. Format: param-KEY=VALUE",
                required=False,
                type=str
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Workflow Status.",
                response=WorkflowStatusSerializer,
            ),
        },
        tags=["Workflows"],
    )
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

    @extend_schema(
        description="Check workflow execution status.",
        summary="Check workflow execution status.",
        responses={
            200: OpenApiResponse(
                description="Workflow Status.",
                response=WorkflowStatusSerializer,
            ),
        },
        tags=["Workflows"],
    )
    def get(self, request, workflow_id) -> Response:

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
    renderer_classes = [ZipRenderer, JSONRenderer]

    def __init__(
        self,
        prefix=settings.CORDRA["PREFIX"],
        user=settings.CORDRA["USER"],
        password=settings.CORDRA["PASSWORD"],
    ):
        self.user = user
        self.password = password
        self.prefix = prefix
        self._connector = CordraConnector(user=user, password=password)

    @extend_schema(
        summary="Download completed workflow as RO-Crate.",
        description="Download completed workflow as RO-Crate. Use `format=zip` (default) to receive a ZIP archive including all files or `format=json` to receive the RO-Crate metadata as JSON-LD.",
        responses={
            200: OpenApiResponse(
                description="Workflow RO-Crate. Returns a ZIP archive when `format=zip` or JSON-LD when `format=json`.",
                response={
                    "application/zip": {"type": "string", "format": "binary"},
                    "application/json": {"type": "object"},
                },
            ),
            400: OpenApiResponse(description="Invalid format parameter."),
            404: OpenApiResponse(description="Workflow not found."),
        },
        tags=["Workflows"],
        parameters=[
            OpenApiParameter(
                name="format",
                description="Output format. `zip` returns a ZIP archive (default), `json` returns JSON-LD metadata.",
                required=False,
                type=OpenApiTypes.STR,
                enum=["zip", "json"],
                default="zip",
            ),
        ],
    )
    def get(self, request, workflow_id) -> HttpResponseBase:
        workflow_id = f"{self.prefix}/{workflow_id}"
        format = request.GET.get("format", "zip")
        if format == "json":
            download = False
        elif format == "zip":
            download = True
        else:
            return JsonResponse(
                {
                    "detail": "Invalid format parameter. Supported values are 'zip' and 'json'."
                },
                status=400,
            )

        try:
            self._connector.get_object_by_id(workflow_id)

        except HTTPError as e:
            # Cordra responds with 401 if not a public object is not found.
            if e.response.status_code == 401 or e.response.status_code == 404:
                return JsonResponse(
                    {"detail": f"Workflow {workflow_id} not found"}, status=404
                )
            return JsonResponse({"detail": e.response.text}, status=500)
        except ConnectionError:
            return JsonResponse({"detail": "Object store not available"}, status=500)

        return as_ROCrate(
            request,
            workflow_id,
            download=download,
            connector=self._connector,
            workflow_only=False,
            nested=True,
        )


class WorkflowGraphView(APIView):
    """
    Returns a Cytoscape-compatible graph JSON for an input workflow.

    Accepts exactly one of:
    - multipart file upload: field name file
    - JSON/form with url: URL to a workflow YAML/JSON resource
    - JSON/form with workflow: raw workflow YAML/JSON string
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._workflow_service = WorkflowServiceConnector()

    def _build_graph(
        self,
        *,
        workflow_url: str | None,
        workflow_raw: str | None,
        uploaded_file=None,
    ) -> tuple[dict[str, Any], int]:
        import yaml

        yaml_bytes: bytes | None = None
        filename = "workflow.yaml"

        if uploaded_file is not None:
            yaml_bytes = uploaded_file.read()
            if uploaded_file.name:
                filename = uploaded_file.name
        elif workflow_url:
            parsed = urlparse(workflow_url)
            candidate_name = parsed.path.split("/")[-1] if parsed.path else ""
            if candidate_name:
                filename = candidate_name
            try:
                response = requests.get(workflow_url, timeout=20, verify=False)
                if response.status_code == 404:
                    return {"detail": f"Workflow URL not found: {workflow_url}"}, 404

                response.raise_for_status()
                yaml_bytes = response.content
            except RequestException:
                return {"detail": "Failed to fetch workflow from provided URL."}, 502
        else:
            yaml_bytes = str(workflow_raw).encode("utf-8")

        if not yaml_bytes:
            return {"detail": "Workflow input is empty."}, 400

        try:
            parsed_yaml = yaml.safe_load(yaml_bytes)
            if parsed_yaml is None:
                return {"detail": "Workflow YAML is empty after parsing."}, 400
        except yaml.YAMLError as exc:
            return {"detail": f"Invalid YAML: {exc}"}, 400

        try:
            graph = self._workflow_service.visualize_workflow(
                yaml_bytes,
                filename=filename,
            )
        except RequestException:
            return {"detail": "Workflow service failed to generate graph."}, 502

        return graph, 200

    @extend_schema(
        summary="Generate workflow graph from file, URL, or raw YAML.",
        description=(
            "POST endpoint. Provide exactly one of file, url, or workflow. "
            "Validates YAML and returns Cytoscape-compatible graph JSON."
        ),
        request={
            "application/json": WorkflowGraphRequestSerializer,
            "multipart/form-data": WorkflowGraphRequestSerializer,
            "application/x-www-form-urlencoded": WorkflowGraphRequestSerializer,
        },
        responses={
            200: OpenApiResponse(
                description="Cytoscape-compatible graph JSON.",
                response=WorkflowGraphResponseSerializer,
            ),
            400: OpenApiResponse(
                description="Missing input, multiple inputs, empty input, or invalid YAML."
            ),
            404: OpenApiResponse(description="Workflow URL not found."),
            502: OpenApiResponse(description="Upstream service error."),
        },
        tags=["Workflows"],
    )
    def post(self, request) -> Response:
        serializer = WorkflowGraphRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        graph_payload, status_code = self._build_graph(
            workflow_url=serializer.validated_data.get("url"),
            workflow_raw=serializer.validated_data.get("workflow"),
            uploaded_file=serializer.validated_data.get("file"),
        )

        if status_code != 200:
            return Response(graph_payload, status=status_code)

        response_serializer = WorkflowGraphResponseSerializer(graph_payload)
        return Response(response_serializer.data)