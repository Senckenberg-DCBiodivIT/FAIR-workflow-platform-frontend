import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import django
import yaml
from django.conf import settings
import requests
from django.urls import reverse
from rocrate.rocrate import ROCrate

from django.core.exceptions import BadRequest
from django.shortcuts import render
from django.views.generic import TemplateView
from allauth.socialaccount.models import SocialAccount

from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector


class WorkflowSubmissionView(TemplateView):
    template_name = "submit_workflow.html"

    _logger = logging.getLogger(__name__)
    _connector = WorkflowServiceConnector()

    def handle_request(self, request, **kwargs):
        if request.method == "POST":
            if "rocratefile" in request.FILES:
                return self.step_2(request)
            elif "cancel" in request.POST:
                request.session = {}
                return self.step_1(request)
            elif "submit" in request.POST and "workflow" in request.session:
                return self.step_3(request)
        elif "crate_id" in request.GET:
            return self.step_2(request)

        return self.step_1(request)

    def step_1(self, request):
        self._logger.info("Render step 1")
        context = {"step": 1}
        return render(request, self.template_name, context=context)

    def get_crate_workflow_from_zip(self, file) -> tuple[ROCrate, dict[str, Any]]:
        # check if this is a zip file
        if (file.content_type != "application/zip"):
            raise BadRequest("File is not a zip file")

        # assert zip file is valid
        try:
            bytes = io.BytesIO(file.read())
            zipfile.ZipFile(bytes)
            file.seek(0)
        except zipfile.BadZipFile as e:
            file.close()
            raise BadRequest("File is not a zip file")

        # Parse RO crate and extract workflow
        with file as f:
            # parse ro-crate and find workflow file
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                if isinstance(f, django.core.files.base.File):
                    # django file object
                    chunks = f.chunks()
                else:
                    # object is http request
                    chunks = f.iter_content(chunk_size=8192)

                for chunk in chunks:
                    tmp.write(chunk)
                tmp.flush()

                crate = ROCrate(tmp.name)
                workflow_path = crate.source / crate.root_dataset["mainEntity"].id

                # check workflow file and set it to the session
                if workflow_path.exists():
                    workflow = yaml.load(open(workflow_path, "r"), Loader=yaml.CLoader)
                else:
                    raise Exception("Workflow file not found in RO-Crate")

                return crate, workflow

    def get_crate_workflow_from_id(self, request, crate_id):
        crate_url = request.build_absolute_uri(reverse("dataset_detail", kwargs={"id": crate_id}))
        crate_url += "?format=ROCrate"
        response = requests.get(crate_url, stream=True, verify=False)
        response.raise_for_status()
        with tempfile.TemporaryDirectory(delete=True) as tmp_dir:
            file = open(tmp_dir + "/ro-crate-metadata.json", "wb")
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
            file.flush()

            crate = ROCrate(source=tmp_dir)
            workflow_url = crate.root_dataset["mainEntity"].id
            workflow_response = requests.get(workflow_url, verify=False)
            workflow_response.raise_for_status()
            workflow = yaml.load(workflow_response.content, Loader=yaml.CLoader)
            return crate, workflow

    def step_2(self, request):
        self._logger.info("Render step 2")

        if request.method == "POST":
            file = request.FILES["rocratefile"]
            crate, workflow = self.get_crate_workflow_from_zip(file)
        else:
            crate_id = request.GET["crate_id"]
            crate, workflow = self.get_crate_workflow_from_id(request, crate_id)

        workflow_name = crate.root_dataset.get("name", "Workflow")
        workflow_description = crate.root_dataset.get("description", None)
        workflow_keywords = ",".join(crate.root_dataset.get("keywords", []))
        if "license" in crate.root_dataset:
            license = crate.root_dataset["license"]
            workflow_license = license if isinstance(license, str) else license.id
        else:
            workflow_license = None

        # check if workflow is valid
        workflow_lint_status, workflow_lint_result = self._connector.check_workflow(workflow)

        # Update session with workflow
        request.session["workflow"] = workflow
        request.session["workflow_check_status"] = workflow_lint_status
        request.session["workflow_check_result"] = workflow_lint_result

        social_account = SocialAccount.objects.get(user=request.user, provider="orcid")
        licenses = [{"name": "No License", "url": None}] + [{"name": license["name"], "url": license["reference"].replace(".html", "")} for license in json.load(open(settings.BASE_DIR / "cwr_frontend/workflow_licenses.json", "r"))["licenses"]]
        if workflow_license not in [license["url"] for license in licenses]:
            workflow_license = None
        context = {
            "step": 2,
            "licenses": [{"name": "No License", "url": ""}] + [{"name": license["name"], "url": license["reference"].replace(".html", "")} for license in json.load(open(settings.BASE_DIR / "cwr_frontend/workflow_licenses.json", "r"))["licenses"]],
            "workflow": yaml.dump(workflow, indent=2),
            "workflow_title": workflow_name,
            "workflow_description": workflow_description,
            "workflow_keywords": workflow_keywords,
            "workflow_license": workflow_license,
            "username": f"{social_account.user.first_name.title()} {social_account.user.last_name.title()}",
            "orcid": social_account.uid,
            "parameters": [],
        }
        if not workflow_lint_status:
            context["workflow_error"] = workflow_lint_result
        else:
            context["parameters"] = dict([(param["name"], param["value"]) for param in workflow_lint_result["parameters"]])
        return render(request, self.template_name, context=context)

    def step_3(self, request):
        self._logger.info("Render step 3")
        social_acc = SocialAccount.objects.get(user=request.user, provider="orcid")
        name = social_acc.user.first_name.title() + " " + social_acc.user.last_name.title()
        orcid = social_acc.uid

        override_parameters = {}
        for key, value in request.POST.items():
            if key.startswith("param-"):
                param_name = key[len("param-"):]
                override_parameters[param_name] = value

        # submit workflow to workflow service
        submit_status, submit_result = self._connector.submit_workflow(
            request.session["workflow"],
            title=request.POST["title"],
            description=request.POST["description"],
            keywords=request.POST["keywords"].split(","),
            license=request.POST["license"],
            submitter_name=name,
            submitter_orcid=orcid,
            override_parameters=override_parameters,
            dry_run=request.POST.get("dryrun", None)  == "DryRun",
        )
        del request.session["workflow"]

        context = {
            "step": 3,
            "submit_status": submit_status,
            "submit_result": submit_result
        }
        return render(request, self.template_name, context)


    def get(self, request, **kwargs):
        return self.handle_request(request, **kwargs)

    def post(self, request, **kwargs):
        return self.handle_request(request, **kwargs)

