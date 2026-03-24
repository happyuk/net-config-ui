from PySide6.QtCore import QObject, Signal

class ConnectionTestWorker(QObject):
    # Signals: success (bool), result_message (str), extra_info (object)
    finished = Signal(bool, str, object)

    def __init__(self, mode, vm, host, user, pwd):
        super().__init__()
        self.mode = mode
        self.vm = vm
        self.host = host
        self.user = user 
        self.pwd = pwd 

    def run(self):
        try:
            if self.mode == "ssh":
                # Add a timeout to the actual call (e.g., 10 seconds)
                # Make sure your vm.test_ssh handles a timeout argument
                ok, result = self.vm.test_ssh(self.host, self.user, self.pwd)
                
                if ok:
                    self.finished.emit(True, "Login Successful.", result)
                else:
                    self.finished.emit(False, f"Connection Failed: {result}", None)
            elif self.mode == "restconf":
                ok, msg, extra = self.vm.test_restconf(self.host, self.user, self.pwd)
                self.finished.emit(ok, msg, extra)
        except Exception as e:
            self.finished.emit(False, str(e), None)