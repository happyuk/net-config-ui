# app/services/config_manager.py
from app.infrastructure.loader import NODE_OBR_ASSIGNMENT
from app.services.ip_utils import add_to_last_octet

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
        """Maps UI text to folder paths."""
        mapping = {
            "DVR Pre-Cert": "dvr/precert",
            "DVR Post-Cert": "dvr/postcert",
            "OBR Pre-Cert": "obr/precert",
            "OBR Post-Cert": "obr/postcert",
            "Show Running Config": "test"
        }
        return mapping.get(mode)