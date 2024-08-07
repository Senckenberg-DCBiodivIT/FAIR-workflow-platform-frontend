import io
import logging
import tempfile
import zipfile

import yaml
from rocrate.rocrate import ROCrate

from django.core.exceptions import BadRequest
from django.shortcuts import render
from django.views.generic import TemplateView
from allauth.socialaccount.models import SocialAccount

from cwr_frontend.workflowservice.WorkflowServiceConnector import WorkflowServiceConnector


class WorkflowsView(TemplateView):
    template_name = "user_workflows.html"

    _logger = logging.getLogger(__name__)
    _connector = WorkflowServiceConnector()

    def get(self, request, **kwargs):
        step = kwargs.get("step", 1)
        context = {}
        try:
            social_account = SocialAccount.objects.get(user=request.user, provider="orcid")
            context["username"] = f"{social_account.user.first_name.title()} {social_account.user.last_name.title()}"
            context["orcid"] = social_account.uid
        except SocialAccount.DoesNotExist:
            raise Exception("User has no ORCID")

        if step == 2:
            context["workflow"] = request.session.get("workflow", None)
            if not request.session.get("workflow_check_status", True):
                context["workflow_check_result"] = request.session.get("workflow_check_result")
        elif step == 3:
            if not request.session.get("submit_status", True):
                context["submit_result"] = request.session.get("submit_result")

        context["step"] = step
        return render(request, self.template_name, context)

    def post(self, request, **kwargs):
        if "rocratefile" in request.FILES:
            return self.handle_crate_upload(request)
        elif "submit" in request.POST:
            social_acc = SocialAccount.objects.get(user=request.user, provider="orcid")
            name = social_acc.user.first_name.title() + " " + social_acc.user.last_name.title()
            orcid = social_acc.uid
            submit_status, submit_result = self._connector.submit_workflow(request.session["workflow"], submitter_name=name, submitter_orcid=orcid, dry_run=request.POST.get("dryrun", None)  == "DryRun")
            request.session["workflow"] = None
            request.session["submit_status"] = submit_status
            request.session["submit_result"] = submit_result
            return self.get(request, step=3)
        elif "cancel" in request.POST:
            request.session["workflow"] = None
            return self.get(request, step=1)
        else:
            return self.get(request)

    def handle_crate_upload(self, request):
        file = request.FILES["rocratefile"]

        # check if this is a zip file
        if (file.content_type != "application/zip"):

            raise BadRequest("File is not a zip file")
        with file as f:
            # check if zip is broken or not valid zip file
            try:
                bytes = io.BytesIO(f.read())
                zipfile.ZipFile(bytes)
            except zipfile.BadZipFile as e:
                raise BadRequest("File is not a zip file")

            # parse ro crate and find workflow file
            f.seek(0)
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                for chunk in file.chunks():
                    tmp.write(chunk)
                tmp.flush()

                crate = ROCrate(tmp.name)
                workflow_path = crate.source / crate.root_dataset["mainEntity"]["name"]

                if workflow_path.exists():
                    workflow = yaml.load(open(workflow_path, "r"), Loader=yaml.CLoader)
                    workflow_lint_status, workflow_lint_result = self._connector.check_workflow(workflow)
                    # TODO supply parameters for workflow based on formal parameters?
                    request.session["workflow_check_status"] = workflow_lint_status
                    request.session["workflow_check_result"] = workflow_lint_result
                    request.session["workflow"] = workflow
                    return self.get(request, step=2)

