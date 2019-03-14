#!/usr/bin/env python3
import io
import unittest
import warnings
from scrapexpathlist import parse_document, select, xpath, fetch_text, do_fetch


class UnittestRunnerThatDoesntAddWarningFilter(unittest.TextTestRunner):
    def __init(self, *args, **kwargs):
        print(repr((args, kwargs)))
        super().__init__(*args, **kwargs, warnings=None)


class Xml1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            (
                '<a><b><c>c</c><d foo="bar">d</d></b><b><c>C</c>'
                '<d foo="baz">D</d></b><e>ehead<f>f</f>etail</e></a>'
            ),
            False
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_convert_node_to_text(self):
        self.assertEqual(self.select('//c'), ['c', 'C'])

    def test_convert_subnodes_to_text(self):
        self.assertEqual(self.select('//b'), ['cd', 'CD'])

    def test_attributes(self):
        self.assertEqual(self.select('//d/@foo'), ['bar', 'baz'])

    def test_text(self):
        self.assertEqual(self.select('//d/text()'), ['d', 'D'])

    def test_head(self):
        self.assertEqual(self.select('//f/preceding-sibling::text()'),
                         ['ehead'])

    def test_tail(self):
        self.assertEqual(self.select('//f/following-sibling::text()'),
                         ['etail'])

    def test_count(self):
        self.assertEqual(self.select('count(//d)'), [2.0])

    def test_bool(self):
        self.assertEqual(self.select('boolean(//f)'), [True])
        self.assertEqual(self.select('boolean(//g)'), [False])


class Html1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            '''<!DOCTYPE html><html>
              <head>
                <meta charset="utf-16be">
                <title>Hello, world!</title>
                <link rel="stylesheet" href="/style.css"/>
                <script src="/script.js"></script>
              </head>
              <body>
                <img src="/logo.png" alt="logo" />
                <p>Foo</p>
                <p>Bar</p>
                <table><td>Single-cell table</table>
                <a href="/foo">Foo</a>
                <a href="/bar">Bar</a>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">
                  <path d="M0 0L2 2"/>
                </svg>
              </body>
            </html>''',
            True
        )

    def select(self, selector):
        return select(self.tree, xpath(selector))

    def test_simple(self):
        self.assertEqual(self.select('//p'), ['Foo', 'Bar'])

    def test_do_not_expand_single_string(self):
        self.assertEqual(self.select("'ab'"), ['ab'])

    def test_svg_namespace(self):
        # Works across namespaces
        self.assertEqual(self.select('//svg:path/@d'), ['M0 0L2 2'])

    def test_add_missing_elements(self):
        # Parse invalid HTML by adding missing elements
        self.assertEqual(self.select('//tr'), ['Single-cell table'])


class HtmlTest(unittest.TestCase):
    def test_no_warning_coercing_non_xml_name(self):
        # Turn warning into error (just for this test -- the test runner resets
        # filters each test)
        warnings.simplefilter('error', append=True)
        parse_document('<ns:html></ns:html>', True)


class FakeResponseInfo:
    def __init__(self, headers):
        self.headers = headers

    def get(self, key, default=None):
        return self.headers.get(key, default)

    def get_content_type(self):
        return self.headers.get('Content-Type', '').split(';')[0] or None

    def get_content_charset(self):
        parts = self.headers.get('Content-Type', '').split('charset=')
        if len(parts) == 2:
            return parts[1]
        else:
            return None


class FakeResponse:
    def __init__(self, body, headers):
        self.body = io.BytesIO(body)
        self._info = FakeResponseInfo(headers)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        pass

    def read(self, max_n_bytes):
        return self.body.read(max_n_bytes)

    def info(self):
        return self._info


class DoFetchTests(unittest.TestCase):
    def _go(self, selector, response):
        return do_fetch(
            url='http://example.org',
            selector=selector,
            urlopen=lambda x, **kwargs: response
        )

    def test_xpath_eval_error(self):
        selector = xpath('//ns:a')  # valid xpath
        result = self._go(
            selector,
            FakeResponse(b'<p>hi</p>', {'Content-Type': 'text/html'})
        )
        self.assertEqual(result,
                         (None, 'XPath error: Undefined namespace prefix'))


class FetchTextTest(unittest.TestCase):
    def _go(self, response):
        return fetch_text('http://example.org',
                          urlopen=lambda x, **kwargs: response)

    def test_default(self):
        info, s = self._go(FakeResponse(b'<p>hi</p>', {}))
        self.assertEqual(s, '<p>hi</p>')

    def test_gzip_encoding(self):
        """Test that Content-Encoding: gzip gets decoded correctly."""
        info, s = self._go(FakeResponse(
            (b'\x1f\x8b\x08\x00gY\xbe[\x02\xff\xb3)\xb0\xcb'
             b'\xc8\xb4\xd1/\xb0\x03\x00e\xd27m\t\x00\x00\x00'),
            {'Content-Encoding': 'gzip'}
        ))

        self.assertEqual(s, '<p>hi</p>')

    def test_gzip_eoferror(self):
        with self.assertRaises(EOFError):
            self._go(FakeResponse(
                (b'\x1f\x8b\x08\x00gY\xbe[\x02\xff\xb3)\xb0\xcb'
                 b'\xc8\xb4\xd1/\xb0\x03\x00'),
                {'Content-Encoding': 'gzip'}
            ))

    def test_gzip_magic_number_error(self):
        with self.assertRaises(OSError):
            self._go(FakeResponse(b'<p>hi</p>', {'Content-Encoding': 'gzip'}))


if __name__ == '__main__':
    unittest.main(testRunner=UnittestRunnerThatDoesntAddWarningFilter())
