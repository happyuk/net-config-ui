# app/gui/deploy_worker.py
from PySide6.QtCore import QObject, Signal, Slot
import paramiko
from app.services.deployer import Deployer
from app.services.router_api import RouterAPI

class DeployWorker(QObject):
    # Signals back to the GUI thread
    log = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, blocks, host, user, pwd, api=None):
        super().__init__()
        self.blocks = blocks
        self.host = host
        self.user = user
        self.pwd = pwd
        self.api = api  # Optional existing RouterAPI
        self._stop = False

    def stop(self):
        """Allow cancel if you wire a Cancel button."""
        self._stop = True

    @Slot()
    def run(self):
        """
        Run the deployment in a background thread. Emit log strings to update the GUI.
        """
        try:
            # Build API if not supplied
            if self.api is None:
                self.api = RouterAPI(self.host, self.user, self.pwd, verify_tls=False)

            # Ensure SSH for CLI blocks
            ssh = self._make_ssh(self.host, self.user, self.pwd)
            ssh = self._ensure_ssh_active(ssh)

            deployer = Deployer(self.api, ssh_client=ssh)

            self.log.emit("\n[Deploy] Running blocks...")

            for index, block in enumerate(self.blocks, start=1):
                if self._stop:
                    self.log.emit("\n[Deploy] Cancel requested. Stopping…")
                    break

                name = block.get("name", f"block-{index}")
                mode = block.get("mode", "?")

                # Header for each block
                self.log.emit("")
                self.log.emit(f"┌───────────────────────────────────────────────")
                self.log.emit(f"│ BLOCK {index}/{len(self.blocks)}: {name} [{mode.upper()}]")
                self.log.emit(f"└───────────────────────────────────────────────")

                # Ensure SSH alive for CLI blocks
                if mode == "cli":
                    ssh = self._ensure_ssh_active(ssh)
                    # For certain devices it’s safer to open a fresh session per block
                    ssh = self._make_ssh(self.host, self.user, self.pwd)
                    deployer.ssh = ssh

                # Execute the block
                try:
                    blk_name, resp = deployer.deploy_block(block)
                except Exception as e:
                    self.error.emit(f"[Deploy] ({index}/{len(self.blocks)}) ERROR in {name}: {e}")
                    continue

                # Status + details
                status = getattr(resp, "status_code", "n/a")
                text = getattr(resp, "text", "")

                sc = f"{status}"
                if status == 204:
                    sc += " No Content"
                elif status == 200:
                    sc += " OK"

                self.log.emit(f"Status  : {sc}")

                if mode == "restconf":
                    method   = block.get("method", "PATCH")
                    resource = block.get("resource", "")
                    payload  = block.get("payload", {})
                    self.log.emit(f"Method  : {method}")
                    self.log.emit(f"Resource: {resource}")
                    self.log.emit("Payload :")
                    self.log.emit(str(payload))

                self.log.emit("-" * 60)

                if text:
                    cleaned = text.strip()
                    self.log.emit("── Device Output ───────────────────────────────")
                    # Simply emit the full string without checking length
                    self.log.emit(cleaned)
                    self.log.emit("────────────────────────────────────────────────")

        except Exception as e:
            self.error.emit(f"[Deploy] Fatal error: {e}")
        finally:
            self.finished.emit()

    # ---------- SSH helpers (copied/adapted from your MainWindow) ----------
    def _make_ssh(self, host: str, user: str, pwd: str) -> paramiko.SSHClient:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                host,
                username=user,
                password=pwd,
                port=22,
                allow_agent=False,
                look_for_keys=False,
                auth_timeout=15,
                banner_timeout=15,
                timeout=15,
            )

            try:
                transport = ssh.get_transport()
                if transport:
                    transport.set_keepalive(30)
            except Exception:
                pass

            return ssh

        except paramiko.AuthenticationException:
            # Try keyboard-interactive
            transport = paramiko.Transport((host, 22))
            transport.start_client(timeout=15)

            def handler(title, instructions, prompts):
                return [pwd for _ in prompts]

            transport.auth_interactive(user, handler)
            if not transport.is_authenticated():
                raise paramiko.AuthenticationException("keyboard-interactive auth failed")

            ssh = paramiko.SSHClient()
            ssh._transport = transport
            return ssh

    def _ensure_ssh_active(self, ssh: paramiko.SSHClient) -> paramiko.SSHClient:
        transport = ssh.get_transport()
        if transport is None or not transport.is_active():
            ssh = self._make_ssh(self.host, self.user, self.pwd)
        else:
            try:
                transport.set_keepalive(30)
            except Exception:
                pass
        return ssh