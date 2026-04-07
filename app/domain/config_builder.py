import os
import sys
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from app.domain.config_manager import TEMPLATE_REGISTRY

def get_resource_path(relative_path: str) -> Path:
    """ 
    Finds the correct path for files whether running as a script or EXE.
    """
    if hasattr(sys, '_MEIPASS'):
        # If running as EXE, look in the PyInstaller temp folder
        return Path(sys._MEIPASS) / relative_path
    
    # If running as a normal script, look relative to this file
    # (Go up two levels from app/services/ to the root, then into the folder)
    return Path(__file__).resolve().parent.parent / relative_path

class ConfigBuilder:
    def __init__(self):
        # FIX: Use the helper function to find the templates folder
        self.templates_dir = get_resource_path("templates")

        # Initialize Jinja2 using the absolute path we just found
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=False,
            lstrip_blocks=False
        )

    def resolve_template_info(self, friendly_name: str) -> Optional[dict]:
        return TEMPLATE_REGISTRY.get(friendly_name)

    def render_template(self, relative_path: str, **kwargs) -> str:
        try:
            # Jinja needs the path relative to the FileSystemLoader root
            tmpl = self.env.get_template(relative_path)
            return tmpl.render(**kwargs)
        except TemplateNotFound:
            return (
                f"ERROR: Template '{relative_path}' not found.\n"
                f"Expected in: {self.templates_dir / relative_path}"
            )
        except Exception as e:
            return f"ERROR during rendering: {str(e)}"

    def build_from_label(self, friendly_label: str, **kwargs) -> str:
        info = self.resolve_template_info(friendly_label)
        if not info:
            return f"Template for '{friendly_label}' not implemented in Registry."

        # Logic to handle both root files and subfolder files
        if info['path']:
            rel_path = f"{info['path']}/{info['file']}"
        else:
            rel_path = info['file']

        return self.render_template(rel_path, **kwargs)