#!/usr/bin/env python3

import gzip
from typing import Callable, List, Tuple
import warnings
import urllib.request
import urllib.error
from html5lib.constants import DataLossWarning
from lxml import etree
from lxml.html import html5parser
from http.client import HTTPResponse
from pandas import DataFrame


# GLOBALLY ignore the warnings that (hopefully) only this module will emit. The
# warnings all have to do with "invalid" HTML, but that HTML is often good
# enough for our users so it isn't worth dumping anything to stderr.
warnings.filterwarnings('ignore', category=DataLossWarning,
                        module=r'html5lib\._ihatexml')


def fetch(params):
    url = params['url']
    selector_string = params['selector']

    if not url:
        return (None, 'Missing URL')

    if not selector_string:
        return (None, 'Missing selector')

    try:
        selector = xpath(selector_string)
    except etree.XPathSyntaxError as err:
        return (None, f'Bad XPath input: {str(err)}')

    return do_fetch(url, selector)


def xpath(s: str) -> etree.XPath:
    """
    Parse an XPath selector, or raise etree.XPathSyntaxError.

    A word on namespaces: this module parses HTML without a namespace.
    It parses embedded SVGs in the "svg" namespace. So your XPath
    selectors can look like:

    xpath('//p')           # all <p> tags (in HTML)
    xpath('//order/@id')   # all <order> id attributes (in XML)
    xpath('//svg:path/@d') # all <path> tags (in SVG embedded within HTML)
    """
    return etree.XPath(
        s,
        smart_strings=True,  # so result strings don't ref XML doc
        namespaces={
            'svg': 'http://www.w3.org/2000/svg',
        }
    )


def parse_document(text: str, is_html: bool) -> etree._Element:
    """Build a etree root node from `text`.

    Throws TODO what errors?
    """
    if is_html:
        parser = html5parser.HTMLParser(namespaceHTMLElements=False)
        tree = html5parser.fromstring(text, parser=parser)
        return tree
    else:
        parser = etree.XMLParser(
            encoding='utf-8',
            # Disable as much as we can, for security
            load_dtd=False,
            collect_ids=False,
            resolve_entities=False
        )
        return etree.fromstring(text.encode('utf-8'), parser)


def _item_to_string(item) -> str:
    """Convert an XPath-returned item to a string.

    Rules:
    text node => text contents
    """
    if hasattr(item, 'itertext'):
        # This is an Element.
        return ''.join(item.itertext())
    else:
        # item.is_attribute
        # item.is_text
        # item.is_tail
        return str(item)


def select(tree: etree._Element, selector: etree.XPath) -> List[str]:
    """
    Run an xpath expression on `tree` and convert results to strings.

    Raise XPathEvalError on error.
    """
    # TODO avoid DoS. xpath selectors can take enormous amounts of CPU/memory
    result = selector(tree)
    if hasattr(result, '__iter__') and not isinstance(result, str):
        return list(_item_to_string(item) for item in result)
    elif isinstance(result, bool):
        # boolean(//f) -- Workbench does not support bool, so convert to str.
        return [str(result)]
    else:
        # count(//a) => float. Return list of float.
        return [result]


def do_fetch(
    url: str,
    selector: etree.XPath,
    urlopen: Callable[[str], HTTPResponse] = urllib.request.urlopen,
    max_n_bytes: int = 5*1024*1024,
    timeout: float = 30
) -> Tuple[DataFrame, str]:
    """Open the given URL and selects `selector` xpath, as a
    (DataFrame, error_message) tuple.

    Keyword arguments:
    urlopen --  urllib.request.urlopen, or a stub
    max_n_bytes -- number of bytes read before we abort
    timeout --  number of seconds before we abort
    """
    try:
        (response_info, text) = fetch_text(url, urlopen=urlopen,
                                           timeout=timeout)
    except urllib.error.URLError as err:
        return (None, f'Fetch error: {str(err)}')
    except TimeoutError:
        return (None, 'HTTP request timed out')
    except EOFError:
        return (None, 'Compressed data was truncated')
    except OSError:
        return (None, 'Compressed data was not valid gzip')
    except ValueError as err:
        return (None, str(err))  # Exceeded max_n_bytes
    except UnicodeDecodeError:
        return (None, 'HTML or XML has invalid charset')

    is_html = response_info.get_content_type() == 'text/html'

    tree = parse_document(text, is_html)  # FIXME handle errors

    try:
        values = select(tree, selector)
    except etree.XPathEvalError as err:
        return (None, 'XPath error: %s' % err)

    table = DataFrame({'XPath result': values})

    return (table, None)


def fetch_text(
    url: str,
    max_n_bytes: int = 5*1024*1024,
    timeout: float = 30,
    urlopen: Callable[[str], HTTPResponse] = urllib.request.urlopen
):
    """Fetch (HTTPResponse.info(), text_content_str) from `url`.

    This will never read more than `max_n_bytes` bytes from the response.
    It will also return before `timeout`s expire.

    Throw `TimeoutError` if `timeout` expires.

    Throw `ValueError` if the `max_n_bytes` is exceeded.

    Throw `URLError` if anything fails at the HTTP level or below.

    Throw `EOFError` if gzip-decoding fails.

    Throw `OSError` if gzip-decoding is given non-gzipped data.

    Throw `UnicodeDecodeError` if we cannot understand URL's encoding.
    """
    # Throws URLError or TimeoutError
    with urlopen(url, timeout=timeout) as response:
        # TODO avoid DoS. The above timeout is the _socket_ timeout: one
        # byte from the server resets it.
        b = response.read(max_n_bytes + 1)
        if (len(b) == max_n_bytes + 1):
            raise ValueError(
                f'HTTP response is larger than {max_n_bytes} bytes'
            )

        if response.info().get('Content-Encoding') == 'gzip':
            b = gzip.decompress(b)

        text = b.decode(response.info().get_content_charset() or 'utf-8')
        return (response.info(), text)
