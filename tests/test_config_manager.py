import pytest
from app.domain.config_manager import ConfigManager
from app.infrastructure.loader import NODE_OBR_ASSIGNMENT

def test_get_grey_ips_valid_node():
    """Test using the first available node in the actual assignment data."""
    # 1. Dynamically get the first key from your data (e.g., "1")
    if not NODE_OBR_ASSIGNMENT:
        pytest.skip("NODE_OBR_ASSIGNMENT is empty, cannot run test.")
        
    node_id = list(NODE_OBR_ASSIGNMENT.keys())[0]
    ips = ConfigManager.get_grey_ips(node_id)
    
    # 2. Verify the structure
    assert ips is not None, f"Failed to get IPs for existing node {node_id}"
    assert "dhcp" in ips
    assert "router" in ips
    assert "reserved" in ips
    
    # 3. Verify logic (DHCP base should be the first 3 octets of the router)
    # e.g. If router is 192.168.16.1, DHCP is 192.168.16.0
    router_parts = ips["router"].split(".")
    dhcp_parts = ips["dhcp"].split(".")
    assert router_parts[:3] == dhcp_parts[:3]

def test_get_grey_ips_invalid_node():
    """Test that a non-existent node (far outside 1-200) returns None."""
    ips = ConfigManager.get_grey_ips("999")
    assert ips is None

def test_template_mapping():
    """Verify that the UI selection maps to a valid template folder."""
    assert ConfigManager.get_template_path("DVR Pre-Cert") == "dvr/precert"
    assert ConfigManager.get_template_path("OBR Post-Cert") == "obr/postcert"