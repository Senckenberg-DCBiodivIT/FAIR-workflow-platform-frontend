from django.http.response import HttpResponse


def add_signposts(response: HttpResponse, typed_links: list[tuple[str, str, str | None]]):
    """ inserts signposts as headers in the response
    params:
      result - the response object
      postings - map list of typed links [(url, rel, type)]
    """
    signpost = []
    for url, rel, type in typed_links:
        signpost.append(f"<{url}> ; rel=\"{rel}\"")
        if type is not None:
            signpost[-1] += f" ; type=\"{type}\""
    response["Link"] = " , ".join(signpost)

