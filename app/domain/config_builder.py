# app/services/config_builder.py

from pathlib import Path
from typing import Optional, Dict, List
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from app.domain.config_manager import TEMPLATE_REGISTRY

class ConfigBuilder:
    """
    Centralised Jinja2 config rendering system.
    Now pulls its mappings from ConfigManager's TEMPLATE_REGISTRY.
    """

    def __init__(self):
        # templates/ directory
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"

        # FileSystemLoader can handle subdirectories if we pass it the root
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=False,
            lstrip_blocks=False
        )

    # -----------------------------------------------------------
    # TEMPLATE MANAGEMENT
    # -----------------------------------------------------------

    def resolve_template_info(self, friendly_name: str) -> Optional[dict]:
        """Fetch the path and filename from the central registry."""
        return TEMPLATE_REGISTRY.get(friendly_name)

    # -----------------------------------------------------------
    # RENDERING
    # -----------------------------------------------------------
    def render_template(
        self,
        relative_path: str,
        **kwargs
    ) -> str:
        try:
            tmpl = self.env.get_template(relative_path)
            return tmpl.render(**kwargs)
        except TemplateNotFound:
            return (
                f"ERROR: Template '{relative_path}' not found.\n"
                f"Expected in: {self.templates_dir / relative_path}"
            )
        except Exception as e:
            return f"ERROR during rendering: {str(e)}"

    # -----------------------------------------------------------
    # FRIENDLY WRAPPERS
    # -----------------------------------------------------------
    def build_from_label(
        self,
        friendly_label: str,
        **kwargs
    ) -> str:
        # 1. Get info from registry
        info = self.resolve_template_info(friendly_label)

        if not info:
            return f"Template for '{friendly_label}' not implemented in Registry."

        # 2. Construct the relative path Jinja needs (e.g., "dvr/precert/dvr_pre-cert.j2")
        # This handles your subfolder structure!
        rel_path = f"{info['path']}/{info['file']}"

        # 3. Render
        return self.render_template(rel_path, **kwargs)