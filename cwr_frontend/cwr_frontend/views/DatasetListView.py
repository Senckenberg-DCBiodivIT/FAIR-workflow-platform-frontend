from datetime import datetime
from typing import Any

from django.core.paginator import Paginator, Page, EmptyPage
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView
from django.shortcuts import render
import logging

from django_signposting.utils import add_signposts
from signposting import Signpost, LinkRel

from cwr_frontend.cordra.CordraConnector import CordraConnector


class DatasetListView(TemplateView):
    template_name = "dataset_list.html"
    _connector = CordraConnector()

    _logger = logging.getLogger(__name__)

    class DatasetPaginator(Paginator):
        def __init__(self, connector: CordraConnector, page_size, list_all):
            self.connector = connector
            self.page_size = page_size
            self.list_all = list_all
            self._count = None
            self._cached_page = None
            super().__init__([], page_size)

        @property
        def count(self):
            if self._count == None:
                response = self.connector.list_datasets(1, self.page_size, self.list_all)
                self._count = response["size"]
                self._cached_page = self._results_to_page(response["results"], 0)
            return self._count

        def page(self, number):
            number = self.validate_number(number)
            if self._cached_page is not None and self._cached_page.number == number:
                return self._cached_page

            response = self.connector.list_datasets(number-1, self.page_size, self.list_all)
            return self._results_to_page(response["results"], number)

        def _results_to_page(self, results: dict[str, Any], page_num: int) -> Page:
            items_reduced = []
            for item in results:
                id = item["id"]
                if id is None:
                    raise Exception(f"Dataset has no valid id for {item}")

                content = item["content"]
                if "name" in content:
                    name = content["name"]
                else:
                    self._logger.warning(f"Dataset has no valid name for {item}")
                    name = id

                items_reduced.append(dict(
                    id=id,
                    name=name,
                    description=content.get("description", ""),
                    license=content.get("license", None),
                    file_count=len(content.get("hasPart", [])),
                    has_workflow="mainEntity" in content,
                    has_provenance=len(content.get("mentions", [])) > 0 or "isPartOf" in content,
                    date_modified=datetime.strptime(content["dateModified"], "%Y-%m-%dT%H:%M:%S.%fZ"),
                    date_created=datetime.strptime(content["dateCreated"], "%Y-%m-%dT%H:%M:%S.%fZ"),
                ))
            return Page(items_reduced, page_num, self)

    def get(self, request, **kwargs):
        page_num = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 20))
        show_nested = request.GET.get("nested", "true").lower() == "true"
        paginator = self.DatasetPaginator(self._connector, page_size, show_nested)
        try:
            page = paginator.page(page_num)
        except EmptyPage as e:
            if page_num > 1:
                return HttpResponseRedirect(reverse("dataset_list"))
            else:
                page = Page([], 1, paginator)

        # render response
        context = {
            "page": page,
            "nested": show_nested,
            "sd": self._jsonld(page, request),
        }
        response = render(request, self.template_name, context)
        if page is not None:
            add_signposts(
                response,
                Signpost(LinkRel.type, "https://schema.org/CollectionPage"),
                *[Signpost(LinkRel.item, request.build_absolute_uri(reverse("dataset_detail", args=[item["id"]]))) for item in page.object_list])
        return response

    def _jsonld(self, page, request):
        return {
            "@context": "https://schema.org/",
            "@type": "DataCatalog",
            "@id": request.build_absolute_uri(reverse("dataset_list")),
            "name": "Agriculture and climate change datasets",
            "description": "A collection of datasets from the agriculture and climate change use case at Destination Earth. Datasets for crop wild relatives",
            "keywords": ["Destination Earth", "BioDT", "Crop wild relatives", "CWR", "RO-Crate", "FAIR Digital Objects"],
            "author": {
                "@id": "https://orcid.org/0000-0001-9447-460X",
                "@type": "Person",
                "name": "Daniel Bauer",
                "affiliation": "Senckenberg Society for Nature Research"
            },
            "publication": {
                "@id": "https://doi.org/10.3897/biss.8.134479",
            }

        }