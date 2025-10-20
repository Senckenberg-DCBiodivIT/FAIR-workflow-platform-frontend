import io
import ssl
import tempfile
import zipfile
from typing import Any

import django
import requests
import yaml
from django.core.exceptions import ValidationError
from django.http import HttpResponseBase, JsonResponse, StreamingHttpResponse
from django.urls import reverse
from rocrate.rocrate import ROCrate

from cwr_frontend.cordra.CordraConnector import CordraConnector
from cwr_frontend.rocrate_builder import build_ROCrate


def get_crate_workflow_from_zip(file) -> tuple[ROCrate, dict[str, Any]]:
        # check if this is a zip file
        if (file.content_type not in ['application/zip', 'application/octet-stream']):
            raise ValidationError("File is not a zip file")

        # assert zip file is valid
        try:
            bytes = io.BytesIO(file.read())
            zipfile.ZipFile(bytes)
            file.seek(0)
        except zipfile.BadZipFile as e:
            file.close()
            raise ValidationError("File is not a zip file")

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
                    raise ValidationError("Workflow file not found in RO-Crate")
                
                # check if license is defined
                if not "license" in crate.root_dataset:
                    raise ValidationError("License not defined in RO-Crate")

                return crate, workflow
            
def get_crate_workflow_from_id(request, crate_id):
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

def _build_ROCrate(connector, request, dataset_id: str, objects: dict[str, dict[str, Any]], with_preview: bool, detached: bool, workflow_only=False) -> ROCrate:
    remote_urls = {}
    for cordra_id in objects:
        if "contentUrl" in objects[cordra_id]:
            url = request.build_absolute_uri(connector.get_object_abs_url(cordra_id, objects[cordra_id]["contentUrl"]))
            remote_urls[cordra_id] = url
        elif "identifier" in objects[cordra_id]:
            url = request.build_absolute_uri(connector.get_object_abs_url(cordra_id))
            remote_urls[cordra_id] = url
        elif "Dataset" in objects[cordra_id]["@type"]:
            url = request.build_absolute_uri(reverse("dataset_detail", args=[cordra_id]))
            remote_urls[cordra_id] = url
            if "isPartOf" in objects[cordra_id]:
                for parent_id in objects[cordra_id]["isPartOf"]:
                    remote_urls[parent_id] = request.build_absolute_uri(reverse("dataset_detail", args=[parent_id]))
    crate = build_ROCrate(dataset_id, objects, remote_urls=remote_urls, with_preview=with_preview, detached=detached, workflow_only=workflow_only)
    return crate

def as_ROCrate(request, id: str, download: bool, connector: CordraConnector, workflow_only=False, nested=False) -> HttpResponseBase:
    """ return a downloadable zip in RO-Crate format from the given dataset entity
    the zip file is build on the fly by streaming payload objects directly from the api

    params:
        id - the pid of the dataset
        objects - list of digital objects of the dataset
        download - return a downloadable zip in RO-Crate format
        connector - CordraConnector
    """
    objects = connector.resolve_objects(id, nested=nested, workflow_only=workflow_only)
    crate = _build_ROCrate(connector, request, id, objects, with_preview=download, detached=not download, workflow_only=workflow_only)

    if not download:
        # return just the metadata
        return JsonResponse(crate.metadata.generate())
    else:
        try:
            ssl._create_default_https_context = ssl._create_unverified_context
            archive_name = f'{"_".join(id.split('/')[1:])}.zip'
            response = StreamingHttpResponse(crate.stream_zip(), content_type="application/zip")
            response["Content-Disposition"] = f"attachment; filename={archive_name}"
            return response
        finally:
            # restore default ssl context
            ssl._create_default_https_context = ssl._create_default_https_context