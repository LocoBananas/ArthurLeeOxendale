#!/usr/bin/env python3
"""Static SEO and internal navigation checks for the ALO website.

Run locally with: python3 scripts/seo_check.py
No network access or third-party packages are needed.
"""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "https://arthurleeoxendale.xyz/"
PAGES = ("index.html", "writings.html", "timeline.html", "about.html")
errors = []

class SiteHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_count = 0
        self.h1_count = 0
        self.links = []
        self.ids = set()
        self.description = None
        self.canonical = None
        self.robot_directive = None
        self.ld_scripts = []
        self._in_title = False
        self._in_ld = False
        self._ld_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        elif tag == "meta" and attrs.get("name") == "description":
            self.description = attrs.get("content")
        elif tag == "meta" and attrs.get("name") == "robots":
            self.robot_directive = attrs.get("content")
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self._in_ld = True
            self._ld_text = ""
        if "id" in attrs:
            if attrs["id"] in self.ids:
                errors.append("Duplicate id: " + attrs["id"])
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self.ld_scripts.append(self._ld_text)
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.title_count += 1
        if self._in_ld:
            self._ld_text += data

parsed = {}
for filename in PAGES:
    path = ROOT / filename
    if not path.is_file():
        errors.append(f"Missing page: {filename}")
        continue
    item = SiteHTML()
    item.feed(path.read_text(encoding="utf-8"))
    parsed[filename] = item
    expected = DOMAIN + ("" if filename == "index.html" else filename)
    if item.canonical != expected:
        errors.append(f"{filename}: canonical must be {expected}")
    if item.title_count != 1:
        errors.append(f"{filename}: expected one nonempty title")
    if item.h1_count != 1:
        errors.append(f"{filename}: expected one H1")
    if not item.description:
        errors.append(f"{filename}: missing meta description")
    if not item.robot_directive or "noindex" in item.robot_directive:
        errors.append(f"{filename}: indexing disabled or robots meta missing")
    if not item.ld_scripts:
        errors.append(f"{filename}: missing JSON-LD")
    for raw in item.ld_scripts:
        try:
            info = json.loads(raw)
            if info.get("url") != expected:
                errors.append(f"{filename}: structured-data URL mismatch")
        except json.JSONDecodeError:
            errors.append(f"{filename}: invalid structured data")

for filename, item in parsed.items():
    for href in item.links:
        parts = urlsplit(href)
        if parts.scheme or parts.netloc:
            continue
        target = unquote(parts.path.lstrip("/")) if parts.path else filename
        if not target:
            target = "index.html"
        if target not in parsed:
            errors.append(f"{filename}: unresolved internal file {href}")
        elif parts.fragment and parts.fragment not in parsed[target].ids:
            errors.append(f"{filename}: unresolved fragment {href}")

sitemap_path = ROOT / "sitemap.xml"
if sitemap_path.is_file():
    try:
        tree = ET.parse(sitemap_path)
        urls = {n.text for n in tree.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        expected_urls = {DOMAIN + ("" if p == "index.html" else p) for p in PAGES}
        if urls != expected_urls:
            errors.append("Sitemap entries differ from published HTML pages")
    except ET.ParseError as ex:
        errors.append("Invalid sitemap XML: " + str(ex))
else:
    errors.append("Missing sitemap.xml")

robots = ROOT / "robots.txt"
if not robots.exists() or "Sitemap: " + DOMAIN + "sitemap.xml" not in robots.read_text(encoding="utf-8"):
    errors.append("robots.txt missing canonical sitemap reference")

if errors:
    print("SEO checks FAILED:")
    for item in errors:
        print(" - " + item)
    sys.exit(1)
print(f"SEO checks passed: {len(parsed)} pages, canonical tags, indexing, metadata, JSON-LD, sitemap, internal links.")
