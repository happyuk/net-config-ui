# app/services/deployer.py
from typing import Any, Dict, List, Tuple
import time
import re

from app.services.output_cleaner import clean_output
from netmiko import ConnectHandler

# Executes configuration blocks on network devices via RESTCONF, SSH CLI, or NETCONF.
class Deployer:
    """
    Executes blocks of commands on network devices via RESTCONF, SSH CLI, or NETCONF.
    """
    def __init__(self, api, ssh_client=None, netconf_client=None):
        self.api = api
        self.ssh = ssh_client
        self.netconf = netconf_client

    # -----------------------------
    # RESTCONF
    # -----------------------------
    def deploy_via_restconf(self, resource: str, payload: Dict[str, Any], method: str = "PATCH"):
        method = method.upper()
        if method == "PATCH":
            return self.api.patch(resource, payload_json=payload)
        if method == "PUT":
            return self.api.put(resource, payload_json=payload)
        raise ValueError(f"Unsupported RESTCONF method: {method}")

    # -----------------------------
    # CLI helpers
    # -----------------------------
    def _read_until(self, chan, prompt_regex: str, timeout: float = 10.0) -> str:
        buf = ""
        regex = re.compile(prompt_regex, re.MULTILINE)
        end_time = time.time() + timeout
        while time.time() < end_time:
            if chan.recv_ready():
                buf += chan.recv(65535).decode(errors="ignore")
                if regex.search(buf):
                    break
            else:
                time.sleep(0.05)
        return clean_output(buf)

    def _normalize_commands(self, commands) -> List[str]:
        """Flatten commands into a clean list of strings, stripping empty lines."""
        if isinstance(commands, str):
            commands = commands.splitlines()
        flat: List[str] = []
        for item in commands:
            flat.extend([line.rstrip() for line in str(item).splitlines() if line.rstrip()])
        return flat
    
    def deploy_via_cli_paramiko(self, commands, prompt_regex: str = r"[^\r\n]+[>#)] ?$"):
        if not self.ssh:
            raise RuntimeError("CLI deployment requested but no SSH client provided")

        if not hasattr(self, "chan") or self.channel is None:
            self.channel = self.ssh.invoke_shell(term='vt100', width=512, height=24)
            self.channel.settimeout(10)
            self.channel.set_combine_stderr(True)

        channel = self.channel
        channel.settimeout(10)
        channel.set_combine_stderr(True)

        output_lines = ["CLI Session Start\n"]

        # Initial prompt sync
        channel.send("\n")
        self._read_until(channel, prompt_regex)

        # Prevent paging & set wide terminal
        for cmd in ["terminal width 512", "terminal length 0"]:
            channel.send(cmd + "\n")
            self._read_until(channel, prompt_regex)

        for cmd in self._normalize_commands(commands):
            while channel.recv_ready():
                channel.recv(65535)
            channel.send(cmd + "\n")
            time.sleep(0.1)
            resp = self._read_until(channel, prompt_regex)
            output_lines.append(f"\n$ {cmd}")
            output_lines.append(resp.strip())        

        class SimpleResp:
            status_code = 200
            text = "\n".join(output_lines)

        return SimpleResp()

    def deploy_via_cli_netmiko(self, commands):
        """
        Smartly deploys commands by detecting if they are configuration 
        changes or simple 'show' commands.
        """
        if not self.ssh:
            raise RuntimeError("CLI deployment requested but no SSH client provided")

        # 1. Clean up the commands: remove 'conf t', '!', and empty lines
        cleaned_cmds = []
        is_config_block = False

        # Normalize input: ensure it's a list even if a single string was passed
        if isinstance(commands, str):
            commands = commands.splitlines()

        for cmd in commands:
            c = cmd.strip()
            if not c or c == "!":
                continue
            if c.lower() in ["conf t", "configure terminal"]:
                is_config_block = True  # We found a 'conf t', so treat the whole block as config
                continue
            cleaned_cmds.append(c)

        # 2. Execute based on intent
        try:
            # If we detected 'conf t' OR if there are multiple lines (usually a config block)
            if is_config_block or len(cleaned_cmds) > 1:
                # send_config_set automatically enters 'conf t', sends commands, and exits
                output = self.ssh.send_config_set(cleaned_cmds)
            else:
                # Single command (likely a 'show' or 'exec' command)
                output = self.ssh.send_command(cleaned_cmds[0])
                
        except Exception as e:
            output = f"Error during deployment: {str(e)}"

        # 3. Return response object to match your existing UI logic
        class SimpleResp:
            def __init__(self, text):
                self.status_code = 200
                self.text = text

        return SimpleResp(output)

    # -----------------------------
    # NETCONF placeholder (TODO)
    # -----------------------------
    def deploy_via_netconf(self, xml_payload: str):
        raise NotImplementedError("NETCONF deployment not implemented yet.")

    # -----------------------------
    # Block dispatching
    # -----------------------------
    def deploy_block(self, block: Dict[str, Any]) -> Tuple[str, Any]:
        mode = block.get("mode")
        name = block.get("name", "unnamed")

        dispatch = {
            "restconf": lambda b: self.deploy_via_restconf(b["resource"], b["payload"], b.get("method", "PATCH")),
            "cli": lambda b: self.deploy_via_cli_netmiko(b["commands"]),
            "netconf": lambda b: self.deploy_via_netconf(b["xml"]),
        }

        if mode not in dispatch:
            raise ValueError(f"Unknown block mode '{mode}' for block '{name}'")

        return name, dispatch[mode](block)

    # -----------------------------
    # Full list deployment
    # -----------------------------
    def deploy_full(self, blocks: List[Dict[str, Any]]) -> List[Tuple[str, Any]]:
        return [self.deploy_block(b) for b in blocks]

    # -----------------------------
    # Convenience
    # -----------------------------
    def deploy_hostname(self, hostname: str):
        payload = {"Cisco-IOS-XE-native:hostname": hostname}
        return self.api.patch("Cisco-IOS-XE-native:native/hostname", payload_json=payload)