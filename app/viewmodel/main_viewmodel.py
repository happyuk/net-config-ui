from PySide6.QtCore import QObject, Qt, Signal, QThread
from app.workers.deploy_worker import DeployWorker
from app.services.router_api import RouterAPI

class MainViewModel(QObject):
    deploy_log = Signal(str)
    deploy_error = Signal(str)
    deploy_progress = Signal(int)
    deploy_finished = Signal()

    def __init__(self, config_builder, config_manager, template_setter):
        super().__init__()
        self.config_builder = config_builder
        self.config_manager = config_manager
        self.template_setter = template_setter
        self._thread = None
        self._worker = None

    # ---------------------------
    # Business logic
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
    
    def prepare_deploy_blocks(self, raw_text: str):
        commands = [line.strip() for line in raw_text.splitlines() if line.strip()]

        if not commands:
            return None, "No commands in output box."

        blocks = [{
            "name": "manual-output",
            "mode": "cli",
            "commands": commands
        }]

        return blocks, None
    
    def validate_device(self, host, user, pwd):
        if not (host and user and pwd):
            return False, "Missing device host/user/pass."
        return True, None
    
    def generate_config(self, node, mode, form_data):
        ips = self.get_ips(node)

        if ips:
            form_data.update({
                "grey_dhcp": ips["dhcp"],
                "grey_router": ips["router"],
                "grey_router_dhcp_reserved": ips["reserved"]
            })

        self.apply_template(mode)

        config = self.build_config(mode, node, form_data)

        return {
            "config": config,
            "ips": ips
        }
    
    def prepare_deployment(self, raw_text, host, user, pwd):
        ok, err = self.validate_device(host, user, pwd)
        if not ok:
            return None, err

        blocks, err = self.prepare_deploy_blocks(raw_text)
        if err:
            return None, err

        return blocks, None
    
    def test_restconf(self, host, user, pwd):
        if not (host and user and pwd):
            return False, "[API] Missing credentials", None

        try:
            api = RouterAPI(host, user, pwd, verify_tls=False)

            ok, msg = api.ping()

            extra = None
            if ok:
                r = api.get_native_hostname()
                extra = (r.status_code, r.text[:2000])

            return ok, msg, extra

        except Exception as e:
            return False, str(e), None
    
    def start_deployment(self, blocks, host, user, pwd):
        if not blocks:
            self.deploy_error.emit("No deployment blocks.")
            return

        # Create thread + worker
        self._thread = QThread()
        self._worker = DeployWorker(blocks, host, user, pwd)

        self._worker.moveToThread(self._thread)

        # Connect worker → ViewModel signals
        self._worker.log.connect(self.deploy_log)
        self._worker.error.connect(self.deploy_error)
        self._worker.progress.connect(self.deploy_progress)

        # Lifecycle management
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # When done, notify UI
        self._worker.finished.connect(self._on_deploy_finished_internal)

        # Start execution
        self._thread.started.connect(self._worker.run, Qt.QueuedConnection)
        self._thread.start()

    def _on_deploy_finished_internal(self):
        self.deploy_finished.emit()
        self._thread = None
        self._worker = None