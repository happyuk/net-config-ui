# app/services/deployer.py
from typing import Any, Dict, List, Tuple
import time
import re

from app.services.output_cleaner import clean_output

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

    def deploy_via_cli(self, commands, prompt_regex: str = r"[^\r\n]+[>#)] ?$"):
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
            "cli": lambda b: self.deploy_via_cli(b["commands"]),
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