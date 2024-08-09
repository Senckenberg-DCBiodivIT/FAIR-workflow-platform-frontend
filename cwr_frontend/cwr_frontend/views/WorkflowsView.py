import io
import logging
import tempfile
import zipfile
from pathlib import Path

import yaml
from rocrate.rocrate import ROCrate

from django.core.exceptions import BadRequest
from django.shortcuts import render
from django.views.generic import TemplateView
from allauth.socialaccount.models import SocialAccount

from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector


class WorkflowsView(TemplateView):
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
        return self.step_1(request)

    def step_1(self, request):
        self._logger.info("Render step 1")
        context = {"step": 1}
        return render(request, self.template_name, context=context)

    def step_2(self, request):
        self._logger.info("Render step 2")
        file = request.FILES["rocratefile"]

        # check if this is a zip file
        if (file.content_type != "application/zip"):
            raise BadRequest("File is not a zip file")

        # Parse RO crate and extract workflow
        with file as f:
            # assert zip file is valid
            try:
                bytes = io.BytesIO(f.read())
                zipfile.ZipFile(bytes)
            except zipfile.BadZipFile as e:
                raise BadRequest("File is not a zip file")

            # parse ro-crate and find workflow file
            f.seek(0)
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                for chunk in file.chunks():
                    tmp.write(chunk)
                tmp.flush()

                crate = ROCrate(tmp.name)
                workflow_path = crate.source / crate.root_dataset["mainEntity"].id

                # check workflow file and set it to the session
                if workflow_path.exists():
                    workflow = yaml.load(open(workflow_path, "r"), Loader=yaml.CLoader)
                else:
                    raise Exception("Workflow file not found in RO-Crate")

        # check if workflow is valid
        workflow_lint_status, workflow_lint_result = self._connector.check_workflow(workflow)

        # Update session with workflow
        request.session["workflow"] = workflow
        request.session["workflow_check_status"] = workflow_lint_status
        request.session["workflow_check_result"] = workflow_lint_result

        social_account = SocialAccount.objects.get(user=request.user, provider="orcid")
        context = {
            "step": 2,
            "workflow": yaml.dump(workflow, indent=2),
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
        submit_status, submit_result = self._connector.submit_workflow(request.session["workflow"], submitter_name=name, submitter_orcid=orcid, override_parameters=override_parameters, dry_run=request.POST.get("dryrun", None)  == "DryRun")
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

