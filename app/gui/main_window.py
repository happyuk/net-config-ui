# app/gui/main_window.py
from PySide6.QtCore import QTimer, Qt, QSettings
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor, QGuiApplication
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QProgressBar, QRadioButton, QSplitter, QWidget,
    QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QFormLayout,
    QComboBox
)

import serial
import serial.tools.list_ports

from app.domain.config_blocks import set_selected_template_set
from app.infrastructure.loader import NODE_OBR_ASSIGNMENT
from app.domain.config_builder import ConfigBuilder
from app.domain.config_manager import TEMPLATE_REGISTRY, ConfigManager
from app.services.router_api import RouterAPI
from app.viewmodel.main_viewmodel import MainViewModel


# ====================== FIELD DEFINITIONS ======================
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
    ("Password", "device_pass", QLineEdit),
]

RIGHT_FIELDS = [
    ("Grey DHCP", "grey_dhcp"),
    ("Grey Router", "grey_router"),
    ("Grey DHCP Reserved", "grey_router_dhcp_reserved"),
]


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # Core objects
        self.settings = QSettings("QinetiQ", "DVRConfigBuilder")
        self.config_builder = ConfigBuilder()
        self.vm = None  # Will be initialized after UI

        # Timer for SSH test timeout feedback
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_timer_label)
        self.seconds_elapsed = 0

        # UI Setup
        self.widgets = {}
        self.init_ui()

        # ViewModel (after UI is ready)
        self.vm = MainViewModel(
            config_builder=self.config_builder,
            config_manager=ConfigManager,
            template_setter=set_selected_template_set
        )

        # Connect signals
        self._connect_viewmodel_signals()

        # Final setup
        self.restore_settings()
        self.update_access_ui()

        self.setWindowTitle("Router Config Builder")
        self.resize(1000, 650)

    # =============================================================
    # UI INITIALIZATION
    # =============================================================
    def init_ui(self):
        """Main UI initialization entry point."""
        self._create_input_widgets()
        self._create_forms()
        self._create_output_area()
        self._setup_layout()

    def _create_input_widgets(self):
        """Create all input widgets and store them appropriately."""
        # Connection mode toggles
        self.radio_serial = QRadioButton("Serial Cable (Day 0)")
        self.radio_ssh = QRadioButton("SSH")
        self.radio_ssh.setChecked(True)
        self.radio_ssh.toggled.connect(self.update_access_ui)
        self.radio_serial.toggled.connect(self.update_access_ui)

        # Left side fields
        for _, name, widget_type in LEFT_FIELDS:
            w = widget_type()
            if name == "usersecret":
                w.setEchoMode(QLineEdit.Password)
            setattr(self, name, w)
            self.widgets[name] = w

        # Device credentials fields
        for _, name, widget_type in DEVICE_FIELDS:
            w = widget_type()
            if name == "device_pass":
                w.setEchoMode(QLineEdit.Password)
            setattr(self, name, w)
            self.widgets[name] = w

        # Serial widgets
        self.serial_port_combo = QComboBox()
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(["9600", "115200", "38400", "57600"])

        self.refresh_serial_btn = QPushButton("Refresh Ports")
        self.refresh_serial_btn.clicked.connect(self.on_refresh_serial)

        self.btn_serial_connect = QPushButton("Connect via Console")
        self.btn_serial_connect.clicked.connect(self.on_serial_connect)

        # Right side read-only fields
        for _, name in RIGHT_FIELDS:
            w = QLineEdit()
            w.setReadOnly(True)
            setattr(self, name, w)
            self.widgets[name] = w

        # Populate combos
        self.template_mode.addItems(list(TEMPLATE_REGISTRY.keys()))
        self.template_mode.currentTextChanged.connect(self.on_template_changed)

        self._populate_node_combo()

        # Default values
        self._set_default_values()

        # Action buttons
        self._create_action_buttons()

    def _populate_node_combo(self):
        try:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys(), key=int)
        except ValueError:
            keys = sorted(NODE_OBR_ASSIGNMENT.keys())
        self.nodenumber.addItems(keys)

    def _set_default_values(self):
        self.domain.setText("o")
        self.secret.setText("DC2e*1234!")
        self.username.setText("admin")
        self.usersecret.setText("DC2e*1234!")

        self.device_host.setPlaceholderText("192.168.16.111")
        self.device_user.setPlaceholderText("admin")
        self.device_pass.setPlaceholderText("device password")

    def _create_action_buttons(self):
        self.generate = QPushButton("Generate node configuration")
        self.generate.clicked.connect(self.on_generate_config)

        self.test_api = QPushButton("Test RESTCONF")
        self.test_api.clicked.connect(self.on_test_restconf_api)
        self.test_api.hide()

        self.deploy_full_btn = QPushButton("Deploy")
        self.deploy_full_btn.setObjectName("deployButton")
        self.deploy_full_btn.clicked.connect(self.on_deploy_full)

        self.copy_btn = QPushButton("Copy Output Text")
        self.copy_btn.clicked.connect(self.on_copy_output)

        self.clear_btn = QPushButton("Clear Output Text")
        self.clear_btn.clicked.connect(self.on_clear_output)

        self.btn_test_connection = QPushButton("Test Connection")
        self.btn_test_connection.clicked.connect(self.on_handle_test)

        self.btn_factory_reset = QPushButton("⚠️ Factory Reset")
        self.btn_factory_reset.setStyleSheet("""
            QPushButton { 
                background-color: #c0392b; 
                color: white; 
                font-weight: bold; 
                border-radius: 4px; 
                padding: 5px;
            }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:pressed { background-color: #962d22; }
        """)
        self.btn_factory_reset.clicked.connect(self.on_factory_reset_clicked)

    def _create_forms(self):
        """Create the three form layouts."""
        # Left form (Node Configuration)
        self.left_form = QFormLayout()
        self.left_form.setLabelAlignment(Qt.AlignRight)
        for label, name, _ in LEFT_FIELDS:
            self.left_form.addRow(f"{label}:", self.widgets[name])

        # Device form (SSH)
        self.device_form = QFormLayout()
        self.device_form.setLabelAlignment(Qt.AlignRight)
        for label, name, _ in DEVICE_FIELDS:
            self.device_form.addRow(f"{label}:", self.widgets[name])

        # Right form (read-only results)
        self.right_form = QFormLayout()
        self.right_form.setLabelAlignment(Qt.AlignRight)
        for label, name in RIGHT_FIELDS:
            self.right_form.addRow(f"{label}:", self.widgets[name])

    def _create_output_area(self):
        """Create the terminal-like output area."""
        self.output = QTextEdit()
        self.output.setReadOnly(False)
        self.output.setLineWrapMode(QTextEdit.NoWrap)

        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)

        palette = self.output.palette()
        palette.setColor(QPalette.Base, QColor("black"))
        palette.setColor(QPalette.Text, QColor(230, 230, 230))
        self.output.setPalette(palette)

        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.hide()

    def _setup_layout(self):
        """Assemble all widgets into the final layout."""
        # Left Panel
        left_panel = QWidget()
        left_layout = QVBoxLayout()

        left_layout.addWidget(self._create_connection_method_group())
        left_layout.addWidget(self._create_node_config_group())
        left_layout.addWidget(self._create_actions_group())

        left_panel.setLayout(left_layout)

        # Right Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_layout.addWidget(self.output)
        output_box.setLayout(output_layout)

        right_layout.addWidget(output_box)
        right_layout.addWidget(self.progressBar)
        right_panel.setLayout(right_layout)

        # Main Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 680])

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        main_layout.addWidget(splitter)

        self.setLayout(main_layout)

    def _create_connection_method_group(self):
        box = QGroupBox("Connection Method")
        layout = QVBoxLayout()

        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.radio_serial)
        mode_layout.addWidget(self.radio_ssh)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Serial settings
        self.serial_inner_box = QGroupBox("Serial Connection Settings")
        serial_layout = QVBoxLayout()
        port_line = QHBoxLayout()
        port_line.addWidget(self.serial_port_combo, stretch=4)
        port_line.addWidget(self.refresh_serial_btn, stretch=1)

        serial_form = QFormLayout()
        serial_form.setLabelAlignment(Qt.AlignRight)
        serial_form.addRow("Port:", port_line)
        serial_form.addRow("Baud:", self.serial_baud_combo)
        serial_layout.addLayout(serial_form)
        self.serial_inner_box.setLayout(serial_layout)

        # SSH settings
        self.ssh_inner_box = QGroupBox("SSH Connection Settings")
        ssh_layout = QVBoxLayout()
        ssh_layout.addLayout(self.device_form)
        self.ssh_inner_box.setLayout(ssh_layout)

        layout.addWidget(self.serial_inner_box)
        layout.addWidget(self.ssh_inner_box)
        layout.addWidget(self.btn_test_connection)
        layout.addWidget(self.btn_factory_reset)

        box.setLayout(layout)
        return box

    def _create_node_config_group(self):
        box = QGroupBox("Node Configuration")
        layout = QVBoxLayout()
        layout.addLayout(self.left_form)
        layout.addWidget(self.generate)
        box.setLayout(layout)
        return box

    def _create_actions_group(self):
        box = QGroupBox("Actions")
        box.setObjectName("actionsBox")
        layout = QVBoxLayout()
        layout.addWidget(self.test_api)
        layout.addWidget(self.deploy_full_btn)
        layout.addWidget(self.copy_btn)
        layout.addWidget(self.clear_btn)
        layout.addStretch()
        box.setLayout(layout)
        return box

    # =============================================================
    # SIGNAL CONNECTIONS
    # =============================================================
    def _connect_viewmodel_signals(self):
        self.vm.deploy_log.connect(self.log)
        self.vm.deploy_error.connect(self.log)
        self.vm.deploy_progress.connect(self.progressBar.setValue)
        self.vm.deploy_finished.connect(self.on_deploy_finished)
        self.vm.test_finished.connect(self.handle_test_ssh_result)

    # =============================================================
    # SETTINGS
    # =============================================================
    def restore_settings(self):
        s = self.settings

        # Serial
        baud = s.value("serial/baud", "115200")
        idx = self.serial_baud_combo.findText(baud)
        if idx >= 0:
            self.serial_baud_combo.setCurrentIndex(idx)

        port = s.value("serial/port", "")
        idx = self.serial_port_combo.findText(port)
        if idx >= 0:
            self.serial_port_combo.setCurrentIndex(idx)

        # SSH
        self.device_host.setText(s.value("device/host", ""))
        self.device_user.setText(s.value("device/user", ""))
        self.device_pass.setText(s.value("device/pass", ""))

        # UI
        self.template_mode.setCurrentText(s.value("ui/template_mode", "DVR Pre-Cert"))
        self.nodenumber.setCurrentText(s.value("ui/node_number", ""))
        self.domain.setText(s.value("ui/domain", "o"))
        self.username.setText(s.value("ui/username", "admin"))

        # Connection mode
        if s.value("device/access_mode") == "serial":
            self.radio_serial.setChecked(True)
        else:
            self.radio_ssh.setChecked(True)

    def save_settings(self):
        s = self.settings

        s.setValue("device/host", self.device_host.text().strip())
        s.setValue("device/user", self.device_user.text().strip())
        s.setValue("device/pass", self.device_pass.text().strip())

        s.setValue("serial/port", self.serial_port_combo.currentText())
        s.setValue("serial/baud", self.serial_baud_combo.currentText())

        s.setValue("ui/template_mode", self.template_mode.currentText())
        s.setValue("ui/node_number", self.nodenumber.currentText())
        s.setValue("ui/domain", self.domain.text().strip())
        s.setValue("ui/username", self.username.text().strip())

        mode = "serial" if self.radio_serial.isChecked() else "ssh"
        s.setValue("device/access_mode", mode)

        s.sync()

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    # =============================================================
    # LOGIC METHODS (mostly unchanged, minor cleanups)
    # =============================================================
    def on_generate_config(self):
        self.save_settings()
        result = self.vm.generate_config(
            node=self.nodenumber.currentText().strip(),
            mode=self.template_mode.currentText(),
            form_data=self.collect_form_data()
        )
        if result.get("ips"):
            self.grey_dhcp.setText(result["ips"]["dhcp"])
            self.grey_router.setText(result["ips"]["router"])
            self.grey_router_dhcp_reserved.setText(result["ips"]["reserved"])

        if result.get("config"):
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
        config_text = self.output.toPlainText().strip()

        if not config_text:
            self.log("[Error] No configuration generated to deploy.")
            return

        if self.radio_ssh.isChecked():
            host, user, pwd = self.get_device_credentials()
            if not host:
                self.log("[Error] Host IP required for SSH deployment.")
                return

            blocks, err = self.vm.prepare_deployment(config_text, host, user, pwd)
            if err:
                self.log(f"[Deploy] {err}")
                return

            self.progressBar.setValue(0)
            self._set_busy(True)
            self.vm.start_deployment(blocks, host, user, pwd)

        else:  # Serial
            port = self.serial_port_combo.currentText()
            baud = self.serial_baud_combo.currentText()

            if not port or port == "No Devices Found":
                self.log("[Error] Valid Serial Port required for deployment.")
                return

            self.log(f"=== STARTING SERIAL DEPLOYMENT ON {port} ===")
            self._set_busy(True)
            self.progressBar.setRange(0, 0)   # pulsing
            self.vm.start_serial_deployment(port, baud, config_text)

    def _set_busy(self, busy: bool):
        cursor = Qt.WaitCursor if busy else Qt.ArrowCursor
        self.setCursor(cursor)

        for btn in (self.generate, self.test_api, self.deploy_full_btn):
            btn.setEnabled(not busy)

        if busy:
            self.progressBar.show()
        else:
            self.progressBar.hide()

    def on_template_changed(self, value: str):
        if not hasattr(self, "output"):
            return
        path = self.vm.apply_template(value)
        if path:
            self.log(f"[Info] Switched to {value.upper()} template set.")
        else:
            self.log(f"[Warning] No template path found for: {value}")

    def on_copy_output(self):
        text = self.output.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.log("\n[System] Output copied to clipboard.")

    def on_clear_output(self):
        self.output.clear()

    def on_factory_reset_clicked(self):
        # 1. Selection Check
        if self.radio_ssh.isChecked():
            self.log("[Error] Factory Reset must be performed over Serial Cable.")
            return

        # 2. Confirmation Dialog
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.warning(
            self, "Confirm Factory Reset",
            "This will ERASE the router NVRAM and REBOOT the device.\n\n"
            "The process takes approx 5-8 minutes.\nDo you want to proceed?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.on_clear_output()
            self.log("=== INITIATING AUTOMATED FACTORY RESET ===")
            
            # 3. Disable UI while reset is running
            self._set_busy(True)
            self.progressBar.setRange(0, 0) # Pulsing progress
            
            # 4. Trigger ViewModel logic
            # Assuming you have added 'start_factory_reset' to your MainViewModel
            port = self.serial_port_combo.currentText()
            baud = self.serial_baud_combo.currentText()
            secret = self.secret.text() # Use the secret field from the UI
            
            self.vm.start_factory_reset(port, baud, secret)


    # ====================== Serial ======================
    def on_refresh_serial(self):
        self.serial_port_combo.clear()
        self.on_clear_output()

        ports = [
            p for p in serial.tools.list_ports.comports()
            if "ttyUSB" in p.device or "ttyACM" in p.device
        ]

        if not ports:
            self.serial_port_combo.addItem("No Devices Found")
            self.log("[System] Scan complete: No USB serial devices found.")
        else:
            device_paths = [p.device for p in ports]
            self.serial_port_combo.addItems(device_paths)
            self.log(f"[System] Found {len(ports)} serial device(s):")
            for p in ports:
                self.log(f" → {p.device} ({p.description})")

    def on_serial_connect(self):
        # ... your existing implementation (kept mostly as-is) ...
        port = self.serial_port_combo.currentText()
        baud = self.serial_baud_combo.currentText()

        if not port or port == "No Devices Found":
            self.log("[Critical] Test Aborted: No valid serial port selected.")
            return

        self.log(f"[1/3] Opening port {port} at {baud} baud...")
        try:
            ser = serial.Serial(port, int(baud), timeout=1)
            if ser.is_open:
                self.log(f"[2/3] Port {port} is OPEN.")
                self.log("[3/3] Waking up terminal: send carriage return...")
                ser.write(b'\r\n')
                response = ser.read(100).decode('utf-8', errors='ignore')
                if response.strip():
                    self.log(f"[Success] Device responded: {response.strip()}")
                else:
                    self.log("[Warning] Port open but device is silent.")
                ser.close()
            self.log(">>> TEST COMPLETE <<<")
        except serial.SerialException as e:
            self.log(f"[Error] {e}")
            if "Permission denied" in str(e):
                self.log("[Tip] Try: sudo usermod -aG dialout $USER")
        except Exception as e:
            self.log(f"[Error] Unexpected: {e}")

    # ====================== Logging & Helpers ======================
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
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(100)
        self.log("\n[System] Deployment sequence complete.")

    # ====================== SSH Test ======================
    def on_test_ssh(self):
        self.on_clear_output()
        host, user, pwd = self.get_device_credentials()
        if not host:
            self.log("[Error] Host IP is required for SSH test.")
            return

        self.seconds_elapsed = 0
        self.output.setReadOnly(True)
        self.log(f"Testing SSH connection to {host}...")
        self.output.insertPlainText(f"[SSH] Initializing connection to {host}...\n")
        self.output.insertPlainText("Still attempting connection... (0s elapsed)\n")

        self.timer.start(1000)
        self.setCursor(Qt.WaitCursor)
        self.btn_test_connection.setEnabled(False)

        self.vm.start_ssh_test(host, user, pwd)

    def on_handle_test(self):
        self.on_clear_output()
        if self.radio_ssh.isChecked():
            self.on_test_ssh()
        else:
            self.on_serial_connect()

    def handle_test_ssh_result(self, ok: bool, result: str, extra=None):
        self.timer.stop()
        self.output.setReadOnly(False)
        self.setCursor(Qt.ArrowCursor)
        self.btn_test_connection.setEnabled(True)

        # Ensure clean newline
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n")
        self.output.setTextCursor(cursor)

        if ok:
            self.log("SUCCESS: Connection established.")
        else:
            self.log(f"FAILURE: {result}")

    def update_timer_label(self):
        self.seconds_elapsed += 1
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
        cursor.insertText(f"Still attempting connection... ({self.seconds_elapsed}s elapsed)")
        self.output.setTextCursor(cursor)

    def update_access_ui(self):
        """Update UI visibility and button text based on selected connection method."""
        is_ssh = self.radio_ssh.isChecked()

        # Only allow factory reset if we are on Serial mode
        self.btn_factory_reset.setEnabled(not is_ssh)

        self.ssh_inner_box.setEnabled(is_ssh)
        self.serial_inner_box.setEnabled(not is_ssh)

        test_text = "Test SSH Connection" if is_ssh else "Test Serial Connection"
        self.btn_test_connection.setText(test_text)

        if is_ssh:
            self.deploy_full_btn.setText("🌐 Deploy via SSH")
            self.deploy_full_btn.setStyleSheet("")
        else:
            self.deploy_full_btn.setText("🚀 Deploy via Serial Cable (Day 0)")
            self.deploy_full_btn.setStyleSheet(
                "background-color: #2c3e50; color: white; font-weight: bold;"
            )