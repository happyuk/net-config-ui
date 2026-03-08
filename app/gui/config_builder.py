# app/services/config_builder.py

from pathlib import Path
from typing import Optional, Dict, List
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# Render the Jinja template into config. string using the parameters provided (node, domain, secrets etc)
class ConfigBuilder:
    """
    Centralised Jinja2 config rendering system.

    Supports:
      - template lookup by filename
      - template registry for friendly names
      - auto-discovery of available templates
      - clean error handling for missing templates
    """

    def __init__(self):
        # templates/ directory
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=False,
            lstrip_blocks=False
        )

        # Friendly names -> template filenames
        # You can freely expand this.
        self.registry: Dict[str, str] = {
            "DVR Pre-Cert": "dvr_pre-cert.j2",
            "DVR Post-Cert": "dvr_post-cert.j2",  
            "OBR Pre-Cert": "obr_pre-cert.j2",
            "OBR Post-Cert": "obr_post-cert.j2",
            "Show Running Config": "test-show-config.j2"
        }

    # -----------------------------------------------------------
    # TEMPLATE MANAGEMENT
    # -----------------------------------------------------------

    def list_templates(self) -> List[str]:
        """
        Returns all template filenames (.j2) in the templates directory.
        Useful for debugging or dynamic dropdown UIs.
        """
        if not self.templates_dir.exists():
            return []
        return sorted([f.name for f in self.templates_dir.glob("*.j2")])

    def has_template(self, filename: str) -> bool:
        """Check if a .j2 template file exists."""
        return (self.templates_dir / filename).exists()

    def resolve_template(self, friendly_name: str) -> Optional[str]:
        """
        Convert a UI template label into a Jinja filename via registry.
        Returns None if not implemented yet.
        """
        return self.registry.get(friendly_name)

    # -----------------------------------------------------------
    # RENDERING
    # -----------------------------------------------------------
    def render_template(
        self,
        template_name: str,
        node_number: str,
        domain: str,
        secret: str,
        username: str,
        usersecret: str,
        grey_dhcp: str,
        grey_router: str,
        grey_router_dhcp_reserved: str,
    ) -> str:
        """
        Render the specified Jinja template.
        """

        try:
            tmpl = self.env.get_template(template_name)
        except TemplateNotFound:
            return (
                f"ERROR: Template '{template_name}' not found.\n"
                f"Expected in: {self.templates_dir}"
            )

        return tmpl.render(
            node_number=node_number,
            domain=domain,
            secret=secret,
            username=username,
            usersecret=usersecret,
            grey_dhcp=grey_dhcp,
            grey_router=grey_router,
            grey_router_dhcp_reserved=grey_router_dhcp_reserved
        )

    # -----------------------------------------------------------
    # FRIENDLY WRAPPERS (OPTIONAL)
    # -----------------------------------------------------------
    def build_from_label(
        self,
        friendly_label: str,
        node_number: str,
        domain: str,
        secret: str,
        username: str,
        usersecret: str,
        grey_dhcp: str,
        grey_router: str,
        grey_router_dhcp_reserved: str,
    ) -> str:

        filename = self.resolve_template(friendly_label)

        if filename is None:
            return f"Template for '{friendly_label}' not implemented yet."

        if not self.has_template(filename):
            return (
                f"Template '{filename}' is expected for '{friendly_label}' "
                f"but does not exist in {self.templates_dir}"
            )

        return self.render_template(
            filename,
            node_number=node_number,
            domain=domain,
            secret=secret,
            username=username,
            usersecret=usersecret,
            grey_dhcp=grey_dhcp,
            grey_router=grey_router,
            grey_router_dhcp_reserved=grey_router_dhcp_reserved
        )