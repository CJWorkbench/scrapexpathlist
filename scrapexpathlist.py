#!/usr/bin/env python3

import io
import urllib.request
import urllib.error
from lxml import etree
from lxml.html import html5parser
import pandas
from typing import Callable, List
from http.client import HTTPResponse
import re


_content_type_charset_re = re.compile(';\\s*charset=([-.a-zA-Z0-9]+)')


def render(wf_module, empty_table):
    fetched_table = wf_module.retrieve_fetched_table()
    if fetched_table is not None:
        table = fetched_table
    return table


def event(wf_module, event=None, **kwargs):
    url = wf_module.get_param_string('url')
    selector_string = wf_module.get_param_string('selector')

    if url is None: return
    if selector_string is None: return

    try:
        selector = xpath(selector_string)
    except etree.XPathSyntaxError as e:
        wf_module.set_error(f'Bad XPath input: {e.msg}')

    refresh(wf_module, url, selector, **kwargs)


def xpath(s: str) -> etree.XPath:
    """Parses an XPath selector, or throws etree.XPathSyntaxError.

    A word on namespaces: this module parses HTML without a namespace.
    It parses embedded SVGs in the "svg" namespace. So your XPath
    selectors can look like:

    xpath('//p')           # all <p> tags (in HTML)
    xpath('//order/@id')   # all <order> id attributes (in XML)
    xpath('//svg:path/@d') # all <path> tags (in SVG embedded within HTML)
    """
    return etree.XPath(
        s,
        smart_strings=True, # so result strings don't ref XML doc
        namespaces={
            'svg': 'http://www.w3.org/2000/svg',
        }
    )


def parse_document(text: str, is_html: bool,
                   source_url: str=None) -> etree._Element:
    """Build a etree root node from `text`.

    Throws TODO what errors?

    Keyword arguments:
    source_url -- if set, convert src and href attributes to absolute URLs
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
    """Run an xpath expression on `tree` and convert results to strings.
    """
    # TODO avoid DoS. xpath selectors can take enormous amounts of CPU/memory
    result = selector(tree)
    if hasattr(result, '__iter__'):
        return list(_item_to_string(item) for item in result)
    else:
        # count(//a) => float. Return list of float.
        return [ result ]


def poll(url: str, selector: etree.XPath, 
         urlopen: Callable[[str], HTTPResponse]=urllib.request.urlopen,
         max_n_bytes: int=5*1024*1024, timeout: float=30) -> List[str]:
    """Open the given URL and selects `selector` xpath text.

    Potential errors:
    URLError -- could not fetch data

    Keyword arguments:
    urlopen --  urllib.request.urlopen, or a stub.
    timeout --  number of seconds before we throw a URLError
    """
    (response_info, text) = fetch_text(url, urlopen=urlopen, timeout=timeout)
    is_html = response_info.get_content_type() == 'text/html'

    tree = parse_document(text, is_html, source_url=url)

    return select(tree, selector)


def fetch_text(url: str, max_n_bytes: int=5*1024*1024, timeout: float=30,
               urlopen: Callable[[str], HTTPResponse]=urllib.request.urlopen):
    """Fetch (HTTPResponse.info(), text_content_str) from `url`.

    This will never read more than `max_n_bytes` bytes from the response.
    It will also return before `timeout`s expire.

    Throw `os.TimeoutError` if `timeout` expires.

    Throw `ValueError` if the `max_n_bytes` is exceeded.

    Throw `URLError` if anything fails at the HTTP level or below.

    Throw `UnicodeDecodeError` if we cannot understand URL's encoding.
    """
    # Throws os.URLError or os.TimeoutError
    with urlopen(url, timeout=timeout) as response:
        # TODO avoid DoS. The above timeout is the _socket_ timeout: one
        # byte from the server resets it.
        b = response.read(max_n_bytes + 1)
        if (len(b) == max_n_bytes + 1):
            raise ValueError(f'HTTP response is larger than {max_n_bytes} bytes')

        text = b.decode(response.info().get_content_charset() or 'utf-8')
        return (response.info(), text)


def refresh(wf_module, url: str, selector: etree.XPath, urlopen=urllib.request.urlopen,
            timeout=30, **kwargs) -> None:
    """Polls the server, builds a DataFrame, and saves it on wf_module if
    needed.

    If poll() fails, sets an error on the module instead.

    Keyword arguments:
    urlopen --  urllib.request.urlopen, or a stub.
    timeout --  number of seconds before we throw a URLError
    """
    wf_module.set_busy()

    try:
        values = poll(url, selector, urlopen=urlopen, timeout=timeout)
        table = pandas.DataFrame({ str(selector): values })
    except URLError as e:
        wf_module.set_error(f'Fetch error: {e.msg}')
    except os.TimeoutError:
        wf_module.set_error('HTTP request timed out')
    except ValueError as e:
        wf_module.set_error(str(e)) # Exceeded max_n_bytes
    except UnicodeDecodeError:
        wf_module.set_error('HTML or XML has invalid charset')

    wf_module.set_ready(notify=False)

    wf_module.save_fetched_table_if_changed(table)
