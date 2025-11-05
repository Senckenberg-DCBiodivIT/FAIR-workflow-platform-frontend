import json
import re
from typing import Any

from pyld import jsonld
import requests
from pyld.jsonld import JsonLdError, parse_link_header, LINK_HEADER_REL
import string
import urllib.parse as urllib_parse
from django.core.cache import cache
import hashlib

def cached_frame(input: dict|list, frame: dict, cache_time=60 * 60 * 24, skip_cache=False):
    cache_key = hashlib.sha1(json.dumps([input, frame]).encode('utf-8')).hexdigest()
    if not skip_cache:
        response = cache.get(cache_key)
        if response is not None:
            return json.loads(response)
    framed = jsonld.frame(input, frame)
    cache.set(cache_key, json.dumps(framed), cache_time)
    return framed


def pyld_caching_document_loader(url, options={}, cache_time=60 * 60 * 24, skip_cache=False):
    """ PyLD document loader that caches results in django cache """
    if not skip_cache:
        response = cache.get("jsonld-loader-" + url)
        if response is not None:
            return json.loads(response)

    response = _pyld_extended_loader(url, options)
    cache.set("jsonld-loader-" + url, json.dumps(response), cache_time)
    return response


def _pyld_extended_loader(url, options={}):
    """
    Based on the default requests pyld document loader
    Extended to support contexts that use alternate Link headers for json+ld context, i.e. http(s)://schema.org
    (see https://github.com/digitalbazaar/pyld/issues/154)
    """
    try:
        # validate URL
        pieces = urllib_parse.urlparse(url)
        if (not all([pieces.scheme, pieces.netloc]) or
                pieces.scheme not in ['http', 'https'] or
                set(pieces.netloc) > set(
                    string.ascii_letters + string.digits + '-.:')):
            raise JsonLdError(
                'URL could not be dereferenced; only "http" and "https" '
                'URLs are supported.',
                'jsonld.InvalidUrl', {'url': url},
                code='loading document failed')

        headers = options.get('headers')
        if headers is None:
            headers = {
                'Accept': 'application/ld+json, application/json'
            }
        response = requests.get(url, headers=headers)

        content_type = response.headers.get('content-type')
        if not content_type:
            content_type = 'application/octet-stream'

        def get_linked_context_url(response):
            link_header = response.headers.get('link')
            try:
                parsed_link_header = parse_link_header(link_header)
                linked_context = parsed_link_header.get(LINK_HEADER_REL, parsed_link_header.get("alternate"))
            except Exception:
                linked_context = None

            if linked_context:
                if isinstance(linked_context, list):
                    raise JsonLdError(
                        'URL could not be dereferenced, '
                        'it has more than one '
                        'associated HTTP Link Header.',
                        'jsonld.LoadDocumentError',
                        {'url': url},
                        code='multiple context link headers')
                linked_alternate = parse_link_header(link_header).get('alternate')
                if linked_alternate.get('type') == 'application/ld+json' and \
                        not re.match(r'^application\/(\w*\+)?json$', content_type):
                    return linked_alternate['target']
            return None

        linked_context = get_linked_context_url(response)
        if linked_context:
            doc = {
                'contentType': 'application/ld+json',
                'contextUrl': linked_context,
                'documentUrl': jsonld.prepend_base(url, linked_context),
                'document': requests.get(jsonld.prepend_base(url, linked_context)).json(),
            }

        else:
            doc = {
                'contentType': content_type,
                'contextUrl': None,
                'documentUrl': response.url,
                'document': response.json(),
            }

        return doc
    except JsonLdError as e:
        raise e
    except Exception as cause:
        raise JsonLdError(
            'Could not retrieve a JSON-LD document from the URL.',
            'jsonld.LoadDocumentError', code='loading document failed',
            cause=cause)


def replace_values(obj: dict[str, Any] | list[Any] | Any, replacements: dict[str, str]) -> dict[str, Any] | list[Any] | Any:
    """
    Recursively replaces values in a JSON-like object (dict, list, etc.)
    based on a provided key-value mapping.

    The function traverses through the input object, which can be a dictionary,
    list, or a primitive data type (string, integer, etc.). If a value in the object
    matches a key in the provided `ids` mapping, it is replaced with the corresponding
    value from the `ids` dictionary. The function handles nested structures, ensuring
    that all values are checked and replaced if necessary.
    """
    if isinstance(obj, dict):
        return {k: replace_values(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_values(item, replacements) for item in obj]
    else:
        for patten, replacement in replacements.items():
            if re.match(patten, str(obj)):
                return re.sub(patten, replacement, str(obj))

    return obj
