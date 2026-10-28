import Connection
import os
import time
from pyfiglet import Figlet


SSHClient = Connection.SSH()
TelnetClient = Connection.Telnet()
SerialClient = Connection.Serial()


text = Figlet(font='slant')
text = text.renderText('SECOND MIND')


def RunApp():
    global SSHClient, TelnetClient, SerialClient
    app_key = True
    while app_key:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(text)
        print('-'*30)
        print("Connection Type: \n"
              "1| SSH\n"
              "2| Telnet\n"
              "3| Serial\n"
              "4| Exit")
        ConnectionType = input("--> ").strip()
        
        if ConnectionType == '4':
            print("Exiting the program. Goodbye!")
            break
        
        if ConnectionType not in ['1', '2', '3']:
            print("Invalid choice. Please try again.")
            time.sleep(2)
            continue
        if ConnectionType == '1':
            os.system("cls")
            print(text)
            print("SSH Connection")
            print('-'*30)
            hostname = input('IP Address or Host name: ')
            port = input('Port(default=22): ')
            username = input('Username: ')
            password = input('Password: ') 
            connection = SSHClient.connect(hostname=hostname, port=port, username=username, password=password)
            time.sleep(3)
            if not connection:
                response = input("Do you want to Try again?\n"
                                " (y or n) :")
                if response == "y" or response == "Y" or response == "yes":
                    RunApp()
                else:
                    SSHClient.close()
                    app_key = False
            elif connection:
                SSHMenu()
        elif ConnectionType == '2':
            os.system("cls")
            print(text)
            print("Telnet Connection")
            print('-'*30)
            print("Coming soon...")
            time.sleep(3)
            RunApp()
        elif ConnectionType == '3':
            os.system("cls")
            print(text)
            print("Serial Connection")
            print('-'*30)
            print("Coming soon...")
            time.sleep(3)
            RunApp()


