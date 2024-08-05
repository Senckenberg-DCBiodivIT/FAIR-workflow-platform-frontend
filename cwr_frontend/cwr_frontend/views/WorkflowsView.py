import io
import logging
import tempfile
import zipfile

import yaml
from django.core.files.storage import FileSystemStorage
from rocrate.model import DataEntity
from rocrate.rocrate import ROCrate

from django.core.exceptions import BadRequest
from django.shortcuts import render
from django.views.generic import TemplateView
from allauth.socialaccount.models import SocialAccount

class WorkflowsView(TemplateView):
    template_name = "user_workflows.html"

    _logger = logging.getLogger(__name__)

    def get(self, request, **kwargs):
        step = kwargs.get("step", 1)
        context = {}
        try:
            social_account = SocialAccount.objects.get(user=request.user, provider="orcid")
            context["user"] = {
                "username": f"{social_account.user.first_name} {social_account.user.last_name}".rstrip(),
                "orcid": social_account.uid
            }
        except SocialAccount.DoesNotExist:
            raise Exception("User has no ORCID")

        context["workflow"] = request.session.get("workflow", None)
        context["step"] = step
        return render(request, self.template_name, context)

    def post(self, request, **kwargs):
        if "rocratefile" in request.FILES:
            return self.handle_crate_upload(request)
        elif "submit" in request.POST:
            request.session["workflow"] = None
            return self.get(request, step=3)
        elif "cancel" in request.POST:
            request.session["workflow"] = None
            return self.get(request, step=1)
        else:
            raise Exception("Invalid request")

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
                    # TODO validate with backend
                    request.session["workflow"] = workflow
                    return self.get(request, step=2)

