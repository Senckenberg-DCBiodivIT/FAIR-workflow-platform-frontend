from typing import Any
from urllib.parse import urlparse

import requests
from requests import RequestException
import yaml

from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector

def build_workflow_graph(
    *,
    workflow_url: str | None,
    workflow_raw: str | None,
    uploaded_file=None,
) -> tuple[dict[str, Any], int]:
    
    workflow_service = WorkflowServiceConnector()

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
        graph = workflow_service.visualize_workflow(
            yaml_bytes,
            filename=filename,
        )
    except RequestException:
        return {"detail": "Workflow service failed to generate graph."}, 502

    return graph, 200
