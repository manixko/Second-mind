import os
import re
import time
import paramiko
import serial
from telnetlib3.sync import TelnetConnection


class SSH:
    def __init__(self):
        self.client = paramiko.SSHClient()
        self.hostname = None
        self.port = None
        self.username = None
        self.password = None

    def connect(self, hostname, port, username, password=None):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        try:
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=self.hostname, port=self.port, username=self.username, password=self.password, look_for_keys=False, allow_agent=False)
            print("SSH connection established successfully!")
            return True
        except Exception as e:
            print(f"Failed to establish SSH connection: {e}")
            return False

    def command(self, command):
        try:
            if not self.client.get_transport().is_active():
                self.reconnect()  # Attempt to reconnect if connection is inactive
            stdin, stdout, stderr = self.client.exec_command(command)
            output = stdout.read().decode()
            return output.strip()
        except Exception as e:
            print(f"Error executing command over SSH: {e}")
            return ""
        
    def reconnect(self):
        try:
            self.client.connect(hostname=self.hostname, port=self.port, username=self.username, password=self.password)
            return True
        except Exception as e:
            print(f"Reconnection failed: {e}")
            return False

    def close(self):
        self.client.close()
        print("SSH connection closed.")


class Telnet:
    """Synchronous Telnet client compatible with the existing Second Mind API."""

    LOGIN_TIMEOUT = 12
    COMMAND_TIMEOUT = 20
    READ_INTERVAL = 0.4
    IDLE_TIMEOUT = 1.0

    def __init__(self):
        self.client = None
        self.hostname = None
        self.port = None
        self.username = None
        self.password = None
        self.prompt = None

    @staticmethod
    def _is_username_prompt(text):
        return bool(re.search(r"(?:login|username)\s*:\s*$", text, re.IGNORECASE))

    @staticmethod
    def _is_password_prompt(text):
        return bool(re.search(r"password\s*:\s*$", text, re.IGNORECASE))

    @staticmethod
    def _is_device_prompt(text):
        # Cisco: Router>, Router# | MikroTik: [admin@MikroTik] >
        lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
        if not lines:
            return False
        last_line = lines[-1]
        return bool(
            re.search(r"\[[^\]]+\]\s*[>#]\s*$", last_line)
            or re.search(r"[A-Za-z0-9_.()/-]+[>#]\s*$", last_line)
        )

    @staticmethod
    def _has_auth_error(text):
        return bool(re.search(
            r"(login incorrect|authentication failed|access denied|invalid username|invalid password|%\s*login invalid)",
            text,
            re.IGNORECASE,
        ))

    def _read_some(self, timeout=None):
        """Read one available Telnet chunk; a timeout simply means no new data."""
        try:
            return self.client.read_some(timeout=timeout or self.READ_INTERVAL)
        except TimeoutError:
            return ""

    def _read_until_login_state(self, timeout):
        """Read until a username prompt, password prompt, or device prompt appears."""
        collected = ""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            chunk = self._read_some(min(self.READ_INTERVAL, max(0.1, deadline - time.monotonic())))
            if chunk:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="replace")
                collected += chunk

                if self._has_auth_error(collected):
                    raise PermissionError("Telnet authentication failed: device rejected the credentials.")
                if self._is_username_prompt(collected):
                    return "username", collected
                if self._is_password_prompt(collected):
                    return "password", collected
                if self._is_device_prompt(collected):
                    return "prompt", collected

        return None, collected

    def connect(self, hostname, port, username, password=None):
        self.hostname = hostname
        self.port = int(port)
        self.username = username or ""
        self.password = password or ""
        self.prompt = None

        try:
            self.client = TelnetConnection(
                self.hostname,
                self.port,
                timeout=2,
                connect_timeout=10,
                encoding="utf8",
            )
            self.client.connect()

            # Some devices show the login prompt immediately; others wait for Enter.
            state, response = self._read_until_login_state(3)
            if state is None:
                self.client.write("\r\n")
                state, response = self._read_until_login_state(self.LOGIN_TIMEOUT)

            # Handle username/password prompts in either order. This covers common
            # RouterOS and Cisco VTY login sequences without assuming exact casing.
            for _ in range(4):
                if state == "username":
                    self.client.write(self.username + "\r\n")
                    state, response = self._read_until_login_state(self.LOGIN_TIMEOUT)
                elif state == "password":
                    self.client.write(self.password + "\r\n")
                    state, response = self._read_until_login_state(self.LOGIN_TIMEOUT)
                elif state == "prompt":
                    self.prompt = response.splitlines()[-1].strip()
                    print("Telnet connection established successfully!")
                    return True
                else:
                    break

            if self._has_auth_error(response):
                raise PermissionError("Telnet authentication failed: device rejected the credentials.")
            raise TimeoutError(
                "Could not detect a Telnet login prompt or device command prompt. "
                "Check the device's Telnet service and login configuration."
            )

        except Exception as e:
            print(f"Failed to establish Telnet connection: {e}")
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            return False

    def command(self, command):
        if not self.client:
            print("Error executing command over Telnet: not connected.")
            return ""

        try:
            # Discard any leftover bytes from the previous command.
            while self._read_some(0.05):
                pass

            self.client.write(str(command) + "\r\n")
            self.client.flush(timeout=2)

            output = ""
            deadline = time.monotonic() + self.COMMAND_TIMEOUT
            last_data_time = None

            while time.monotonic() < deadline:
                chunk = self._read_some(self.READ_INTERVAL)
                if chunk:
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8", errors="replace")
                    output += chunk
                    last_data_time = time.monotonic()

                    # A returned command prompt marks the end of normal CLI output.
                    if self._is_device_prompt(output):
                        break
                elif output and last_data_time is not None:
                    if time.monotonic() - last_data_time >= self.IDLE_TIMEOUT:
                        break

            return output.strip()

        except Exception as e:
            print(f"Error executing command over Telnet: {e}")
            return ""

    def close(self):
        if self.client:
            try:
                self.client.close()
            finally:
                self.client = None
                print("Telnet connection closed.")


