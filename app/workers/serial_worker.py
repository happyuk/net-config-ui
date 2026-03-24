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

    def run(self):
            ser = None
            try:
                ser = serial.Serial(self.port, self.baud, timeout=2)
                if not ser.is_open: ser.open()

                # --- 1. WAKE UP & HANDSHAKE ---
                self.log_signal.emit("[Serial] Waking up console...")
                ser.write(b"\r\n\r\n")
                response = self.wait_for_prompt(ser)

                # Handle the "Initial Config Dialog"
                if "initial configuration dialog" in response.lower():
                    self.log_signal.emit("[Serial] Bypassing setup wizard...")
                    ser.write(b"no\r\n")                    
                    self.wait_for_prompt(ser, timeout=15) 
                    ser.write(b"\r\n")
                    self.wait_for_prompt(ser)

                # --- 2. ENTER CONFIG MODE ---
                self.log_signal.emit("[Serial] Entering Configuration Mode...")
                ser.write(b"enable\r\n")
                self.wait_for_prompt(ser)
                
                ser.write(b"configure terminal\r\n")
                self.wait_for_prompt(ser)

                # --- 3. THE DEPLOYMENT LOOP ---
                lines = self.config_text.splitlines()
                total_lines = len(lines)

                for i, line in enumerate(lines):
                    clean_line = line.strip()
                    if not clean_line: continue

                    # Send command
                    ser.write((clean_line + "\r\n").encode('ascii'))
                    
                    # SPECIAL CASE: Reload must happen BEFORE waiting for a prompt
                    if "reload" in clean_line.lower():
                        time.sleep(1)
                        ser.write(b"\r\n") 
                        self.log_signal.emit("[Serial] Reload confirmed. Closing port.")
                        break

                    # For all other commands, wait for the '#' prompt to return
                    # This naturally handles the 3-second 'wr mem' delay too!
                    output = self.wait_for_prompt(ser)
                    
                    if "%" in output:
                        self.log_signal.emit(f"[Router Error] {output.strip()}")
                    else:
                        self.log_signal.emit(f"[Serial] OK: {clean_line}")

                    self.progress_signal.emit(int(((i + 1) / total_lines) * 100))

            except Exception as e:
                self.log_signal.emit(f"[Serial Error] {str(e)}")
            finally:
                if ser and ser.is_open: ser.close()
                self.finished_signal.emit()


    def wait_for_prompt(self, ser, timeout=5):
        """
        Reads the serial buffer until it sees the '#' symbol
        which indicates the router is finished processing.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if the router has sent anything back
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                if "#" in data:  # Most Cisco prompts end with #
                    return True
            time.sleep(0.05) # Small poll interval to prevent 100% CPU usage
        return False