def SSHMenu():
    global SSHClient
    key = 1  # if key is 1 the app will be in a loop anf if key is 0 the app will be closed
    os.system("cls")
    print(text)
    print("-"*30)
    connection_info = Connection.device_information(SSHClient, 'SSH')
    try:
        if "Mikrotik" in connection_info:
            print(SSHClient.command("interface/print"))  # print all interfaces
            input('Press Enter to continue...')
            while key == 1:
                time.sleep(1)
                os.system("cls")
                print(text)
                print(connection_info)
                print('-'*30)
                print("0| Close the Connection\n"
                    "1| Command Line\n"
                    "2| Reset the default configuration\n"
                    "3| Change system identity\n"
                    "4| Set Static IP\n"
                    "5| Configure DHCP\n"
                    "6| Configure NAT\n"
                    "7| Configure DNS-Server\n"
                    "8| Setup HomeCPE\n")
                try:
                    command = int(input("--> Choose an option: "))
                    if command == 0:  # If user selects 0, the connection will be closed
                        SSHClient.close()  # close the ssh connection
                        time.sleep(2)
                        key = 0
                    elif command == 1:  # If user selects 1, free command line will be opened
                        os.system("cls")
                        print(text)
                        print("COMMAND LINE\n"
                            "Enter 0 to exit\n"
                            "--------------------")
                        while True:
                            command = input('>>>')  # input command
                            output = Connection.SSH.command(command=command)
                            if command == '0':  # if the user enter 0, the command line will be closed
                                SSHClient.close()
                            else:
                                print(output)
                    elif command == 2:  # If user selects 2,the default config will be reset
                        os.system("cls")
                        print(text)
                        print('RESETTING SYSTEM CONFIGURATION\n'
                            '--------------------')
                        Connection.SSH.command("system/reset-configuration no-defaults=yes")  # reset the default config
                        Connection.SSH.command("y")
                        print("wait few seconds")
                        time.sleep(7)
                        SSHMenu()
                    elif command == 3:  # If user selects 3,system identity will be changed
                        os.system("cls")
                        print(text)
                        print('CHANGE SYSTEM IDENTITY\n'
                            '--------------------')
                        name = input("--> Name: ")  # new identity name
                        SSHClient.command(f'system/identity/set name={name}')  # set the new name

                    elif command == 4:  # If user selects 4,a static ip will be set to an interface
                        ip = input("--> Choose the IP(with subnet mask): ")  # ip address
                        interface = input("--> Choose the Interface(Only The Number): ")  # interface
                        SSHClient.command(f'ip/address/add address={ip} interface=ether{interface}')  # the command to set the static ip
                    elif command == 5:  # If user selects 5,dhcp configuration will be started
                        os.system("cls")
                        print(text)
                        print('CONFIGURING DHCP\n'
                                '------------')
                        print("1| DHCP-Client\n"
                            "2| DHCP-Server")
                        dhcp = int(input("--> "))  # choose between dhcp server and client
                        if dhcp == 1:  # if the user selects 1, the dhcp client will be set
                            interface = input("--> Choose the Interface(Only The Number): ")  # the interface to set dhcp client on it
                            SSHClient.command(f'ip/dhcp-client/add interface=ether{interface} disabled=no')  # set the dhcp client
                        elif dhcp == 2:  # if the user selects 2, the dhcp server will be set
                            print('Enter the questions empty for default configuration')
                            interface = input("--> Choose the Interface(Only The Number): ")  # interface
                            if not interface.strip():  # check if interface is empty or not
                                SSHClient.command('interface/bridge/add name=Default-DHCP')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=ether2')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=ether3')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=ether4')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=ether5')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=wlan1')
                                SSHClient.command('interface/bridge/port/add bridge=Default-DHCP interface=wlan2')
                            ip_ranges = input("--> Choose the IP(with subnet mask): ")  # ip address
                            if not ip_ranges.strip():  # check ip ranges is empty or not
                                SSHClient.command('ip/pool/add name=Default-DHCP ranges=192.168.150.2-192.168.150.254')
                                SSHClient.command('ip/address/add address=192.168.150.1 interface=Default-DHCP')
                                SSHClient.command('ip/dhcp-server/add address-pool=Default-DHCP interface=Default-DHCP disabled=no')
                            else:  # both is empty
                                pool_name = input("--> Choose a name for your IP-pool: ")
                                SSHClient.command(f'ip/pool/add name={pool_name} ranges={ip_ranges}')
                                SSHClient.command(f'ip/dhcp-server/add address-pool={pool_name} interface=ether{interface} disabled=no')
                    elif command == 6:  # If user selects 6,the nat configuration will be started
                        os.system("cls")
                        print(text)
                        interface = input("--> Choose the Interface(Only The Number): ")
                        SSHClient.command(f'/ip/firewall/nat/ add chain=srcnat out-interface=ether{interface} action=masquerade')

                    elif command == 7:  # If user selects 7,dns configuration will be started
                        os.system("cls")
                        print(text)
                        print('CONFIGURING DNS\n'
                            '------------')
                        dns = input("-->DNS server: ")  # dns server
                        SSHClient.command(f'ip/dns/set servers={dns}')  # set the dns server
                    elif command == 8:  # If user selects 8,HomeCPE configuration will be started
                        SSHClient.command('ip/dhcp-client/add interface=ether1 disabled=no')
                        SSHClient.command('interface/bridge/add name=HomeCPE-Bridge')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=ether2')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=ether3')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=ether4')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=ether5')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=wlan1')
                        SSHClient.command('interface/bridge/port/add bridge=HomeCPE-Bridge interface=wlan2')
                        SSHClient.command('ip/pool/add name=HomeCPE ranges=192.168.150.2-192.168.150.254')
                        SSHClient.command('ip/address/add address=192.168.150.1 interface=HomeCPE-Bridge')
                        SSHClient.command('ip/dhcp-server/add address-pool=HomeCPE interface=HomeCPE-Bridge disabled=no')
                except ValueError:
                    print("Invalid input! Please enter a number.")
        elif 'Cisco' in connection_info:
                while key == 1:
                    SSHClient.reconnect()
                    time.sleep(1)
                    os.system("cls")
                    print(text)
                    print(connection_info)
                    print('-'*30)
                    print("0| Close the Connection\n"
                        "1| Vlan\n")
                    try:
                        command = int(input("Choose an option: "))
                        if command == 0:
                            SSHClient.close()
                            time.sleep(2)
                            key = 0
                        elif command == 1:
                            os.system("cls")
                            print(text)
                            print(connection_info)
                            print('-'*30)
                            VlanID = int(input('Vlan-ID: '))
                            VlanName = input('Vlan Name: ')
                            ports = SSHClient.command('show interface status\n')
                            lines = ports.strip().splitlines()[1:]
                            ports = [line.split()[0] for line in lines] 

                            selected_ports = []
                            while True:
                                print("\nAvailable Ports:")
                                for idx, port in enumerate(ports, start=1):
                                    print(f"{idx}. {port}")

                                user_choice = input("Enter the number of the port to select (or type 'done' to finish): ")

                                if user_choice.lower() == 'done':
                                    break 

                                try:
                                    port_index = int(user_choice) - 1  
                                    if 0 <= port_index < len(ports):
                                        selected_port = ports[port_index]
                                        selected_ports.append(selected_port)
                                        print(f"Port '{selected_port}' added to selection.")
                                    else:
                                        print("Invalid choice. Please enter a valid port number.")
                                except ValueError:
                                    print("Invalid input. Please enter a number or 'done' to finish.")
                            print("\nSelected Ports:")
                            for port in selected_ports:
                                print(port)
                            SSHClient.command('configure terminal')
                            SSHClient.command(f'vlan {VlanID}')
                            SSHClient.command(f'name {VlanName}')
                            for i in range(len(selected_ports)):
                                SSHClient.command(f'interface {selected_ports[i]}')
                                SSHClient.command(f'switchport access vlan{VlanID}')

                            
                    except ValueError:
                        print("Invalid input! Please enter a number.")
    except Exception as e:
        print(f"Error in SSH Menu: {str(e)}")
        SSHClient.close()
        return
        
        
def TelnetMenu():
    pass

def SerialMenu():
    pass

if __name__ == "__main__":
    RunApp()