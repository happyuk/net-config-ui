# app/services/config_manager.py
from app.infrastructure.loader import NODE_OBR_ASSIGNMENT
from app.services.ip_utils import add_to_last_octet

# Single Source of Truth for all template locations
TEMPLATE_REGISTRY = {
    "DVR Pre-Cert": {"path": "", "file": "dvr_pre-cert.j2"},
    "DVR Post-Cert": {"path": "", "file": "dvr_post-cert.j2"},
    "DVR Pre-ESXI": {"path": "dvr/preesxi", "file": "dvr_pre_ESXI.j2"},
    "OBR Pre-Cert": {"path": "", "file": "obr_pre-cert.j2"},
    "OBR Post-Cert": {"path": "", "file": "obr_post-cert.j2"},
    "Show Running Config": {"path": "test", "file": "test-show-config.j2"}
}

class ConfigManager:
    @staticmethod
    def get_grey_ips(node: str):
        """Calculates IPs. Returns a dict or None."""
        if node not in NODE_OBR_ASSIGNMENT:
            return None

        lookup = NODE_OBR_ASSIGNMENT[node]
        vlan10 = lookup["vlan_10_address_space"]
        network_base = vlan10.split("/")[0]

        return {
            "dhcp": network_base,
            "router": add_to_last_octet(network_base, 1),
            "reserved": add_to_last_octet(network_base, 4)
        }

    @staticmethod
    def get_template_path(mode: str):
        """Maps UI text to folder paths using the central registry."""
        # .get(mode, {}) handles cases where a mode might not exist
        return TEMPLATE_REGISTRY.get(mode, {}).get("path")

    @staticmethod
    def get_template_file(mode: str):
        """Maps UI text to specific filenames using the central registry."""
        return TEMPLATE_REGISTRY.get(mode, {}).get("file")