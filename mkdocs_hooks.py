"""Links aus der Doku auf Dateien außerhalb von docs/ (README, LICENSE, ...) zeigen auf GitHub."""

import re

GITHUB = "https://github.com/faolan-exe/Steuy/blob/main/"
AUSSERHALB = re.compile(r"\]\((?:\.\./)+((?:README|LICENSE|SECURITY|CONTRIBUTING)[^)\s]*)\)")


def on_page_markdown(markdown, page, config, files):
    return AUSSERHALB.sub(lambda m: f"]({GITHUB}{m.group(1)})", markdown)
