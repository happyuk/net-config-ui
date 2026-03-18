# app/gui/main_window.py
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QProgressBar, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout,
    QFormLayout, QComboBox
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

        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)

        palette = self.output.palette()
        palette.setColor(QPalette.Base, QColor("black"))
        palette.setColor(QPalette.Text, QColor(230, 230, 230))
        self.output.setPalette(palette)

        self.output.setLineWrapMode(QTextEdit.NoWrap)

        # ✅ ADD THIS
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

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

        # Add progress bar ABOVE output
        main_layout.addWidget(self.progressBar)

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
        # Optional: change cursor and disable controls
        self.setCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)
        for btn in (self.generate, self.test_api, self.deploy_full_btn):
            btn.setEnabled(not busy)

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
            
            # Optional: provide a small visual hint in the output
            self.log("\n[System] Output copied to clipboard.")
    
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