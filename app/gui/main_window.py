# app/gui/main_window.py
from PySide6.QtCore import Qt, QSettings, QThread
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout,
    QFormLayout, QComboBox
)

from app.gui.deploy_worker import DeployWorker
from app.services.blocks import set_selected_template_set
from app.services.loader import NODE_OBR_ASSIGNMENT
from app.gui.config_builder import ConfigBuilder
from app.services.router_api import RouterAPI
from app.services.config_manager import ConfigManager

LEFT_FIELDS = [
    ("Node Number", "nodenumber", QComboBox),
    ("Template", "template_mode", QComboBox),
    ("Domain", "domain", QLineEdit),
    ("Secret", "secret", QLineEdit),
    ("Username", "username", QLineEdit),
    ("User Secret", "usersecret", QLineEdit),
]

DEVICE_FIELDS = [
    ("Host", "device_host", QLineEdit),
    ("User", "device_user", QLineEdit),
    ("Pass", "device_pass", QLineEdit),
]

RIGHT_FIELDS = [
    ("Grey DHCP", "grey_dhcp"),
    ("Grey Router", "grey_router"),
    ("Grey DHCP Reserved", "grey_router_dhcp_reserved"),
]

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # ---- services ----
        self.settings = QSettings("QinetiQ", "DVRConfigBuilder")
        self.config_builder = ConfigBuilder()
        self.api = None

        # ---- UI ----
        self.setWindowTitle("Router Config Builder")
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
        self.widgets = {}

        # Create left side widgets
        for label, name, widget_type in LEFT_FIELDS:
            w = widget_type()

            if name == "usersecret":
                w.setEchoMode(QLineEdit.Password)

            setattr(self, name, w)
            self.widgets[name] = w

        # Create device widgets
        for label, name, widget_type in DEVICE_FIELDS:
            w = widget_type()

            if name == "device_pass":
                w.setEchoMode(QLineEdit.Password)

            setattr(self, name, w)
            self.widgets[name] = w

        # Create right side widgets (readonly)
        for label, name in RIGHT_FIELDS:
            w = QLineEdit()
            w.setReadOnly(True)

            setattr(self, name, w)
            self.widgets[name] = w

        # Populate template dropdown
        self.template_mode.addItems([
            "DVR Pre-Cert",
            "DVR Post-Cert",
            "OBR Pre-Cert",
            "OBR Post-Cert",
            "Show Running Config"
        ])

        self.template_mode.currentTextChanged.connect(self.on_template_changed)

        # Populate node dropdown
        self.nodenumber.setEditable(False)

        try:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys(), key=lambda k: int(k))
        except ValueError:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys())

        self.nodenumber.addItems(keys)

        # Default values
        self.domain.setText("o")
        self.secret.setText("DC2e*1234!")
        self.username.setText("admin")
        self.usersecret.setText("DC2e*1234!")

        self.device_host.setPlaceholderText("192.168.16.111")
        self.device_user.setPlaceholderText("admin")
        self.device_pass.setPlaceholderText("device password")

        # Buttons
        self.generate = QPushButton("Generate config")
        self.generate.clicked.connect(self.on_generate_config)

        self.test_api = QPushButton("Test RESTCONF")
        self.test_api.clicked.connect(self.on_test_restconf_api)
        self.test_api.hide()

        self.deploy_full_btn = QPushButton("Deploy")
        self.deploy_full_btn.clicked.connect(self.on_deploy_full)

        self.copy_btn = QPushButton("Copy Output")
        self.copy_btn.clicked.connect(self.on_copy_output)


    def init_forms(self):
        """Left + right forms."""

        self.left_form = QFormLayout()

        for label, name, _ in LEFT_FIELDS:
            self.left_form.addRow(f"{label}:", self.widgets[name])

        self.left_form.addRow(QLabel("— Device (optional) —"))

        for label, name, _ in DEVICE_FIELDS:
            self.left_form.addRow(f"{label}:", self.widgets[name])

        self.right_form = QFormLayout()

        for label, name in RIGHT_FIELDS:
            self.right_form.addRow(f"{label}:", self.widgets[name])         

    def init_output(self):
        """Output text area as CLI-style terminal."""
        self.output = QTextEdit()
        self.output.setReadOnly(False)
        self.output.clear()

        # Monospace font
        self.output.setFont(QFont("Courier New", 10))

        # Black background, white text
        palette = self.output.palette()
        palette.setColor(QPalette.Base, QColor("black"))
        palette.setColor(QPalette.Text, QColor("white"))
        self.output.setPalette(palette)

        # Optional: wrap text off to mimic CLI
        self.output.setLineWrapMode(QTextEdit.NoWrap)

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
        buttons.addWidget(self.copy_btn)

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

    def on_generate_config(self):
        self.save_settings()
        node = self.nodenumber.currentText().strip()
        mode = self.template_mode.currentText()

        # 1. Logic: Get IPs from the Manager
        ips = ConfigManager.get_grey_ips(node)
        if ips:
            self.grey_dhcp.setText(ips["dhcp"])
            self.grey_router.setText(ips["router"])
            self.grey_router_dhcp_reserved.setText(ips["reserved"])

        # 2. Logic: Handle Template Switching
        path = ConfigManager.get_template_path(mode)
        if path:
            set_selected_template_set(path)

        # 3. Build the config
        cfg = self.config_builder.build_from_label(
            mode,
            node_number=node,
            domain=self.domain.text().strip(),
            secret=self.secret.text().strip(),
            username=self.username.text().strip(),
            usersecret=self.usersecret.text(),
            grey_dhcp=self.grey_dhcp.text(),
            grey_router=self.grey_router.text(),
            grey_router_dhcp_reserved=self.grey_router_dhcp_reserved.text()
        )

        self.output.setPlainText(cfg)

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
        self.save_settings()

        host = self.device_host.text().strip()
        user = self.device_user.text().strip()
        pwd  = self.device_pass.text().strip()

        if not (host and user and pwd):
            self.output.append("[Deploy] Missing device host/user/pass.")
            return

        # Extract commands from output text and put into an array
        raw_text = self.output.toPlainText()
        commands = [line.strip() for line in raw_text.splitlines() if line.strip()]

        if not commands:
            self.output.append("[Deploy] No commands in output box.")
            return

        # Wrap into a single CLI block
        blocks = [{
            "name": "manual-output",
            "mode": "cli",
            "commands": commands
        }]
        self.deploy_thread = QThread(self)
        self.deploy_worker = DeployWorker(blocks, host, user, pwd, api=self.api)
        self.deploy_worker.moveToThread(self.deploy_thread)

        self.deploy_worker.log.connect(self.output.append)
        self.deploy_worker.error.connect(self.output.append)
        self.deploy_worker.finished.connect(self._on_deploy_finished)

        self.deploy_thread.started.connect(self.deploy_worker.run)
        self.deploy_thread.finished.connect(self.deploy_thread.deleteLater)

        self._set_busy(True)
        self.deploy_thread.start()

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
        """Update the template set whenever the dropdown changes."""
        # 1. Prevents crashing during initial window startup
        if not hasattr(self, "output"):
            return

        path = ConfigManager.get_template_path(value)
        
        if path:
            set_selected_template_set(path)
            self.output.append(f"[Info] Switched to {value.upper()} template set.")
        else:
            self.output.append(f"[Warning] No template path found for: {value}")

    def on_copy_output(self):
        """Copies the text from the output box to the system clipboard."""
        text = self.output.toPlainText()
        if text:
            # Access the application-wide clipboard
            from PySide6.QtGui import QGuiApplication
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            
            # Optional: provide a small visual hint in the output
            self.output.append("\n[System] Output copied to clipboard.")