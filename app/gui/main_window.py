# app/gui/main_window.py
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QProgressBar, QRadioButton, QSplitter, QWidget, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QFormLayout, QComboBox
)
import serial
import serial.tools.list_ports  # Add this line

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

        # 1. Basics
        self.settings = QSettings("QinetiQ", "DVRConfigBuilder")
        self.config_builder = ConfigBuilder()

        # 2. UI Setup (MUST happen before restore_settings)
        self.init_inputs()
        self.init_forms()
        self.init_output()
        self.init_layout() 

        # 3. Viewmodel (Fixing the TypeError)
        # Note: I'm assuming ConfigManager needs to be instantiated here
        self.vm = MainViewModel(
            config_builder=self.config_builder,
            config_manager=ConfigManager, 
            template_setter=set_selected_template_set
        )

        # 4. Final Wiring & Loading
        self.vm.deploy_log.connect(self.log)
        self.vm.deploy_error.connect(self.log)
        self.vm.deploy_progress.connect(self.progressBar.setValue)
        self.vm.deploy_finished.connect(self.on_deploy_finished)

        self.restore_settings() # Now this won't crash on 'ssh_inner_box'

        self.setWindowTitle("Router Config Builder")
        self.resize(1000, 650)


    # ============================================================
    # UI SETUP
    # ============================================================

    def init_inputs(self):
        """Create all input widgets."""
        self.widgets = {}
        self.ssh_status_label = QLabel("")

        # ---- Connection Mode Toggles ----
        self.radio_serial = QRadioButton("Serial Cable")
        self.radio_ssh = QRadioButton("SSH")
        self.radio_ssh.setChecked(True) 

        self.radio_ssh.toggled.connect(self.update_access_ui)
        self.radio_serial.toggled.connect(self.update_access_ui)

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

        # ---- Serial Console Widgets ----
        self.serial_port_combo = QComboBox()
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(["9600", "115200", "38400", "57600"])
        self.refresh_serial_btn = QPushButton("Refresh Ports")
        self.refresh_serial_btn.clicked.connect(self.on_refresh_serial)
        self.btn_serial_connect = QPushButton("Connect via Console")
        self.btn_serial_connect.clicked.connect(self.on_serial_connect)

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

        self.btn_test_connection = QPushButton("Test Connection")
        self.btn_test_connection.clicked.connect(self.on_handle_test)

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

        # ---- PARENT: Device Access ----
        self.device_access_box = QGroupBox("Device Access")
        access_layout = QVBoxLayout()

        # 1. Mode Selection (Horizontal)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.radio_serial)
        mode_layout.addWidget(self.radio_ssh)
        mode_layout.addStretch() # Pushes buttons to the left
        access_layout.addLayout(mode_layout)

        # 2. Inner Box: Serial Settings
        self.serial_inner_box = QGroupBox("Serial Connection Settings")
        serial_inner_layout = QVBoxLayout()

        # Helper layout for the Port + Refresh button line
        port_line = QHBoxLayout()
        port_line.addWidget(self.serial_port_combo, stretch=4)
        port_line.addWidget(self.refresh_serial_btn, stretch=1)

        serial_form = QFormLayout()
        serial_form.addRow("Port:", port_line)
        serial_form.addRow("Baud:", self.serial_baud_combo)
        
        serial_inner_layout.addLayout(serial_form)
        self.serial_inner_box.setLayout(serial_inner_layout)
        access_layout.addWidget(self.serial_inner_box)

        # 3. Inner Box: SSH Settings
        self.ssh_inner_box = QGroupBox("SSH Connection Settings")
        ssh_inner_layout = QVBoxLayout()
        ssh_inner_layout.addLayout(self.device_form) # Uses your DEVICE_FIELDS form
        self.ssh_inner_box.setLayout(ssh_inner_layout)
        access_layout.addWidget(self.ssh_inner_box)

        # 4. Unified Test Button
        access_layout.addWidget(self.btn_test_connection)
        self.device_access_box.setLayout(access_layout)
        left_layout.addWidget(self.device_access_box)

        # ---- Node Configuration ----
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
        self.update_access_ui()


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

        # Restore the connection mode
        mode = s.value("device/access_mode", "ssh") # Default to ssh if not found
        if mode == "serial":
            self.radio_serial.setChecked(True)
        else:
            self.radio_ssh.setChecked(True)

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

        # Save the connection mode
        mode = "ssh" if self.radio_ssh.isChecked() else "serial"
        s.setValue("device/access_mode", mode)
        
        # ... your existing ui/domain etc saves ...
        s.sync() # Force write to disk

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
        self.output.clear()

    def on_refresh_serial(self):
            """Manually scan for /dev/ttyUSB* or /dev/ttyACM* ports and log findings."""
            self.serial_port_combo.clear()
            
            # Use a list comprehension to get the full port objects so we can see descriptions
            ports = [p for p in serial.tools.list_ports.comports() 
                    if "ttyUSB" in p.device or "ttyACM" in p.device]
            
            if not ports:
                self.serial_port_combo.addItem("No Devices Found")
                self.btn_serial_connect.setEnabled(False)
                self.log("[System] Scan complete: No USB serial devices found. Check your cable.")
            else:
                # Extract just the device paths for the dropdown
                device_paths = [p.device for p in ports]
                self.serial_port_combo.addItems(device_paths)
                self.btn_serial_connect.setEnabled(True)
                
                # Log each found device with its hardware description
                self.log(f"[System] Scan complete: Found {len(ports)} device(s):")
                for p in ports:
                    # Example log: [System] -> /dev/ttyUSB0 (FT232R USB UART)
                    self.log(f"  -> {p.device} ({p.description})")

    def on_serial_connect(self):
        port = self.serial_port_combo.currentText()
        baud = self.serial_baud_combo.currentText()
        
        if port == "No Devices Found" or not port:
            self.log("[Critical] Test Aborted: No valid serial port selected.")
            return

        self.log(f"[1/3] Opening port {port} at {baud} baud...")
        
        try:
            # We use a short timeout so the UI doesn't hang if the device is dead
            ser = serial.Serial(port, int(baud), timeout=1)
            
            if ser.is_open:
                self.log(f"[2/3] Port {port} is OPEN and available.")
                
                # Test "Liveness": Send a carriage return to see if we get anything back
                self.log("[3/3] Sending 'Enter' to device to check for response...")
                ser.write(b'\r\n')
                
                # Read a small bit of buffer to see if there's text (like a login prompt)
                response = ser.read(100).decode('utf-8', errors='ignore')
                
                if response:
                    self.log(f"[Success] Device responded with: {response.strip()}")
                else:
                    self.log("[Warning] Port is open, but the device is SILENT.")
                    self.log("[Tip] Ensure the router is powered on and the cable is seated.")
                
                ser.close()
                self.log(">>> TEST COMPLETE <<<")

        except serial.SerialException as e:
            self.log(f"[Error] Hardware failure: {str(e)}")
            if "Permission denied" in str(e):
                self.log("[Tip] Run: 'sudo usermod -aG dialout $USER' and restart your session.")
        except Exception as e:
            self.log(f"[Error] Unexpected failure: {str(e)}")

    
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

    def update_access_ui(self):
        """Disables the group box not currently in use based on Radio Selection."""
        is_ssh = self.radio_ssh.isChecked()
        
        # This one line disables/enables every widget inside the SSH box
        self.ssh_inner_box.setEnabled(is_ssh)
        
        # This one line disables/enables every widget inside the Serial box
        self.serial_inner_box.setEnabled(not is_ssh)
        
        # Optional: Update the button text so the user knows exactly what it's testing
        if is_ssh:
            self.btn_test_connection.setText("Test SSH Connection")
        else:
            self.btn_test_connection.setText("Test Serial Connection")

    def on_handle_test(self):
        self.on_clear_output()
        if self.radio_ssh.isChecked():
            self.log("=== STARTING SSH ACCESS TEST ===")
            self.on_test_ssh()
        else:
            self.log("=== STARTING SERIAL CONSOLE TEST ===")
            self.on_serial_connect()