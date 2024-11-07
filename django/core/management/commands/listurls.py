import json
from importlib import import_module
from io import StringIO

from django.conf import settings
from django.contrib.admindocs.views import (
    extract_views_from_urlpatterns,
    simplify_regex,
)
from django.core.management import color
from django.core.management.base import BaseCommand, CommandParser, CommandError
from django.utils import termcolors

FORMATS = (
    "aligned",
    "table",
    "verbose",
    "json",
    "pretty-json",
)


COLORLESS_FORMATS = (
    "json",
    "pretty-json",
)


class Command(BaseCommand):
    help = "Displays URL patterns matching the given prefixes for the project."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.style.HEADER = termcolors.make_style(opts=("bold",))
        self.style.ROUTE = termcolors.make_style(fg="green", opts=("bold",))
        self.style.VIEW_PATH = termcolors.make_style(fg="yellow")
        self.style.VIEW_NAME = termcolors.make_style(opts=("bold",))
        self.style.NAME = termcolors.make_style(fg="red")

    def add_arguments(self, parser: CommandParser):
        super().add_arguments(parser)

        # Sorting
        parser.add_argument(
            "--unsorted",
            "-u",
            action="store_true",
            dest="unsorted",
            help="List URLs with the same order as found in URL patterns",
        )

        # Prefix
        parser.add_argument(
            "--prefix",
            "-p",
            nargs="*",
            help="Only list URLs with these prefixes.",
        )

        # Format
        parser.add_argument(
            "--format",
            "-f",
            default="aligned",
            choices=FORMATS,
            help="Formatting style of the output",
        )

    def handle(self, *args, **options):
        prefixes = options["prefix"]
        if prefixes:
            prefixes = prefixes if isinstance(prefixes, list) else [prefixes]

        url_patterns = get_url_patterns(prefixes=prefixes)

        if not url_patterns:
            raise CommandError("There are no URL patterns that match given prefixes")

        unsorted = options["unsorted"]
        no_color = options["no_color"]
        format = options["format"]

        # Apply sorting
        if not unsorted:
            url_patterns.sort()

        # Apply colors
        if (
            color.supports_color()
            and (not no_color)
            and (format not in COLORLESS_FORMATS)
        ):
            url_patterns = self.apply_color(url_patterns=url_patterns)

        # Apply formatting
        url_patterns = self.apply_format(
            url_patterns=url_patterns,
            format=format,
        )

        return url_patterns

    def apply_color(self, url_patterns):
        colored_url_patterns = []

        for url_pattern in url_patterns:
            # Route
            route = url_pattern[0]
            route = self.style.ROUTE(route)

            # View
            view = url_pattern[1]
            module_path, module_name = view.rsplit(".", 1)
            module_path = self.style.VIEW_PATH(module_path)
            module_name = self.style.VIEW_NAME(module_name)
            view = f"{module_path}.{module_name}"

            # Name
            name = url_pattern[2]
            name = self.style.NAME(name) if name else ""

            # Append to the list
            colored_url_patterns.append((route, view, name))

        return colored_url_patterns

    def apply_format(self, url_patterns, format):
        format_method_name = f"format_{format.replace('-', '_')}"
        format_method = getattr(self, format_method_name)

        return format_method(url_patterns)

    def format_table(self, url_patterns):
        formatted_str = StringIO()

        widths = []
        margin = 2
        for columns in zip(*url_patterns, strict=False):
            widths.append(len(max(columns, key=len)) + margin)

        # Headers
        headers = (
            self.style.HEADER("Route"),
            self.style.HEADER("View"),
            self.style.HEADER("Name"),
        )

        header_parts = []
        for width, header in zip(widths, headers, strict=False):
            header_parts.append(header.ljust(width))

        formatted_str.write(" | ".join(header_parts))
        formatted_str.write("\n")

        # Header - content seperator
        formatted_str.write("-+-".join("-" * width for width in widths))
        formatted_str.write("\n")

        # Rows (content)
        for row in url_patterns:
            row_parts = []

            for width, cdata in zip(widths, row, strict=False):
                row_parts.append(cdata.ljust(width))

            formatted_str.write(" | ".join(row_parts))
            formatted_str.write("\n")

        return formatted_str.getvalue()

    def format_aligned(self, url_patterns):
        formatted_str = StringIO()

        widths = []
        for columns in zip(*url_patterns, strict=False):
            margin = 2
            widths.append(len(max(columns, key=len)) + margin)

        for row in url_patterns:
            for width, cdata in zip(widths, row, strict=False):
                formatted_str.write(cdata.ljust(width))

            formatted_str.write("\n")

        return formatted_str.getvalue()

    def format_verbose(self, url_patterns):
        formatted_str = StringIO()

        for route, view, name in url_patterns:
            route_str = f"{self.style.HEADER('Route:')} {route}"
            view_str = f"{self.style.HEADER('View:')} {view}"
            name_str = f"{self.style.HEADER('Name:')} {name}" if name else ""

            seperator = "-" * 20 + "\n"
            parts = (
                route_str,
                view_str,
                name_str,
                seperator,
            )

            formatted_str.write("\n".join(part for part in parts if part))

        return formatted_str.getvalue()

    def format_json(self, url_patterns, pretty=False):
        indent = 4 if pretty else None

        # Having keys in the resulting JSON makes it more useful
        url_pattern_dicts = []
        for route, view, name in url_patterns:
            url_pattern_dict = {
                "route": route,
                "view": view,
                "name": name,
            }
            url_pattern_dicts.append(url_pattern_dict)

        return json.dumps(url_pattern_dicts, indent=indent)

    def format_pretty_json(self, url_patterns):
        return self.format_json(url_patterns, pretty=True)


def get_url_patterns(prefixes=None):
    """
    Returns a list of URL patterns in the project with given prefixes.

    Each object in the returned list is a tuple[str] with 3 elements:
    (route, view, name)
    """

    url_patterns = []
    urlconf = import_module(settings.ROOT_URLCONF)

    for view_func, regex, namespace_list, name in extract_views_from_urlpatterns(
        urlconf.urlpatterns
    ):
        # Route
        route = simplify_regex(regex)

        # View
        view = "{}.{}".format(
            view_func.__module__,
            getattr(view_func, "__name__", view_func.__class__.__name__),
        )

        # Name
        namespace = ""

        if namespace_list:
            for part in namespace_list:
                namespace += part + ":"

        name = namespace + name if name else None
        name = name or ""

        # Append to the list
        url_patterns.append((route, view, name))

    # Filter out when prefixes are given but the pattern's route doesn't match
    if prefixes:
        url_patterns = [
            url_pattern
            for url_pattern in url_patterns
            if any(url_pattern[0].startswith(prefix) for prefix in prefixes)
        ]

    return url_patterns
