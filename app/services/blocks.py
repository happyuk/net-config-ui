from typing import Any, Dict, List
from pathlib import Path
import re
from jinja2 import Environment, FileSystemLoader

from app.services.block_naming import display_name_from_j2

Block = Dict[str, Any]

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

BLOCK_SET_DIR = "dvr/precert"
TOP_LEVEL_FILE = "dvr_pre-cert.j2"

TOP_FILE_MAP = {
    "dvr/precert": "dvr_pre-cert.j2",
    "dvr/postcert": "dvr_post-cert.j2",
    "obr/precert": "obr_pre-cert.j2",
    "obr/postcert": "obr_post-cert.j2",
    "test": "test-show-config.j2",
}

_env: Environment | None = None


# -----------------------------------------------------------------------------
# Template set selection
# -----------------------------------------------------------------------------

def set_selected_template_set(name: str):
    """Set the active template directory and its top-level file."""
    global BLOCK_SET_DIR, TOP_LEVEL_FILE
    BLOCK_SET_DIR = name
    TOP_LEVEL_FILE = TOP_FILE_MAP.get(name, TOP_LEVEL_FILE)


# -----------------------------------------------------------------------------
# Jinja Environment
# -----------------------------------------------------------------------------

def _get_jinja_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
    return _env


# -----------------------------------------------------------------------------
# Render template -> CLI commands
# -----------------------------------------------------------------------------

def render_jinja_template_to_cli_commands(
    template_name: str,
    context: dict | None = None,
    *,
    strip_bang_comments: bool = False,
) -> List[str]:

    template = _get_jinja_env().get_template(template_name)
    text = template.render(**(context or {}))

    commands = []
    for line in text.splitlines():
        line = line.rstrip()

        if not line:
            continue

        if strip_bang_comments and line.lstrip().startswith("!"):
            continue

        commands.append(line)

    return commands


# -----------------------------------------------------------------------------
# Parse top-level template includes
# -----------------------------------------------------------------------------

INCLUDE_RE = re.compile(r'{%\s*include\s*"([^"]+)"\s*%}')


def get_included_templates(top_level_filename: str) -> List[str]:
    """Return active {% include %} templates from the top-level file."""

    path = TEMPLATES_DIR / top_level_filename
    if not path.exists():
        return []

    includes: List[str] = []

    with open(path) as f:
        for line in f:
            s = line.strip()

            if s.startswith("{#") and s.endswith("#}"):
                continue
            if s.startswith("#"):
                continue

            m = INCLUDE_RE.search(s)
            if m:
                includes.append(m.group(1))

    return includes


# -----------------------------------------------------------------------------
# Build CLI blocks
# -----------------------------------------------------------------------------

def build_blocks(*, node_number: str, domain: str) -> List[Block]:

    ctx = {"node_number": node_number, "domain": domain}
    templates = get_included_templates(TOP_LEVEL_FILE)

    blocks: List[Block] = []

    for i, rel_path in enumerate(templates, start=1):

        base = Path(rel_path).stem
        simple_name = base.split("-", 1)[-1]

        dn = display_name_from_j2(rel_path, simple_name)
        display = f"{i:02d}-{simple_name}" if dn.startswith("??-") else dn

        blocks.append({
            "name": simple_name,
            "mode": "cli",
            "display_name": display,
            "commands": render_jinja_template_to_cli_commands(rel_path, ctx),
        })

    return blocks