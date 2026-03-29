import time
import serial
from PySide6.QtCore import QThread, Signal

class SerialDeployWorker(QThread):
    # Signals to talk back to the ViewModel/UI
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal()

    def __init__(self, port, baud, config_text):
        super().__init__()
        self.port = port
        self.baud = int(baud)
        self.config_text = config_text

    def run(
        self,
        username="admin",
        password="DC2e*1234!",
        commands=None,
        confirm_reload=True,
        enable_secret="DC2e*1234!"
    ):
        """
        Serial worker: handles login, initial config dialog, enable secret, and arbitrary commands.
        Special handling for 'reload': confirm if needed, then exit since router is rebooting.
        """
        ser = None
        try:
            if not self.port:
                self.log_signal.emit("[Error] Valid Serial Port required for deployment.")
                self.finished_signal.emit()
                return

            # --- OPEN SERIAL PORT ---
            ser = serial.Serial(
                self.port,
                baudrate=self.baud,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            if not ser.is_open:
                ser.open()

            # --- WAKE ROUTER ---
            self.log_signal.emit("[Serial] Waking up console...")
            ser.write(b"\r\n")
            time.sleep(0.5)

            # --- INITIAL CONFIG DIALOG ---
            buffer = self.wait_for_prompt(ser, timeout=5)
            self.log_signal.emit(buffer.strip())
            if "initial configuration dialog" in buffer.lower():
                self.log_signal.emit("[Serial] Bypassing setup wizard...")
                ser.write(b"no\r\n")
                time.sleep(0.5)
                buffer = self.wait_for_prompt(ser, timeout=5)
                self.log_signal.emit(buffer.strip())

            # --- LOGIN & PROMPT CHECK ---
            login_timeout = 15
            start_time = time.time()
            logged_in = False
            buffer = ""

            # Give the router a moment to show its current state
            ser.write(b"\r\n") 
            time.sleep(0.5)

            while True:
                if ser.in_waiting:
                    chunk = ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
                    buffer += chunk
                    
                    # 1. Check if we are ALREADY at a usable prompt
                    if "#" in buffer:
                        self.log_signal.emit("[Serial] Detected Privileged mode (#). Skipping login/enable.")
                        logged_in = True
                        break
                    if "(config)" in buffer:
                        self.log_signal.emit("[Serial] Detected Config mode. Returning to Privileged mode...")
                        ser.write(b"end\r\n")
                        time.sleep(0.5)
                        buffer = "" # Reset to catch the new # prompt
                        continue

                    # 2. Standard Login Handlers
                    if "username:" in buffer.lower():
                        self.log_signal.emit("[Serial] Sending username...")
                        ser.write((username + "\r\n").encode("ascii"))
                        buffer = ""
                    elif "password:" in buffer.lower():
                        self.log_signal.emit("[Serial] Sending password...")
                        ser.write((password + "\r\n").encode("ascii"))
                        buffer = ""
                    elif ">" in buffer:
                        self.log_signal.emit("[Serial] User mode detected (>). Proceeding to enable.")
                        logged_in = True
                        break

                if time.time() - start_time > login_timeout:
                    self.log_signal.emit("[Serial] Login check timed out.")
                    logged_in = True # Attempt to proceed anyway
                    break
                time.sleep(0.1)

            # --- DYNAMIC ENABLE MODE ---
            # We only run this if we aren't already at the '#' prompt
            if "#" not in buffer and "(config)" not in buffer:
                self.log_signal.emit("[Serial] Entering enable mode...")
                ser.write(b"enable\r\n")
                time.sleep(0.5)
                buffer = self.wait_for_prompt(ser, timeout=5)
                
                if "password:" in buffer.lower():
                    self.log_signal.emit("[Serial] Sending enable secret...")
                    ser.write((enable_secret + "\r\n").encode("ascii"))
                    time.sleep(0.5)
                    buffer = self.wait_for_prompt(ser)

            # --- PREPARE FOR AND HANDLE LONG OUTPUT ---
            # Always run this to be safe, but only if we are in # mode
            self.log_signal.emit("[Serial] Disabling pagination (terminal length 0)...")
            ser.write(b"terminal length 0\r\n")
            time.sleep(0.5)
            ser.read_all()

            # --- CHOOSE COMMANDS ---
            if commands is None:
                lines = self.config_text.splitlines()
            else:
                lines = commands
            total_lines = len(lines)

            # --- SEND COMMANDS LOOP ---
            for i, line in enumerate(lines):
                clean_line = line.strip()
                if not clean_line:
                    continue

                self.log_signal.emit(f"[Serial] Sending: {clean_line}")
                ser.write((clean_line + "\r\n").encode("ascii"))
                time.sleep(0.2)

                # --- SPECIAL CASE: reload ---
                if clean_line.lower() == "reload":
                    output = ser.read_all().decode("utf-8", errors="ignore")
                    self.log_signal.emit(output.strip())

                    # Handle confirmation prompt
                    if "[confirm]" in output.lower() or "proceed with reload" in output.lower():
                        self.log_signal.emit(f"[Serial] Reload confirmation prompt detected: {output.strip()}")        
                        reply = b"yes\r\n" if confirm_reload else b"no\r\n"
                        self.log_signal.emit(f"[Serial] Sending '{reply.decode().strip()}' to confirmation prompt")
                        ser.write(reply)
                        time.sleep(0.5)

                        followup = ser.read_all().decode("utf-8", errors="ignore")
                        if followup.strip():
                            self.log_signal.emit(followup.strip())

                    self.log_signal.emit("[Serial] Router has accepted reload command and is rebooting. Disconnecting session...")
                    self.log_signal.emit("[Serial] Reload may take ~90 seconds. Please wait before reconnecting.")
                    break

                else:
                    # --- READ OUTPUT for normal commands ---
                    output = self.wait_for_prompt(ser, timeout=15)
                    self.log_signal.emit(f"[DEBUG LEN] {len(output)}")
                    if "%" in output:
                        self.log_signal.emit(f"[Router Error] {output.strip()}")
                    else:
                        if output.strip():
                            self.log_signal.emit(output.strip())

                # --- PROGRESS ---
                self.progress_signal.emit(int(((i + 1) / total_lines) * 100))

        except Exception as e:
            self.log_signal.emit(f"[Serial Error] {str(e)}")

        finally:
            if ser and ser.is_open:
                ser.close()
            self.finished_signal.emit()


    def wait_for_prompt(self, ser, timeout=10, idle_time=1.0):
        start_time = time.time()
        last_data_time = time.time()
        accumulated_output = ""

        time.sleep(0.5)

        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                new_data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                accumulated_output += new_data
                last_data_time = time.time()

                # Debug (you'll want this)
                print(new_data, end="")

            # Only exit if:
            # 1. We have a prompt somewhere
            # 2. AND no data has arrived recently
            if ("#" in accumulated_output or ">" in accumulated_output):
                if time.time() - last_data_time > idle_time:
                    return accumulated_output

            time.sleep(0.1)

        return accumulated_output