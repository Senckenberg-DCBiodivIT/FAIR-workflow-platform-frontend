from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin
import requests
from requests.auth import HTTPBasicAuth
import yaml
from django.conf import settings
from rest_framework.exceptions import APIException


class WorkflowServiceConnector:

    def __init__(self, base_url=settings.WORKFLOW_SERVICE["URL"], username=settings.WORKFLOW_SERVICE["USER"], password=settings.WORKFLOW_SERVICE["PASSWORD"], verify_ssl=False):
        self._base_url = base_url
        if not self._base_url.endswith("/"):
            self._base_url += "/"
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl

    def check_workflow(self, workflow: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        files = {"file": ("workflow.yaml", yaml.dump(workflow, indent=2))}
        response = requests.post(urljoin(self._base_url, "workflow/check"), files=files, auth=HTTPBasicAuth(self._username, self._password), verify=self._verify_ssl)
        if response.status_code != 200:
            if response.status_code == 400 and "detail" in response.json():
                return False, response.json()
            else:
                response.raise_for_status()
        return True, response.json()

    def submit_workflow(self, workflow: dict[str, Any], title: str, description: str, submitter_name: str, submitter_id: str, license: Optional[str] = None, keywords: list[str] = [], override_parameters: dict[str, str] = {}, dry_run: bool = False, webhook_url: Optional[str] = None) -> tuple[bool, dict[str, Any]]:

        files = {"file": ("workflow.yaml", yaml.dump(workflow, indent=2))}
        form_data = {
            "title": title,
            "description": description,
            "submitterName": submitter_name,
            "submitterId": submitter_id,
            "license": license,
            "keywords": ",".join(keywords),
            "overrideParameters": ",".join([f"{key}:{value}" for key, value in override_parameters.items()]),
            "dryRun": dry_run,
            "webhookURL" : webhook_url,
        }
        response = requests.post(urljoin(self._base_url, "workflow/submit"), files=files, data=form_data, auth=HTTPBasicAuth(self._username, self._password), verify=self._verify_ssl)
        if response.status_code != 200:
            if 400 <= response.status_code < 500:
                return False, response.json()
            else:
                response.raise_for_status()
        return True, response.json()

    def list_workflows(self) -> list[dict[str, Any]]:
        """ retrieve list of objects from cordra """
        url = f'{urljoin(self._base_url, "workflow/list")}'
        response = requests.get(url, auth=HTTPBasicAuth(self._username, self._password), verify=self._verify_ssl)
        if response.status_code != 200:
            raise Exception(response.text)

        json = response.json()
        for i in range(len(json)):
            json[i]["createdAt"] = datetime.strptime(json[i]["createdAt"], "%Y-%m-%dT%H:%M:%SZ")
            json[i]["startedAt"] = datetime.strptime(json[i]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
            if "finishedAt" in json[i] and json[i]["finishedAt"] is not None:
                json[i]["finishedAt"] = datetime.strptime(json[i]["finishedAt"], "%Y-%m-%dT%H:%M:%SZ")
        return json
    
    def get_workflow_detail(self, workflow_id:str):
        """
        Get details of a specific workflow
        """
        url = f'{urljoin(self._base_url, f"workflow/detail/{workflow_id}")}'
        response = requests.get(url, auth=HTTPBasicAuth(self._username, self._password), verify=self._verify_ssl)
        if response.status_code != 200:
            raise APIException(detail=f"Error from workflow service: {response.text}")

        json = response.json()
        return json 