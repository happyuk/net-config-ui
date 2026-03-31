from PySide6.QtCore import QObject, Qt, Signal, QThread
from netmiko import ConnectHandler
from app.services.ssh_service import SSHService
from app.workers.connection_test_worker import ConnectionTestWorker
from app.workers.deploy_worker import DeployWorker
from app.workers.serial_worker import SerialDeployWorker
from app.services.router_api import RouterAPI

class MainViewModel(QObject):
    deploy_log = Signal(str)
    deploy_error = Signal(str)
    deploy_progress = Signal(int)
    deploy_finished = Signal()
    test_finished = Signal(bool, str)
    log_signal = Signal(str)

    def __init__(self, config_builder, config_manager, template_setter, worker_factory=None, thread_factory=None):
        super().__init__()
        self.ssh = SSHService()
        self.config_builder = config_builder
        self.config_manager = config_manager
        self.template_setter = template_setter
         # Injected factories (for testing)
        self.worker_factory = worker_factory or DeployWorker
        self.thread_factory = thread_factory or QThread

        self._thread = None
        self._worker = None
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

    # app/viewmodel/main_viewmodel.py
    def test_ssh(self, host, user, pwd):
        try:
            # We attempt to connect. 
            # Suggestion: check if your SSHService.connect accepts a timeout parameter
            self.ssh.connect(host, user, pwd) 
            output = self.ssh.send_command("show version")
            return True, output
        except Exception as e:
            # This catches timeouts, refused connections, or bad auth
            return False, str(e)
    
    def start_deployment(self, blocks, host, user, pwd):
        if not blocks:
            self.deploy_error.emit("No deployment blocks.")
            return

        self._thread = self.thread_factory()
        self._worker = self.worker_factory(blocks, host, user, pwd)

        self._worker.moveToThread(self._thread)

        self._worker.log.connect(self.deploy_log)
        self._worker.error.connect(self.deploy_error)
        self._worker.progress.connect(self.deploy_progress)

        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._worker.finished.connect(self.deploy_finished)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

        # IMPORTANT:
        # The View (MainWindow) is now responsible for threading.

    def _on_deploy_finished_internal(self):
        self.deploy_finished.emit()
        self._thread = None
        self._worker = None

    def start_connection_test(self, mode, host, user, pwd):
        # 1. Setup the thread and worker using your existing factories
        thread = self.thread_factory()
        worker = ConnectionTestWorker(mode, self, host, user, pwd)
        worker.moveToThread(thread)
        # 2. Wire the signals (Assuming you add a 'test_finished' Signal to MainViewModel)
        worker.finished.connect(self.test_finished) 
        # 3. Standard cleanup pattern
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.started.connect(worker.run)
        thread.start()

    # In app/viewmodel/main_viewmodel.py
    def start_ssh_test(self, host, user, pwd):
        self._test_thread = self.thread_factory()
        
        # 5 arguments: mode, vm (self), host, user, pwd
        self._test_worker = ConnectionTestWorker("ssh", self, host, user, pwd) 
        self._test_worker.moveToThread(self._test_thread)
        
        # Signal connections
        self._test_worker.finished.connect(self.test_finished) 
        self._test_worker.finished.connect(self._test_thread.quit)
        self._test_worker.finished.connect(self._test_worker.deleteLater)
        self._test_thread.finished.connect(self._test_thread.deleteLater)
        self._test_thread.started.connect(self._test_worker.run)
        
        self._test_thread.start()

    def start_serial_deployment(self, port, baud, config):
        """Orchestrates the serial thread."""
        # Create the worker instance
        self.serial_worker = SerialDeployWorker(port, baud, config)

        # Connect signals to the ViewModel's own signals 
        # (Which are already connected to the MainWindow UI)
        self.serial_worker.log_signal.connect(self.deploy_log.emit)
        self.serial_worker.progress_signal.connect(self.deploy_progress.emit)
        self.serial_worker.finished_signal.connect(self.deploy_finished.emit)

        # Start the background thread
        self.serial_worker.start()


    def start_serial_deployment(self, port: str, baud: str, config: str):
        """Orchestrates the serial thread with safety checks."""
        
        # 1. SAFETY: Prevent overlapping deployments
        if hasattr(self, 'serial_worker') and self.serial_worker is not None:
            if self.serial_worker.isRunning():
                self.deploy_error.emit("[Serial] A deployment is already in progress.")
                return

        # 2. Initialize the worker
        # Ensure you have 'from app.workers.serial_worker import SerialDeployWorker' at the top
        self.serial_worker = SerialDeployWorker(port, baud, config)

        # 3. Connect signals (Wiring the worker to the VM's existing UI-connected signals)
        self.serial_worker.log_signal.connect(self.deploy_log.emit)
        self.serial_worker.progress_signal.connect(self.deploy_progress.emit)
        
        # 4. Clean up the worker object when it's done to free memory
        self.serial_worker.finished_signal.connect(self.on_serial_worker_finished)
        self.serial_worker.finished_signal.connect(self.deploy_finished.emit)

        # 5. Kick off the thread
        self.serial_worker.start()

    def on_serial_worker_finished(self):
        """Cleanup after the thread dies."""
        self.serial_worker.deleteLater()
        self.serial_worker = None


    def start_factory_reset(self, port: str, baud: str, secret: str):
        """
        Initiates the background thread for the factory reset sequence via Serial.
        """
        # 1. Create the specific block for the factory reset
        reset_block = {
            "name": "Full Factory Reset & Setup Bypass",
            "mode": "factory_reset",
            "secret": secret
        }

        # 2. Initialize the Worker
        # We pass: 
        #   host = port (e.g., /dev/ttyUSB0)
        #   user = "console" (placeholder)
        #   pwd = baud (e.g., 9600) -> The worker will use this as the baudrate
        self.worker = DeployWorker(
            blocks=[reset_block], 
            host=port, 
            user="console", 
            pwd=baud
        )

        # 3. Connect signals so the UI updates
        self.worker.log.connect(self.deploy_log.emit)
        self.worker.error.connect(self.deploy_error.emit)
        self.worker.progress.connect(self.deploy_progress.emit)
        self.worker.finished.connect(self.deploy_finished.emit)

        # 4. Start the background thread
        from PySide6.QtCore import QThread
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()
        
        self.log_signal.emit(f"[Serial] Starting Reset Thread on {port}...")