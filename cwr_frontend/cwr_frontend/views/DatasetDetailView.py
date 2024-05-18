from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
from django.urls import reverse
from cwr_frontend.utils import add_signpost
import requests
from django.http import StreamingHttpResponse
import zipstream
import json
import io
from django.core.files.temp import NamedTemporaryFile

class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"

    def path_to_abs_url(self, request, id: str, item_name: str) -> str:
        return request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])) + f"?payload={item_name}"

    def get(self, request, **kwargs):
        id = request.GET.get("id", None)

        # get metadata oject from cordra
        url = settings.CORDRA["URL"] + "/objects/" + id
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        obj = response.json()

        response_format = request.GET.get("format", None)
        if response_format == "ROCrate":
            return self.to_ROCrate(request, id, obj)
        else:
            return self.render(request, id, obj)

    def render(self, request, id, obj):
        """ Return a html representation with signposts from the given dataset entity"""
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))

        dataset_author_id = dataset["author"]["@id"]
        author = next((elem for elem in obj["@graph"] if elem["@id"] == dataset_author_id), None)
        author_name = author["name"]

        signposts = {"item": [
            (request.build_absolute_uri() + "&format=ROCrate", "application/zip"),
        ]}

        # render content
        context = {
            "id": id,
            "name": dataset["name"],
            "description": dataset["description"],
            "keywords": dataset["keywords"],
            "datePublished": dataset["datePublished"],
            "author": author_name,
            "author_id": dataset_author_id,
            "images": [],
            "rocrate": request.build_absolute_uri() + "&format=ROCrate"
        }

        for part in dataset["hasPart"]:
            part_id = part["@id"]
            item = next((elem for elem in obj["@graph"] if elem["@id"] == part_id), None)
            if item is None:
                continue
            item_id = part_id
            item_type = item["encodingFormat"]
            if (item_type.startswith("image")):
                item_abs_url = self.path_to_abs_url(request, id, item_id)
                signposts["item"].append((item_abs_url, item_type))
                context["images"].append(item_abs_url)

        response = render(request, self.template_name, context)

        # attach signposting headers
        signposts |= {
            "cite-as": [(request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])), "related")],
            "author": [dataset_author_id],
            "license": [dataset["license"]["@id"]],
        }
        add_signpost(response, signposts)

        return response

    def to_ROCrate(self, request, id: str, obj: dict) -> StreamingHttpResponse:
        """ Return a downloadable zip in RO-Crate format from the given dataset entity"""

        # get list of files to add to the archive
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))
        files_to_add = {}
        for item in dataset["hasPart"]:
            item_id = item["@id"]
            item_abs_url = self.path_to_abs_url(request, id, item_id)
            files_to_add[item_id] = item_abs_url

        # stream files directliy into the zip respones
        # this does not allocate memory on the server
        zs = zipstream.ZipFile(mode="w", compression=zipstream.ZIP_DEFLATED)
        for file_name in files_to_add:
            response = requests.get(files_to_add[file_name], verify=False, stream=True)
            if response.status_code == 200:
                zs.write_iter(file_name, response.iter_content(chunk_size=1024))

        # also add ro-crate-metadata.json to the archive
        zs.writestr("ro-crate-metadata.json", str.encode(json.dumps(obj, indent=2)))
        # zs.write_iter("ro-crate-metadata.json", metadata_file.read())#json.dumps(obj, indent=2))

        response = StreamingHttpResponse(zs, content_type="application/zip")
        response['Content-Disposition'] = f'attachment; filename={id.replace("/", "_")}.zip'
        return response


