# app/services/deployer.py
from typing import Any, Dict, List, Tuple, Optional
import time
import re

from app.services.output_cleaner import clean_output


class Deployer:
    def __init__(self, api, ssh_client=None, netconf_client=None):
        self.api = api
        self.ssh = ssh_client
        self.netconf = netconf_client

    # -----------------------------
    # Specific helper (kept): IOS-XE hostname via RESTCONF
    # -----------------------------
    def deploy_hostname(self, hostname: str):
        payload = {"Cisco-IOS-XE-native:hostname": hostname}
        return self.api.patch(
            "Cisco-IOS-XE-native:native/hostname",
            payload_json=payload
        )

    # -----------------------------
    # Generic RESTCONF executor
    # -----------------------------
    def deploy_via_restconf(self, resource: str, payload: Dict[str, Any], method: str = "PATCH"):
        m = method.upper()
        if m == "PATCH":
            return self.api.patch(resource, payload_json=payload)
        elif m == "PUT":
            return self.api.put(resource, payload_json=payload)
        else:
            raise ValueError(f"Unsupported RESTCONF method: {method}")

    # -----------------------------
    # CLI executor (interactive shell so config mode persists)
    # -----------------------------
    from app.services.output_cleaner import clean_output

    def deploy_via_cli(self, commands, prompt_regex=r"[^\r\n]+[>#)] ?$"):
        if not self.ssh:
            raise RuntimeError("CLI deployment requested but no SSH client provided")

        # Open a PTY with a wide width to prevent line-wrapping/echo glitches
        chan = self.ssh.invoke_shell(term='vt100', width=512, height=24)
        chan.settimeout(10)
        chan.set_combine_stderr(True)

        def read_until(prompt, timeout=10):
            end = time.time() + timeout
            buf = ""
            regex = re.compile(prompt, re.MULTILINE)
            while time.time() < end:
                if chan.recv_ready():
                    chunk = chan.recv(65535).decode(errors="ignore")
                    buf += chunk
                    if regex.search(buf):
                        break
                else:
                    time.sleep(0.05)
            return clean_output(buf)

        output_lines = []
        output_lines.append("CLI Session Start\n")

        # initial prompt
        chan.send("\r")
        read_until(prompt_regex)

        # Prevent paging + widen terminal on the device side too
        chan.send("terminal width 512\r")
        output_lines.append("> terminal width 512")
        output_lines.append(read_until(prompt_regex))

        chan.send("terminal length 0\r")
        output_lines.append("> terminal length 0")
        output_lines.append(read_until(prompt_regex))

        for cmd in commands:
            chan.send(cmd + "\r")
            # tiny pause can help on some platforms
            time.sleep(0.03)
            resp = read_until(prompt_regex)

            output_lines.append(f"\n$ {cmd}")
            output_lines.append(resp.strip())

        chan.close()

        class SimpleResp:
            status_code = 200
            text = "\n".join(output_lines)

        return SimpleResp()

    # -----------------------------
    # NETCONF placeholder
    # -----------------------------
    def deploy_via_netconf(self, xml_payload: str):
        raise NotImplementedError("NETCONF deployment not wired yet.")

    # -----------------------------
    # Block dispatcher
    # -----------------------------
    def deploy_block(self, block: Dict[str, Any]) -> Tuple[str, Any]:
        mode = block.get("mode")
        name = block.get("name", "unnamed")

        if mode == "restconf":
            return name, self.deploy_via_restconf(
                block["resource"],
                block["payload"],
                block.get("method", "PATCH")
            )
        elif mode == "cli":
            return name, self.deploy_via_cli(block["commands"])
        elif mode == "netconf":
            return name, self.deploy_via_netconf(block["xml"])
        else:
            raise ValueError(f"Unknown block mode '{mode}' for block '{name}'")

    # -----------------------------
    # Run full block list
    # -----------------------------
    def deploy_full(self, blocks: List[Dict[str, Any]]) -> List[Tuple[str, Any]]:
        results: List[Tuple[str, Any]] = []
        for block in blocks:
            results.append(self.deploy_block(block))
        return results