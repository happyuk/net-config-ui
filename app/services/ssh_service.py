from netmiko import ConnectHandler

class SSHService:
    def __init__(self):
        self.connection = None
        self.device_type = None

    def connect(self, host, username, password):
        device = {
            "device_type": "autodetect",
            "host": host,
            "username": username,
            "password": password,
            "timeout": 5,
        }

        self.connection = ConnectHandler(**device)
        self.device_type = self.connection.device_type

    def disconnect(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def is_connected(self):
        return self.connection is not None

    def send_command(self, command):
        if not self.connection:
            raise Exception("Not connected to device")

        return self.connection.send_command(command)

    def send_config(self, config_lines):
        if not self.connection:
            raise Exception("Not connected to device")

        return self.connection.send_config_set(config_lines)