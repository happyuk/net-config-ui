from PySide6.QtCore import QObject, Signal, Slot
from netmiko import ConnectHandler
import paramiko
from app.services.deployer import Deployer
from app.services.router_api import RouterAPI

# Used to run sets of configuration blocks on a network device via a background thread
# Threads allow the user to interact with the app while these commands are being executed
class DeployWorker(QObject):
    log = Signal(str)
    error = Signal(str)
    progress = Signal(int) 
    finished = Signal()

    def __init__(self, blocks, host, user, pwd, api=None):
        super().__init__()
        self.blocks = blocks
        self.host = host
        self.user = user
        self.pwd = pwd
        self.api = api
        self._stop = False

    def stop(self):
        self._stop = True

    def _log(self, *msgs):
        """Helper to emit multiple log lines."""
        for m in msgs:
            self.log.emit(m)

    def _block_header(self, index, total, name, mode):
        self._log(
            "",
            "┌" + "─" * 45,
            f"│ BLOCK {index}/{total}: {name} [{mode.upper()}]",
            "└" + "─" * 45
        )

    def _ensure_ssh_connection(self, ssh=None):
        """Return a connected SSH client; reconnect if needed."""
        if ssh is None:
            return self._make_ssh_netmiko()
        # Optional: could add reconnection logic here if ssh is disconnected
        return ssh

    def _make_ssh_paramiko(self):
        # Paramiko is a Python library for SSH connections
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                self.host,
                username=self.user,
                password=self.pwd,
                port=22,
                allow_agent=False,
                look_for_keys=False,
                auth_timeout=15,
                banner_timeout=15,
                timeout=15,
            )
            ssh.get_transport().set_keepalive(30)
            return ssh
        except paramiko.AuthenticationException:
            # keyboard-interactive fallback
            transport = paramiko.Transport((self.host, 22))
            transport.start_client(timeout=15)
            def handler(title, instructions, prompts): 
                return [self.pwd for _ in prompts]
            transport.auth_interactive(self.user, handler)
            if not transport.is_authenticated():
                raise paramiko.AuthenticationException("keyboard-interactive auth failed")
            ssh._transport = transport
            return ssh

    def _make_ssh_netmiko(self):
        """Return a connected Netmiko SSH client."""
        device = {
            "device_type": "cisco_xr",
            "host": self.host,
            "username": self.user,
            "password": self.pwd,
            "port": 22,
        }
        return ConnectHandler(**device)

    @Slot()
    def run(self):
        try:
            # API session
            if self.api is None:
                self.api = RouterAPI(
                    self.host,
                    self.user,
                    self.pwd,
                    verify_tls=False
                )

            ssh = self._ensure_ssh_connection()
            deployer = Deployer(self.api, ssh_client=ssh)
            self._log("\n[Deploy] Running commands...")
            total = len(self.blocks)

            for idx, block in enumerate(self.blocks, start=1):
                if self._stop:
                    self._log("\n[Deploy] Cancel requested. Stopping…")
                    break

                if total > 0:
                    self.progress.emit(int((idx - 1) / total * 100))

                name = block.get("name", f"block-{idx}")
                mode = block.get("mode", "?")

                if mode == "cli":
                    ssh = self._ensure_ssh_connection()
                    deployer.ssh = ssh

                try:
                    blk_name, resp = deployer.deploy_block(block)
                except Exception as e:
                    self.error.emit(
                        f"[Deploy] ({idx}/{total}) ERROR in {name}: {e}"
                    )
                    continue

                status = getattr(resp, "status_code", "n/a")
                status_map = {200: "OK", 204: "No Content"}
                status_str = f"{status} {status_map.get(status, '')}".strip()
                self._log(f"Status  : {status_str}")

                if mode == "restconf":
                    self._log(
                        f"Method  : {block.get('method', 'PATCH')}",
                        f"Resource: {block.get('resource', '')}",
                        "Payload :",
                        str(block.get("payload", {}))
                    )

                self._log("-" * 60)

                if getattr(resp, "text", None):
                    cleaned = resp.text.strip()
                    self._log(
                        "── Device Output ───────────────────────────────",
                        cleaned,
                        "────────────────────────────────────────────────"
                    )

            if total > 0:
                self.progress.emit(100)

        except Exception as e:
            self.error.emit(f"[Deploy] Fatal error: {e}")

        finally:
            self.finished.emit()