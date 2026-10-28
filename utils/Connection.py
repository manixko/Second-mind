import os
import re
import time
import paramiko
import serial
import telnetlib


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
    def __init__(self):
        self.client = telnetlib.Telnet()
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
            self.client.open(self.hostname, self.port)
            self.client.read_until(b"login: ")
            self.client.write(self.username.encode('ascii') + b"\n")
            if self.password:
                self.client.read_until(b"Password: ")
                self.client.write(self.password.encode('ascii') + b"\n")
            print("Telnet connection established successfully!")
            return True
        except Exception as e:
            print(f"Failed to establish Telnet connection: {e}")
            return False

    def command(self, command):
        try:
            self.client.write(command.encode('ascii') + b"\n")
            time.sleep(1)
            output = self.client.read_very_eager().decode('ascii')
            return output.strip()
        except Exception as e:
            print(f"Error executing command over Telnet: {e}")
            return ""

    def close(self):
        self.client.close()
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