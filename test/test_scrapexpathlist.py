#!/usr/bin/env python3

import io
from lxml import etree
from scrapexpathlist import parse_document, select, xpath
import unittest


class Xml1(unittest.TestCase):
    def setUp(self):
        self.tree = parse_document(
            '<a><b><c>c</c><d foo="bar">d</d></b><b><c>C</c><d foo="baz">D</d></b><e>ehead<f>f</f>etail</e></a>',
            False
        )


    def select(self, selector):
        return select(self.tree, xpath(selector))


    def test_convert_node_to_text(self):
        self.assertEqual(self.select('//c'), [ 'c', 'C' ])


    def test_convert_subnodes_to_text(self):
        self.assertEqual(self.select('//b'), [ 'cd', 'CD' ])


    def test_attributes(self):
        self.assertEqual(self.select('//d/@foo'), [ 'bar', 'baz' ])


    def test_text(self):
        self.assertEqual(self.select('//d/text()'), [ 'd', 'D' ])


    def test_head(self):
        self.assertEqual(self.select('//f/preceding-sibling::text()'), [ 'ehead' ])


    def test_tail(self):
        self.assertEqual(self.select('//f/following-sibling::text()'), [ 'etail' ])


    def test_count(self):
        self.assertEqual(self.select('count(//d)'), [ 2.0 ])


    def test_bool(self):
        self.assertEqual(self.select('boolean(//f)'), [ True ])
        self.assertEqual(self.select('boolean(//g)'), [ False ])


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
            True,
            source_url='http://example.org'
        )


    def select(self, selector):
        return select(self.tree, xpath(selector))


    def test_simple(self):
        self.assertEqual(self.select('//p'), [ 'Foo', 'Bar' ])


    def test_svg_namespace(self):
        # Works across namespaces
        self.assertEqual(self.select('//svg:path/@d'), [ 'M0 0L2 2' ])


    def test_add_missing_elements(self):
        # Parse invalid HTML by adding missing elements
        self.assertEqual(self.select('//tr'), [ 'Single-cell table' ])
