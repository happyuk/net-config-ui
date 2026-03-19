# app/gui/main_window.py
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QGroupBox, QProgressBar, QSplitter, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QFormLayout, QComboBox
)

from app.domain.config_blocks import set_selected_template_set
from app.infrastructure.loader import NODE_OBR_ASSIGNMENT
from app.domain.config_builder import ConfigBuilder
from app.domain.config_manager import ConfigManager
from app.services.router_api import RouterAPI
from app.viewmodel.main_viewmodel import MainViewModel


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
    ("Username", "device_user", QLineEdit),
    ("Password", "device_pass", QLineEdit)
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

        self.init_inputs()
        self.restore_settings()     # Load saved values AFTER creating widgets
        self.init_forms()
        self.init_output()
        self.init_layout()

        self.vm = MainViewModel(
            config_builder=self.config_builder,
            config_manager=ConfigManager,
            template_setter=set_selected_template_set
        )
        self.api = None
        self.vm.deploy_log.connect(self.log)
        self.vm.deploy_error.connect(self.log)
        self.vm.deploy_progress.connect(self.progressBar.setValue)
        self.vm.deploy_finished.connect(self.on_deploy_finished)

        # ---- UI ----
        self.setWindowTitle("Router Config Builder")
        self.resize(1000, 650)


    # ============================================================
    # UI SETUP
    # ============================================================

    def init_inputs(self):
        """Create all input widgets."""
        self.widgets = {}
        self.ssh_status_label = QLabel("")

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
        self.generate = QPushButton("Generate node configuration")
        self.generate.clicked.connect(self.on_generate_config)

        self.test_api = QPushButton("Test RESTCONF")
        self.test_api.clicked.connect(self.on_test_restconf_api)
        self.test_api.hide()

        self.deploy_full_btn = QPushButton("Deploy configuration commands")
        self.deploy_full_btn.clicked.connect(self.on_deploy_full)

        self.copy_btn = QPushButton("Copy Output Text")
        self.copy_btn.clicked.connect(self.on_copy_output)

        self.clear_btn = QPushButton("Clear Output Text")
        self.clear_btn.clicked.connect(self.on_clear_output)

        self.test_ssh_btn = QPushButton("Test Access")
        self.test_ssh_btn.clicked.connect(self.on_test_ssh)

    def init_forms(self):
        """Create separate forms for configuration and device credentials."""

        # =========================
        # CONFIGURATION FORM
        # =========================
        self.left_form = QFormLayout()

        for label, name, _ in LEFT_FIELDS:
            self.left_form.addRow(f"{label}:", self.widgets[name])

        # =========================
        # DEVICE FORM (NEW)
        # =========================
        self.device_form = QFormLayout()

        for label, name, _ in DEVICE_FIELDS:
            self.device_form.addRow(f"{label}:", self.widgets[name])

        # =========================
        # RIGHT FORM
        # =========================
        self.right_form = QFormLayout()

        for label, name in RIGHT_FIELDS:
            self.right_form.addRow(f"{label}:", self.widgets[name])


    def init_output(self):
        """Output text area as CLI-style terminal."""
        self.output = QTextEdit()
        self.output.setReadOnly(False)
        self.output.clear()

        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)

        palette = self.output.palette()
        palette.setColor(QPalette.Base, QColor("black"))
        palette.setColor(QPalette.Text, QColor(230, 230, 230))
        self.output.setPalette(palette)

        self.output.setLineWrapMode(QTextEdit.NoWrap)
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.hide() 

    from PySide6.QtWidgets import QSplitter, QGroupBox

    def init_layout(self):
        # =========================
        # LEFT PANEL
        # =========================
        left_panel = QWidget()
        left_layout = QVBoxLayout()

        # ---- Device SSH Credentials ----
        device_box = QGroupBox("Device Access: SSH")
        device_box.setObjectName("deviceBox")
        device_layout = QVBoxLayout()
        device_layout.addLayout(self.device_form)
        device_layout.addWidget(self.test_ssh_btn)
        device_box.setLayout(device_layout)
        left_layout.addWidget(device_box)

        # ---- Configuration ----
        form_box = QGroupBox("Node Configuration")
        form_box.setLayout(self.left_form)
        left_layout.addWidget(form_box)

        # ---- Actions ----
        actions_box = QGroupBox("Actions")
        actions_box.setObjectName("actionsBox")
        actions_layout = QVBoxLayout()

        actions_layout.addWidget(self.generate)
        actions_layout.addWidget(self.test_api)
        actions_layout.addWidget(self.deploy_full_btn)
        actions_layout.addWidget(self.copy_btn)
        actions_layout.addWidget(self.clear_btn)

        actions_layout.addStretch()

        actions_box.setLayout(actions_layout)

        left_layout.addWidget(actions_box)

        #left_layout.addStretch()
        left_panel.setLayout(left_layout)

        # =========================
        # RIGHT PANEL
        # =========================
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_layout.addWidget(self.output)
        output_box.setLayout(output_layout)

        right_layout.addWidget(output_box)
        right_layout.addWidget(self.progressBar)

        right_panel.setLayout(right_layout)

        # =========================
        # SPLITTER
        # =========================
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 700])

        self.splitter = splitter

        # =========================
        # MAIN LAYOUT
        # =========================
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        main_layout.addWidget(splitter)
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

        result = self.vm.generate_config(
            node=self.nodenumber.currentText().strip(),
            mode=self.template_mode.currentText(),
            form_data=self.collect_form_data()
        )

        if result["ips"]:
            self.grey_dhcp.setText(result["ips"]["dhcp"])
            self.grey_router.setText(result["ips"]["router"])
            self.grey_router_dhcp_reserved.setText(result["ips"]["reserved"])

        self.output.setPlainText(result["config"])

    def on_test_restconf_api(self):
        self.output.clear()

        host, user, pwd = self.get_device_credentials()

        ok, msg, extra = self.vm.test_restconf(host, user, pwd)

        self.log(f"[API] {msg}")

        if extra:
            code, body = extra
            self.log(f"[API] Status: {code}")
            self.log(body)

    def on_deploy_full(self):
        self.save_settings()

        host, user, pwd = self.get_device_credentials()

        blocks, err = self.vm.prepare_deployment(
            self.output.toPlainText(),
            host, user, pwd
        )

        if err:
            self.log(f"[Deploy] {err}")
            return

        self.progressBar.setValue(0)
        self._set_busy(True)

        # Delegated to ViewModel
        self.vm.start_deployment(blocks, host, user, pwd)

    def _set_busy(self, busy: bool):
        self.setCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)
        for btn in (self.generate, self.test_api, self.deploy_full_btn):
            btn.setEnabled(not busy)
        if busy:
            self.progressBar.show()
        else:
            self.progressBar.hide()

    def on_template_changed(self, value: str):
        """Update the template set whenever the dropdown changes."""
        # 1. Prevents crashing during initial window startup
        if not hasattr(self, "output"):
            return

        path = self.vm.apply_template(value)
        if path:
            self.log(f"[Info] Switched to {value.upper()} template set.")
        else:
            self.log(f"[Warning] No template path found for: {value}")

    def on_copy_output(self):
        """Copies the text from the output box to the system clipboard."""
        text = self.output.toPlainText()
        if text:
            # Access the application-wide clipboard
            from PySide6.QtGui import QGuiApplication
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            self.log("\n[System] Output copied to clipboard.")

    from netmiko import ConnectHandler

    def on_test_ssh(self):
        self.on_clear_output()

        host, user, pwd = self.get_device_credentials()

        self.log(f"Connecting to {host}...")

        ok, result = self.vm.test_ssh(host, user, pwd)

        if ok:
            self.log("SSH connection successful")
            self.log(result[:500])
        else:
            self.log(f"SSH connection failed: {result}")

    def on_clear_output(self):
        """Clear the text from the output box"""
        self.output.clear()
    
    def log(self, msg: str):
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(msg + "\n")
        self.output.ensureCursorVisible()

    def get_device_credentials(self):
        return (
            self.device_host.text().strip(),
            self.device_user.text().strip(),
            self.device_pass.text().strip()
        )
    
    def collect_form_data(self):
        return {
            "domain": self.domain.text().strip(),
            "secret": self.secret.text().strip(),
            "username": self.username.text().strip(),
            "usersecret": self.usersecret.text(),
            "grey_dhcp": self.grey_dhcp.text(),
            "grey_router": self.grey_router.text(),
            "grey_router_dhcp_reserved": self.grey_router_dhcp_reserved.text()
        }
    
    def on_deploy_finished(self):
        self._set_busy(False)
        self.log("\n[Deploy] Done.")