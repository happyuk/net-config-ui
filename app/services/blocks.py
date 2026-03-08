from typing import Any, Dict, List
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import re

from app.services.block_naming import display_name_from_j2

Block = Dict[str, Any]

# Root of templates (keep this pointing at app/templates)
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

# -----------------------------------------------------------------------------
# Active block-set and top-level template
# -----------------------------------------------------------------------------
BLOCK_SET_DIR = "dvr/precert"        # default
TOP_LEVEL_FILE = "dvr_pre-cert.j2"   # default

# Map a block-set directory to its top-level file
TOP_FILE_MAP = {
    "dvr/precert":  "dvr_pre-cert.j2",
    "dvr/postcert": "dvr_post-cert.j2",
    "obr/precert":  "obr_pre-cert.j2",  
    "obr/postcert": "obr_post-cert.j2",  
    "test": "test-show-config.j2"
}

def set_selected_template_set(name: str):
    """
    # Select the currently active template set (directory of Jinja templates) based on the user's choice 
    # & update the corresponding top-level Jinja file that drives the command-building process
    """
    global BLOCK_SET_DIR, TOP_LEVEL_FILE
    BLOCK_SET_DIR = name
    TOP_LEVEL_FILE = TOP_FILE_MAP.get(name, TOP_LEVEL_FILE)  # keep previous if unknown


_env: Environment | None = None


def _get_jinja_env() -> Environment:
    """Lazily create and return a Jinja2 environment."""
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


from typing import Any, Dict, List

# Convert Jinja template into list of CLI commands that will be executed on the device by the Deployer service
def render_jinja_template_to_cli_commands(
    template_name: str,
    context: dict | None = None,
    *,
    strip_bang_comments: bool = False
) -> list[str]:
    env = _get_jinja_env()
    template = env.get_template(template_name)
    text: str = template.render(**(context or {}))

    commands: list[str] = []
    for line in text.split('\n'):  # Split on newline, preserves all lines including final blank
        line = line.rstrip()
        if not line:  # Skip empty lines
            continue
        if strip_bang_comments and line.lstrip().startswith('!'):
            continue
        commands.append(line)

    return commands

def get_included_templates(top_level_filename: str) -> List[str]:
    """
    Parse the top-level Jinja template and extract all *active* {% include "..." %}
    statements, ignoring commented-out includes.
    Returns a list of template paths relative to the templates root.
    Example: ["dvr/precert/00-platform.j2", "dvr/precert/02-vrfs.j2"]
    """
    top_level_path = TEMPLATES_DIR / top_level_filename

    if not top_level_path.exists():
        return []

    includes: List[str] = []
    include_pattern = re.compile(r'{%\s*include\s*"([^"]+)"\s*%}')

    with open(top_level_path, "r") as f:
        for line in f:
            s = line.strip()

            # Ignore commented-out Jinja blocks: {# ... #}
            if s.startswith("{#") and s.endswith("#}"):
                continue

            # Ignore VS Code "#" commented lines
            if s.startswith("#"):
                continue

            match = include_pattern.search(s)
            if match:
                includes.append(match.group(1))

    return includes


def build_blocks(
    *,
    node_number: str,
    domain: str,
) -> List[Block]:
    """
    Build deployment blocks based ONLY on templates actively included
    in the currently selected top-level file (Pre-Cert *or* Post-Cert).
    """
    ctx = {"node_number": node_number, "domain": domain}
    blocks: List[Block] = []

    # Use the active top-level file (set via set_block_set)
    active_templates = get_included_templates(TOP_LEVEL_FILE)

    # Build CLI blocks for each included template
    for rel_path in active_templates:
        base = Path(rel_path).name
        name_wo_ext = base[:-3]

        if "-" in name_wo_ext:
            _, simple_name = name_wo_ext.split("-", 1)
        else:
            simple_name = name_wo_ext

        block = {
            "name": simple_name,
            "mode": "cli",
            "commands": render_jinja_template_to_cli_commands(
                rel_path,
                ctx
            ),
            "template_file": rel_path,
        }
        blocks.append(block)

    # Display names
    for i, block in enumerate(blocks, start=1):
        base_name = block["name"]
        tpl_for_display = block.get("template_file") or TOP_LEVEL_FILE
        dn = display_name_from_j2(tpl_for_display, base_name)
        block["display_name"] = (f"{i:02d}-{base_name}" if dn.startswith("??-") else dn)
        block.pop("template_file", None)

    return blocks