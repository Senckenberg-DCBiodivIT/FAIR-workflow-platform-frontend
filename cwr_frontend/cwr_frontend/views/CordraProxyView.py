from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import classonlymethod
from django.views import View
import requests
from urllib.parse import urljoin


class CordraProxyView(View):

    upstream = None # url to forward requests to
    path = None  # path to remove from request url before forwarding

    def get(self, request, **kwargs):
        if request.method == "GET":
            relative_url = request.path[len(self.path)+1:]

            url = urljoin(self.upstream, relative_url)
            print(url)
            response = requests.get(f"{url}", request.GET, verify=False)
            response.raise_for_status()
            return HttpResponse(response.content, content_type=response.headers["content-type"])
        else:
            return HttpResponse(status=405)
