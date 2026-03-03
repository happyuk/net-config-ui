# app/gui/main_window.py
import paramiko

# app/gui/main_window.py (imports at top)
from PySide6.QtCore import Qt, QSettings, QThread
# ...
from app.gui.deploy_worker import DeployWorker


from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox
)
from PySide6.QtCore import Qt, QSettings

from app.services.blocks import build_blocks, set_block_set
from app.services.deployer import Deployer
from app.services.loader import NODE_OBR_ASSIGNMENT
from app.gui.config_builder import ConfigBuilder
from app.services.router_api import RouterAPI
from app.services.ip_utils import add_to_last_octet


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # ---- services ----
        self.settings = QSettings("QinetiQ", "DVRConfigBuilder")
        self.config_builder = ConfigBuilder()
        self.api = None

        # ---- UI ----
        self.setWindowTitle("DVR Router Config Builder")
        self.resize(1000, 650)

        self.init_inputs()
        self.restore_settings()     # Load saved values AFTER creating widgets
        self.init_forms()
        self.init_output()
        self.init_layout()
        

    # ============================================================
    # UI SETUP
    # ============================================================

    def init_inputs(self):
        """Create all input widgets."""
        # Template selector
        self.template_mode = QComboBox()
        self.template_mode.addItems(["DVR Pre-Cert", "DVR Post-Cert"])

        # DVR selection
        self.template_mode.currentTextChanged.connect(self.on_template_changed)

        # Node selection
        self.nodenumber = QComboBox()
        self.nodenumber.setEditable(False)
        try:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys(), key=lambda k: int(k))
        except ValueError:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys())
        self.nodenumber.addItems(keys)

        # Basic fields
        self.domain = QLineEdit();      self.domain.setPlaceholderText("e.g., o")
        self.domain.setText("o")

        self.secret = QLineEdit();      self.secret.setPlaceholderText("enable secret")
        self.secret.setText("DC2e*1234!")

        self.username = QLineEdit();    self.username.setPlaceholderText("e.g., admin")
        self.username.setText("admin")

        self.usersecret = QLineEdit()
        self.usersecret.setPlaceholderText("password/secret")
        self.usersecret.setEchoMode(QLineEdit.Password)
        self.usersecret.setText("DC2e*1234!")

        # Device fields
        self.device_host = QLineEdit(); self.device_host.setPlaceholderText("192.168.16.111")
        self.device_user = QLineEdit(); self.device_user.setPlaceholderText("admin")
        self.device_pass = QLineEdit(); self.device_pass.setPlaceholderText("device password")
        self.device_pass.setEchoMode(QLineEdit.Password)

        # Calculated grey-IP fields
        self.grey_dhcp = QLineEdit();          self.grey_dhcp.setReadOnly(True)
        self.grey_router = QLineEdit();        self.grey_router.setReadOnly(True)
        self.grey_dhcp_reserved = QLineEdit(); self.grey_dhcp_reserved.setReadOnly(True)

        # Buttons
        self.generate = QPushButton("Generate config")
        self.generate.clicked.connect(self.on_generate)

        self.test_api = QPushButton("Test RESTCONF")
        self.test_api.clicked.connect(self.on_test_restconf_api)

        self.deploy_full_btn = QPushButton("Deploy")
        self.deploy_full_btn.clicked.connect(self.on_deploy_full)

    def init_forms(self):
        """Left + right forms."""
        # Left form inputs
        self.left_form = QFormLayout()
        self.left_form.addRow("Node Number:", self.nodenumber)
        self.left_form.addRow("Template:", self.template_mode)
        self.left_form.addRow("Domain:", self.domain)
        self.left_form.addRow("Secret:", self.secret)
        self.left_form.addRow("Username:", self.username)
        self.left_form.addRow("User Secret:", self.usersecret)
        self.left_form.addRow(QLabel("— Device (optional) —"))
        self.left_form.addRow("Host:", self.device_host)
        self.left_form.addRow("User:", self.device_user)
        self.left_form.addRow("Pass:", self.device_pass)

        # Right form output
        self.right_form = QFormLayout()
        self.right_form.addRow("Grey DHCP:", self.grey_dhcp)
        self.right_form.addRow("Grey Router:", self.grey_router)
        self.right_form.addRow("Grey DHCP Reserved:", self.grey_dhcp_reserved)

    def init_output(self):
        """Output text area."""
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.clear()

    def init_layout(self):
        """Final layout assembly."""
        hbox = QHBoxLayout()
        hbox.addLayout(self.left_form, stretch=1)
        hbox.addSpacing(40)
        hbox.addLayout(self.right_form, stretch=1)

        buttons = QHBoxLayout()
        buttons.addWidget(self.generate)
        buttons.addWidget(self.test_api)
        buttons.addWidget(self.deploy_full_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(hbox)
        main_layout.addLayout(buttons)
        main_layout.addWidget(QLabel("Output:"))
        main_layout.addWidget(self.output)

        self.setLayout(main_layout)

    # ============================================================
    # SETTINGS
    # ============================================================

    def restore_settings(self):
        """Load saved user/device settings."""
        s = self.settings

        self.device_host.setText(s.value("device/host", ""))
        self.device_user.setText(s.value("device/user", ""))
        self.device_pass.setText(s.value("device/pass", ""))

        self.template_mode.setCurrentText(s.value("ui/template_mode", "DVR Pre-Cert"))
        self.nodenumber.setCurrentText(s.value("ui/node_number", self.nodenumber.currentText()))
        self.domain.setText(s.value("ui/domain", self.domain.text()))
        self.username.setText(s.value("ui/username", self.username.text()))

    def save_settings(self):
        """Write settings to disk."""
        s = self.settings
        s.setValue("device/host", self.device_host.text().strip())
        s.setValue("device/user", self.device_user.text().strip())
        s.setValue("device/pass", self.device_pass.text().strip())
        s.setValue("ui/template_mode", self.template_mode.currentText())
        s.setValue("ui/node_number", self.nodenumber.currentText())
        s.setValue("ui/domain", self.domain.text().strip())
        s.setValue("ui/username", self.username.text().strip())

    # Save when window closes
    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    # ============================================================
    # LOGIC
    # ============================================================

    def populate_grey_fields(self, node: str):
        """Calculate grey fields based on JSON config."""
        if node not in NODE_OBR_ASSIGNMENT:
            self.grey_dhcp.setText("Node not found")
            self.grey_router.clear()
            self.grey_dhcp_reserved.clear()
            return

        lookup = NODE_OBR_ASSIGNMENT[node]
        vlan10 = lookup["vlan_10_address_space"]
        network_base = vlan10.split("/")[0]

        self.grey_dhcp.setText(network_base)
        self.grey_router.setText(add_to_last_octet(network_base, 1))
        self.grey_dhcp_reserved.setText(add_to_last_octet(network_base, 4))

    def selected_template(self):
        mode = self.template_mode.currentText()
        if mode == "DVR Pre-Cert":
            return "dvr/precert"
        if mode == "DVR Post-Cert":
            return "dvr/postcert"
        return None

    def on_generate(self):
        self.save_settings()

        node = self.nodenumber.currentText().strip()
        self.populate_grey_fields(node)

        # NEW — switch the template set
        blockset = self.selected_template()
        if blockset:
            set_block_set(blockset)

        mode = self.template_mode.currentText()

        cfg = self.config_builder.build_from_label(
            mode,
            node_number=node,
            domain=self.domain.text().strip(),
            secret=self.secret.text().strip()
        )

        self.output.setPlainText(cfg)

    def on_deploy_hostname(self):
        self.output.clear()

        hostname = f"N{self.nodenumber.currentText()}{self.domain.text()}002DVR001"

        deployer = Deployer(self.api)
        resp = deployer.deploy_hostname(hostname)

        self.output.append(f"Hostname deployment response: {resp.status_code}")
        self.output.append(resp.text)

    def on_test_restconf_api(self):
        self.output.clear()
        self.save_settings()

        host = self.device_host.text().strip()
        user = self.device_user.text().strip()
        pwd = self.device_pass.text().strip()

        if not (host and user and pwd):
            self.output.append("\n[API] Please fill Host/User/Pass to test RESTCONF.")
            return

        try:
            # Create API (your original works)
            self.api = RouterAPI(host, user, pwd, verify_tls=False)

            ok, msg = self.api.ping()
            self.output.append(f"[API] {msg}")

            # Optional: if you want to also show a tiny JSON sample when reachable
            if ok:
                r = self.api.get_native_hostname()
                self.output.append(f"[API] Sample GET native/hostname -> {r.status_code}")
                # To avoid huge paste, only show first 2k chars
                body = r.text or ""
                self.output.append(body[:2000] + ("..." if len(body) > 2000 else ""))

        except Exception as e:
            self.output.append(f"\n[API] Error: {e}")

    def on_deploy_full(self):
        self.output.clear()
        self.save_settings()

        # ensure block-set aligns with the current dropdown selection
        blockset = self.selected_template()
        if blockset:
            set_block_set(blockset)

        # 1) Extract host/user/pass
        host = self.device_host.text().strip()
        user = self.device_user.text().strip()
        pwd  = self.device_pass.text().strip()

        if not (host and user and pwd):
            self.output.append("[Deploy] Missing device host/user/pass.")
            return

        # 2) Reuse or create RESTCONF API session (optional; worker can create its own)
        if not self.api:
            self.api = RouterAPI(host, user, pwd, verify_tls=False)

        # 3) Build blocks
        node   = self.nodenumber.currentText().strip()
        domain = self.domain.text().strip()
        blocks = build_blocks(node_number=node, domain=domain)

        # 4) Preview Execution Plan (in GUI thread)
        self.output.append("[Deploy] Execution Plan:")
        for i, b in enumerate(blocks, start=1):
            name = b.get("name", f"block-{i}")
            mode = b.get("mode", "?")
            if mode == "restconf":
                method = b.get("method", "PATCH")
                resource = b.get("resource", "")
                self.output.append(f"  {i:02d}. {name} [{mode}] {method} {resource}")
            elif mode == "cli":
                cmd_count = len(b.get("commands", []))
                self.output.append(f"  {i:02d}. {name} [{mode}] {cmd_count} command(s)")
            else:
                self.output.append(f"  {i:02d}. {name} [{mode}]")

        self.output.append("")  # spacer

        # 5) Start threaded deployment
        self.deploy_thread = QThread(self)
        self.deploy_worker = DeployWorker(blocks, host, user, pwd, api=self.api)
        self.deploy_worker.moveToThread(self.deploy_thread)

        # Connect signals
        self.deploy_worker.log.connect(self.output.append)
        self.deploy_worker.error.connect(self.output.append)
        self.deploy_worker.finished.connect(self._on_deploy_finished)

        self.deploy_thread.started.connect(self.deploy_worker.run)
        self.deploy_thread.finished.connect(self.deploy_thread.deleteLater)

        # Disable buttons while running
        self._set_busy(True)

        self.deploy_thread.start()
    
    def _make_ssh(self, host: str, user: str, pwd: str) -> paramiko.SSHClient:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # Try plain password auth first (most IOS-XE)
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

            # Enable SSH keepalive packets (helps prevent idle drops)
            try:
                transport = ssh.get_transport()
                if transport:
                    transport.set_keepalive(30)  # seconds
            except Exception:
                pass

            return ssh

        except paramiko.AuthenticationException:
            # Some AAA configs use keyboard-interactive; try that explicitly
            try:
                transport = paramiko.Transport((host, 22))
                transport.start_client(timeout=15)

                # Simple handler that just supplies the same password to all prompts
                def handler(title, instructions, prompts):
                    # prompts is a list of tuples: (prompt_text, echo)
                    return [pwd for _ in prompts]

                transport.auth_interactive(user, handler)
                if not transport.is_authenticated():
                    raise paramiko.AuthenticationException("keyboard-interactive auth failed")

                # Bind the authenticated transport to a new SSHClient
                ssh = paramiko.SSHClient()
                ssh._transport = transport
                return ssh

            except Exception as e:
                raise paramiko.AuthenticationException(f"SSH auth failed (password & keyboard-interactive): {e}") from e

        except Exception as e:
            # Network / cipher / banner issues etc.
            raise RuntimeError(f"SSH connection failed: {e}") from e

    def _ensure_ssh_active(self, ssh: paramiko.SSHClient, host: str, user: str, pwd: str) -> paramiko.SSHClient:
        """
        Ensure the SSHClient has an active transport; reconnect if needed.
        """
        transport = ssh.get_transport()
        if transport is None or not transport.is_active():
            # Recreate a fresh SSH client
            ssh = self._make_ssh(host, user, pwd)
        else:
            # Set keepalives (seconds) to mitigate idle drops
            try:
                transport.set_keepalive(30)
            except Exception:
                pass
        return ssh
    

    def _on_deploy_finished(self):
        try:
            self.output.append("\n[Deploy] Done.")
        finally:
            # Cleanup worker and thread objects
            try:
                self.deploy_thread.quit()
            except Exception:
                pass
            try:
                self.deploy_worker.deleteLater()
            except Exception:
                pass
            self._set_busy(False)

    def _set_busy(self, busy: bool):
        # Optional: change cursor and disable controls
        self.setCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)
        for btn in (self.generate, self.test_api, self.deploy_full_btn):
            btn.setEnabled(not busy)

    def on_template_changed(self, value: str):
        """
        Update the active block-set folder when the template dropdown is changed.
        """
        if not hasattr(self, "output"):
            return
        if value == "DVR Pre-Cert":
            set_block_set("dvr/precert")
            self.output.append("[Info] Switched to PRE-CERT template set.")
        elif value == "DVR Post-Cert":
            set_block_set("dvr/postcert")
            self.output.append("[Info] Switched to POST-CERT template set.")
        else:
            self.output.append("[Warning] Unknown template mode selected.")