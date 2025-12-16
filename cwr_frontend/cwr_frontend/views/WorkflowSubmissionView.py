import json
import logging

import yaml
from django.conf import settings

from django.shortcuts import render
from django.views.generic import TemplateView
from allauth.socialaccount.models import SocialAccount
from cwr_frontend.rocrate_io import get_crate_workflow_from_zip, get_crate_workflow_from_id
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


    def step_2(self, request):
        self._logger.info("Render step 2")

        if request.method == "POST":
            file = request.FILES["rocratefile"]
            crate, workflow = get_crate_workflow_from_zip(file)
        else:
            crate_id = request.GET["crate_id"]
            crate, workflow = get_crate_workflow_from_id(request, crate_id)

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
            submitter_id=orcid,
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

