class MainViewModel:
    def __init__(self, config_builder, config_manager, template_setter):
        self.config_builder = config_builder
        self.config_manager = config_manager
        self.template_setter = template_setter

    # ---------------------------
    # Core logic
    # ---------------------------

    def get_ips(self, node):
        return self.config_manager.get_grey_ips(node)

    def apply_template(self, mode):
        path = self.config_manager.get_template_path(mode)
        if path:
            self.template_setter(path)
        return path

    def build_config(self, mode, node, data: dict):
        return self.config_builder.build_from_label(
            mode,
            node_number=node,
            domain=data["domain"],
            secret=data["secret"],
            username=data["username"],
            usersecret=data["usersecret"],
            grey_dhcp=data["grey_dhcp"],
            grey_router=data["grey_router"],
            grey_router_dhcp_reserved=data["grey_router_dhcp_reserved"]
        )