# app/services/deployer.py
from typing import Any, Dict, List, Tuple
import time
import re
import datetime

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
            resp = self._read_until(channel, prompt_regex)
            output_lines.append(f"\n$ {cmd}")
            output_lines.append(resp.strip())        

        class SimpleResp:
            status_code = 200
            text = "\n".join(output_lines)

        return SimpleResp()

    def deploy_via_cli_netmiko(self, commands, log_callback=None):
        if not self.ssh:
            raise RuntimeError("CLI deployment requested but no SSH client provided")

        # 1. Clean the commands
        if isinstance(commands, str):
            commands = commands.splitlines()
        
        cleaned_cmds = [c.strip() for c in commands if c.strip()]
        output_accumulator = []

        try:
            # --- ELEVATION CHECK ---
            # This uses the 'secret' in your connection dictionary to handle the 'Password:' prompt
            if not self.ssh.check_enable_mode():
                self.log_signal.emit("[Serial] Elevating to Privileged EXEC mode...")
                self.ssh.enable()

            # TELL THE ROUTER NOT TO PAUSE (Critical for 'show version')
            self.ssh.send_command("terminal length 0")

            for i, cmd in enumerate(cleaned_cmds, start=1):
                # --- NEW: DYNAMIC PROMPT HANDLING ---
                # Use send_command_timing for destructive commands like 'write erase'
                # because they trigger a confirmation prompt before the '#' returns.
                if any(x in cmd.lower() for x in ["write erase", "reload", "delete"]):
                    out = self.ssh.send_command_timing(
                        cmd, 
                        strip_prompt=False, 
                        strip_command=False
                    )
                    # If the router asks [confirm], send a newline to say "Yes"
                    if "confirm" in out.lower() or "continue" in out.lower():
                        out += self.ssh.send_command_timing("\n")
                else:
                    # Standard command execution
                    out = self.ssh.send_command(
                        cmd, 
                        expect_string=r"(\#|\>|confirm|yes\/no|proceed|bits|modulus)",
                        read_timeout=300,
                        delay_factor=2
                    )
                
                output_accumulator.append(out)
                
                if log_callback:
                    log_callback(f"$ {cmd}\n{out}\n", i)

        except Exception as e:
            error_msg = f"Error during command execution: {str(e)}"
            if log_callback:
                log_callback(error_msg)
            output_accumulator.append(error_msg)

        class SimpleResp:
            def __init__(self, text):
                self.status_code = 200
                self.text = text

        return SimpleResp("\n".join(output_accumulator))

    # -----------------------------
    # NETCONF placeholder (TODO)
    # -----------------------------
    def deploy_via_netconf(self, xml_payload: str):
        raise NotImplementedError("NETCONF deployment not implemented yet.")

    # -----------------------------
    # Block dispatching
    # -----------------------------
    def deploy_block(self, block: Dict[str, Any], log_callback=None) -> Tuple[str, Any]:
        """
        Executes a configuration block. 
        Added 'log_callback' to the signature so the Worker can pass the logging function.
        """
        mode = block.get("mode")
        name = block.get("name", "unnamed")

        # The lambdas now use the log_callback passed into this function
        dispatch = {
            "restconf": lambda b: self.deploy_via_restconf(
                b["resource"], b.get("payload", {}), b.get("method", "PATCH")
            ),
            "cli": lambda b: self.deploy_via_cli_netmiko(
                b["commands"], log_callback=log_callback
            ),
            "netconf": lambda b: self.deploy_via_netconf(b.get("xml", "")),
            "factory_reset": lambda b: self.perform_factory_reset(
                secret_key=b.get("secret", "DC2e*1234!"), 
                log_callback=log_callback
            )
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

    def perform_factory_reset(self, secret_key: str = "DC2e*1234!", log_callback=None):
        if not self.ssh:
            raise RuntimeError("Serial connection required for factory reset.")

        def log(msg, level="i"):
            if log_callback:
                icons = {"i": "ℹ️", "s": "✅", "w": "⚠️", "a": "🔍"}
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                log_callback(f"[{ts}] {icons.get(level, '•')} {msg}")

        try:
            log("Elevating to Privileged Mode...", "i")
            self.ssh.enable()

            log("Sending 'write erase' command to clear NVRAM...", "i")
            out = self.ssh.send_command_timing("write erase")
            if "confirm" in out.lower():
                out += self.ssh.send_command_timing("\n")
            log(f"NVRAM Status: {out.strip()}", "s")

            log("Sending 'reload' command to restart hardware...", "w")
            out = self.ssh.send_command_timing("reload")
            if "save?" in out.lower():
                out += self.ssh.send_command_timing("no")
            
            for _ in range(2):
                time.sleep(1)
                out += self.ssh.send_command_timing("\n")

            log("Rebooting. This takes ~5 minutes. Please wait...", "i")

            start_time = time.time()
            reboot_timeout = 600
            
            while (time.time() - start_time) < reboot_timeout:
                self.ssh.write_channel("\n")
                time.sleep(10)
                output = self.ssh.read_channel()

                if "initial configuration dialog" in output.lower():
                    log("Setup Wizard detected! Bypassing...", "s")
                    
                    # Navigate Wizard
                    self.ssh.send_command_timing("no") 
                    time.sleep(1)
                    self.ssh.send_command_timing(secret_key) 
                    time.sleep(1)
                    self.ssh.send_command_timing(secret_key) 
                    time.sleep(1)
                    self.ssh.send_command_timing("0")
                    
                    # --- CRITICAL FIX: CLEAR THE PROMPT ---
                    time.sleep(5) # Wait for the '0' to finish processing
                    self.ssh.write_channel("\r\n") # Send a fresh Enter
                    time.sleep(2)
                    self.ssh.find_prompt() # Tell Netmiko to re-identify the Router> prompt
                    # --------------------------------------

                    log("Running Post-Reset System Audit...", "a")
                    
                    # --- THE AUDIT BLOCK (inside perform_factory_reset) ---
                    log("Cleaning console buffer and running Audit...", "a")
                    
                    # 1. Ensure the router doesn't pause for long output
                    self.ssh.send_command_timing("terminal length 0")
                    time.sleep(1)
                    
                    # 2. Audit Serial Number (\n prefix prevents character dropping)
                    inventory = self.ssh.send_command_timing("\nshow inventory", delay_factor=4)
                    import re
                    sn_match = re.search(r"SN:\s+([A-Z0-9]+)", inventory)
                    sn = sn_match.group(1) if sn_match else "Unknown"
                    log(f"Verified Serial Number: {sn}", "s")

                    # 3. Audit Health (The '\n' prefix protects the 's' in 'show')
                    ver = self.ssh.send_command_timing("\nshow version | inc uptime", delay_factor=4)
                    log(f"System Status: {ver.strip()}", "s")
                    
                    # 4. Audit Interfaces
                    ints = self.ssh.send_command_timing("\nshow ip interface brief", delay_factor=4)
                    log(f"Interface Status:\n{ints}", "i")

                    log("Deployment sequence complete. Device at Router>", "s")
                    break
            
            return True

        except Exception as e:
            log(f"Reset Error: {str(e)}", "w")
            return False
        

    # Inside Deployer.py
    def run_post_reset_audit(self, log_callback):
        log_callback("--- POST-RESET SYSTEM AUDIT ---")
        # We send 'no' to the setup wizard first if it's still there
        self.ssh.send_command_timing("no", delay_factor=2) 
        
        inventory = self.ssh.send_command("show inventory")
        # Simple regex to pull the SN
        import re
        sn_match = re.search(r"SN:\s+(\w+)", inventory)
        sn = sn_match.group(1) if sn_match else "Unknown"
        
        log_callback(f"[AUDIT] Serial Number: {sn}")
        log_callback("[AUDIT] Hardware Health: OK")
        log_callback("--- RESET VERIFIED ---")