# Console (Serial) Class
class Serial:
    def __init__(self):
        self.ser = None

    def connect(self, port, baudrate=9600):
        try:
            self.ser = serial.Serial(port, baudrate)
            time.sleep(2)  # Wait for the connection to establish
            if self.ser.is_open:
                print("Serial connection established successfully!")
                return True
            else:
                print("Failed to open Serial connection.")
                return False
        except Exception as e:
            print(f"Failed to establish Serial connection: {e}")
            return False

    def command(self, command):
        try:
            self.ser.write(command.encode('ascii') + b"\n")
            time.sleep(1)
            output = self.ser.read(self.ser.in_waiting).decode('ascii')
            return output.strip()
        except Exception as e:
            print(f"Error executing command over Serial: {e}")
            return ""

    def close(self):
        if self.ser:
            self.ser.close()
            print("Serial connection closed.")


def device_information(connection, connection_type): 
    try:
        if connection_type not in ['SSH', 'Telnet', 'Console']:
            raise ValueError(f"Unsupported connection type: {connection_type}")

        # Initialize brand and model info
        brand = "Unknown"
        model_info = "Model not identified"

        # Common commands for different devices
        commands = [
            'show version',  # Cisco
            'system/package/print',  # Mikrotik
        ]

        for cmd in commands:
            response = connection.command(cmd)
            if response:
                if 'routeros' in response.lower():
                    brand = "Mikrotik"
                    match = re.search(r'model:\s*(\S+)', response)
                    model_info = match.group(1) if match else "Virtual Machine"
                elif 'cisco' in response.lower():
                    connection.command('terminal length 0')
                    NewResponse = connection.command('show version')
                    brand = "Cisco"
                    # pattern = re.compile(r'Model number\s*:\s*(.*)')
                    pattern = re.compile(r'WS-C\d{4}[A-Z]*-\d{2,3}[A-Z]*-[A-Z]')
                    match = pattern.search(NewResponse)
                    if match:
                        model_info = match.group(0)
                    # match = re.search(r'CISCO\d{4}/K9\b', NewResponse)
                    # model_info = match.group(0) if match else "Model not found in output"
                if brand != "Unknown":
                    break

        return f"Device: {brand}, Model: {model_info}"

    except Exception as e:
        print(f"Error identifying device model: {e}")
        return "Device model identification failed"


if __name__ == "__main__":
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("Choose your connection type:")
        print("1| SSH")
        print("2| Telnet")
        print("3| Serial")
        print("4| Exit")
        
        connection_type = input(": ").strip()

        if connection_type == '4':
            print("Exiting the program. Goodbye!")
            break

        if connection_type not in ['1', '2', '3']:
            print("Invalid choice. Please try again.")
            time.sleep(2)
            continue

        os.system('cls' if os.name == 'nt' else 'clear')
        
        if connection_type == '1':
            print("SSH Connection\n--------------------")
            client = SSH()
            conn_type = 'SSH'
        elif connection_type == '2':
            print("Telnet Connection\n--------------------")
            client = Telnet()
            conn_type = 'Telnet'
        else:
            print("Serial Connection\n--------------------")
            client = Serial()
            conn_type = 'Console'

        hostname = input('IP Address or Host Name: ')
        port = input('Port: ')
        username = input('Username: ')
        password = input('Password: ')

        if client.connect(hostname=hostname, port=port, username=username, password=password):
            device_info = device_information(client, conn_type)
            print(device_info)
            client.close()
        
        input("\nPress Enter to continue...")