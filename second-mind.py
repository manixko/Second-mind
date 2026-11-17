from __future__ import annotations

import queue
import threading
import re
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

try:
    from utils import Connection as connection
except ImportError:
    import utils.Connection as connection

try:
    from utils.config_manager import ConfigManager
except ImportError:
    from utils.config_manager import ConfigManager

ctk.set_default_color_theme("blue")
ctk.set_appearance_mode("dark")

DEFAULT_PORTS = {"SSH": "22", "Telnet": "23"}


class SecondMindApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Second Mind")
        self.geometry("1180x760")
        self.minsize(760, 520)

        self.client = None
        self.connection_protocol = None
        self.host = ""
        self.username = ""
        self.device_info = "Device not identified"
        self.device_brand = "Unknown"
        self.device_model = "Model not identified"
        self.events = queue.Queue()
        self.busy = False
        self.appearance = "dark"

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.connection_view = ConnectionView(
            self.container, self.start_connect, self.toggle_theme
        )
        self.workspace_view = WorkspaceView(
            self.container, self.run_command, self.disconnect,
            self.toggle_theme, self.execute_config
        )
        self.connection_view.grid(row=0, column=0, sticky="nsew")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self.poll_events)

    def toggle_theme(self):
        self.appearance = "light" if self.appearance == "dark" else "dark"
        ctk.set_appearance_mode(self.appearance)
        label = "☀ Light mode" if self.appearance == "dark" else "☾ Dark mode"
        self.connection_view.theme_button.configure(text=label)
        self.workspace_view.theme_button.configure(text=label)

    def start_connect(self, protocol, host, port, username, password):
        if self.busy:
            return
        self.busy = True
        self.connection_view.set_status("Connecting to device…", busy=True)
        threading.Thread(
            target=self._connect_worker,
            args=(protocol, host, port, username, password),
            daemon=True,
        ).start()

    def _connect_worker(self, protocol, host, port, username, password):
        client = None
        try:
            client = connection.SSH() if protocol == "SSH" else connection.Telnet()
            ok = client.connect(
                hostname=host, port=int(port), username=username, password=password
            )
            if not ok:
                try:
                    client.close()
                except Exception:
                    pass
                self.events.put((
                    "connect_error",
                    "Connection failed. Check the address, port, credentials, and device reachability.",
                ))
                return
            info = connection.device_information(client, protocol)
            self.events.put(("connected", {
                "client": client, "protocol": protocol, "host": host,
                "username": username, "info": info,
            }))
        except Exception as exc:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            self.events.put(("connect_error", str(exc)))

    def run_command(self, command):
        if not self.client or self.busy or not command.strip():
            return
        self.busy = True
        self.workspace_view.set_busy(True)
        threading.Thread(
            target=self._command_worker, args=(command,), daemon=True
        ).start()

    def execute_config(self, commands):
        if not self.client or self.busy or not commands:
            return
        self.busy = True
        self.workspace_view.set_busy(True)
        threading.Thread(
            target=self._config_worker, args=(list(commands),), daemon=True
        ).start()

    def _config_worker(self, commands):
        results = []
        for command in commands:
            try:
                output = self.client.command(command)
                results.append((command, output or "(No output returned)"))
            except Exception as exc:
                results.append((command, f"Command error: {exc}"))
                break
        self.events.put(("config_result", results))

    def _command_worker(self, command):
        try:
            output = self.client.command(command)
            self.events.put(("command_result", (command, output or "(No output returned)")))
        except Exception as exc:
            self.events.put(("command_result", (command, f"Command error: {exc}")))

    def poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "connect_error":
                    self.busy = False
                    self.connection_view.set_status("Could not connect", busy=False)
                    messagebox.showerror("Connection failed", payload, parent=self)
                elif kind == "connected":
                    self.busy = False
                    self.client = payload["client"]
                    self.connection_protocol = payload["protocol"]
                    self.host = payload["host"]
                    self.username = payload["username"]
                    self.device_info = payload["info"]
                    match = re.search(
                        r"Device:\s*([^,]+),\s*Model:\s*(.*)", self.device_info
                    )
                    self.device_brand = match.group(1).strip() if match else "Unknown"
                    self.device_model = match.group(2).strip() if match else "Model not identified"
                    self.workspace_view.load({
                        **payload,
                        "brand": self.device_brand,
                        "model": self.device_model,
                    })
                    self.connection_view.grid_remove()
                    self.workspace_view.grid(row=0, column=0, sticky="nsew")
                elif kind == "command_result":
                    self.busy = False
                    self.workspace_view.set_busy(False)
                    self.workspace_view.append_result(*payload)
                elif kind == "config_result":
                    self.busy = False
                    self.workspace_view.set_busy(False)
                    for command, output in payload:
                        self.workspace_view.append_result(command, output)
        except queue.Empty:
            pass
        self.after(80, self.poll_events)

    def disconnect(self):
        client, self.client = self.client, None
        if client:
            threading.Thread(target=self._close_worker, args=(client,), daemon=True).start()
        self.workspace_view.grid_remove()
        self.connection_view.grid(row=0, column=0, sticky="nsew")
        self.connection_view.set_status("Disconnected", busy=False)
        self.workspace_view.reset()
        self.busy = False
        self.connection_protocol = None
        self.host = ""
        self.username = ""

    @staticmethod
    def _close_worker(client):
        try:
            client.close()
        except Exception:
            pass

    def on_close(self):
        if self.client:
            self._close_worker(self.client)
            self.client = None
        self.destroy()


class ConnectionView(ctk.CTkFrame):
    def __init__(self, master, on_connect, toggle_theme):
        super().__init__(master, corner_radius=0)
        self.on_connect = on_connect
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="new", padx=28, pady=22)
        ctk.CTkLabel(
            top, text="SECOND MIND",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")
        self.theme_button = ctk.CTkButton(
            top, text="☀ Light mode", width=120, height=32,
            command=toggle_theme, fg_color="transparent", border_width=1,
            text_color=("#202938", "#E7ECF5")
        )
        self.theme_button.pack(side="right")

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)

        self.card = ctk.CTkFrame(center, corner_radius=20, border_width=1, width=620, height=510)
        self.card.grid(row=0, column=0, sticky="", padx=12, pady=8)
        self.card.grid_columnconfigure(1, weight=1)
        self.card.grid_columnconfigure(0, minsize=105)
        self.card.grid_propagate(False)

        def resize_card(event):
            desired = max(360, min(620, event.width - 24))
            if self.card.winfo_width() != desired:
                self.card.configure(width=desired)
        center.bind("<Configure>", resize_card)

        ctk.CTkLabel(
            self.card, text="Manage your devices",
            font=ctk.CTkFont(size=27, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=28, pady=(26, 5))
        ctk.CTkLabel(
            self.card, text="Securely connect to network equipment.",
            text_color=("#687386", "#9AA6B8"), font=ctk.CTkFont(size=13)
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 20))

        self.protocol_switch = ctk.CTkSegmentedButton(
            self.card, values=["SSH", "Telnet"], command=self._protocol_changed, height=36
        )
        self.protocol_switch.set("SSH")
        self.protocol_switch.grid(row=2, column=0, columnspan=2, padx=28, pady=(0, 14), sticky="ew")

        self.host_entry = self._field(self.card, "Host / IP", "192.168.1.1", 3)
        self.port_entry = self._field(self.card, "Port", "22", 4)
        self.port_entry.insert(0, "22")
        self.user_entry = self._field(self.card, "Username", "e.g. admin", 5)
        self.pass_entry = self._field(self.card, "Password", "Enter password", 6, show="*")
        self.pass_entry.bind("<Return>", lambda _event: self._submit())

        self.connect_button = ctk.CTkButton(
            self.card, text="Connect to device  →", height=42, corner_radius=10,
            command=self._submit, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.connect_button.grid(row=7, column=0, columnspan=2, padx=28, pady=(20, 10), sticky="ew")
        self.status_label = ctk.CTkLabel(
            self.card, text="SSH connection ready",
            text_color=("#687386", "#9AA6B8")
        )
        self.status_label.grid(row=8, column=0, columnspan=2, padx=28, pady=(0, 20))
        ctk.CTkLabel(
            self, text="SECOND MIND  •  NETWORK DEVICE WORKSPACE",
            text_color=("#8A93A3", "#677286"),
            font=ctk.CTkFont(size=10, weight="bold")
        ).grid(row=2, column=0, pady=(0, 12))

    @staticmethod
    def _field(parent, label, placeholder, row, show=None):
        ctk.CTkLabel(
            parent, text=f"{label}:", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=row, column=0, padx=(28, 12), pady=6, sticky="w")
        widget = ctk.CTkEntry(
            parent, placeholder_text=placeholder, height=38, corner_radius=9, show=show
        )
        widget.grid(row=row, column=1, padx=(0, 28), pady=6, sticky="ew")
        return widget

    def _protocol_changed(self, value):
        old = self.port_entry.get().strip()
        if old in DEFAULT_PORTS.values() or not old:
            self.port_entry.delete(0, "end")
            self.port_entry.insert(0, DEFAULT_PORTS[value])

    def _submit(self):
        protocol = self.protocol_switch.get()
        host, port = self.host_entry.get().strip(), self.port_entry.get().strip()
        username, password = self.user_entry.get().strip(), self.pass_entry.get()
        if not host or not port or not username:
            messagebox.showwarning(
                "Missing information", "Please enter a host, port, and username.", parent=self
            )
            return
        try:
            port_number = int(port)
            if not 1 <= port_number <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Invalid port", "Port must be a number between 1 and 65535.", parent=self
            )
            return
        self.on_connect(protocol, host, port_number, username, password)

    def set_status(self, text, busy=False):
        self.status_label.configure(text=text)
        self.connect_button.configure(
            state="disabled" if busy else "normal",
            text="Connecting…" if busy else "Connect to device  →"
        )


class WorkspaceView(ctk.CTkFrame):
    """Three-column workspace. The center navigation and right panel are placeholders for now."""

    def __init__(self, master, on_command, on_disconnect, toggle_theme, on_execute_config):
        super().__init__(master, corner_radius=0)
        self.on_command = on_command
        self.on_disconnect = on_disconnect
        self.on_execute_config = on_execute_config
        self.config_manager = ConfigManager()
        self.current_vendor = ""
        self.selected_config = None
        self.input_widgets = {}
        self.device_client = None
        self.interfaces = []

        # Main layout: device sidebar | dynamic option list | selected option panel
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=22, minsize=180, uniform="workspace_columns")
        self.grid_columnconfigure(1, weight=25, minsize=200, uniform="workspace_columns")
        self.grid_columnconfigure(2, weight=53, minsize=280, uniform="workspace_columns")

        # LEFT SIDEBAR -------------------------------------------------------
        self.sidebar = ctk.CTkFrame(self, width=205, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            self.sidebar, text="SECOND MIND",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=18, pady=(24, 2))
        ctk.CTkLabel(
            self.sidebar, text="DEVICE MANAGER",
            text_color=("#687386", "#8995A8"), font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", padx=18, pady=(0, 26))

        self._sidebar_section("CONNECTED DEVICE")
        self.device_name_label = ctk.CTkLabel(
            self.sidebar, text="Unknown device", anchor="w", justify="left",
            font=ctk.CTkFont(size=14, weight="bold"), wraplength=165
        )
        self.device_name_label.pack(fill="x", padx=18, pady=(4, 12))
        self._sidebar_detail("Model", "—", "model_value")
        self._sidebar_detail("Connection", "—", "connection_value")
        self._sidebar_detail("Username", "—", "username_value")
        self._sidebar_detail("Host / IP", "—", "host_value")

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=14)
        self.theme_button = ctk.CTkButton(
            bottom, text="☀ Light mode", command=toggle_theme,
            fg_color="transparent", border_width=1,
            text_color=("#202938", "#E7ECF5"), height=34
        )
        self.theme_button.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            bottom, text="←  Disconnect", command=on_disconnect,
            fg_color="transparent", border_width=1,
            text_color=("#B42318", "#FF8B82"),
            hover_color=("#FEE4E2", "#402322"), height=36
        ).pack(fill="x")

        # MIDDLE OPTION LIST -------------------------------------------------
        self.option_panel = ctk.CTkFrame(self, corner_radius=0, border_width=1)
        self.option_panel.grid(row=0, column=1, sticky="nsew")
        self.option_panel.grid_columnconfigure(0, weight=1)
        self.option_panel.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(
            self.option_panel, text="CONFIGURATION",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#687386", "#8995A8")
        ).grid(row=0, column=0, sticky="w", padx=17, pady=(25, 5))
        ctk.CTkLabel(
            self.option_panel, text="Device tools",
            font=ctk.CTkFont(size=19, weight="bold")
        ).grid(row=1, column=0, sticky="w", padx=17, pady=(0, 18))

        self.options_list = ctk.CTkScrollableFrame(
            self.option_panel, fg_color="transparent", corner_radius=0
        )
        self.options_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.empty_options = ctk.CTkLabel(
            self.options_list,
            text="Connect to a supported device\nto load its configurations.",
            justify="left", anchor="w", wraplength=175,
            text_color=("#687386", "#8995A8")
        )
        self.empty_options.pack(fill="x", padx=8, pady=12)

        # RIGHT CONFIGURATION AREA ------------------------------------------
        self.config_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.config_panel.grid(row=0, column=2, sticky="nsew", padx=22, pady=22)
        self.config_panel.grid_columnconfigure(0, weight=1)
        self.config_panel.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(self.config_panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(2, 22))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="WORKSPACE",
            text_color=("#687386", "#8995A8"),
            font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        self.connection_badge = ctk.CTkLabel(
            top, text="● Connected",
            text_color=("#16803D", "#5DDA8A"),
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.connection_badge.grid(row=0, column=1, sticky="e")

        self.config_title = ctk.CTkLabel(
            self.config_panel, text="Choose a configuration",
            font=ctk.CTkFont(size=25, weight="bold"), anchor="w"
        )
        self.config_title.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.form_area = ctk.CTkScrollableFrame(
            self.config_panel, fg_color="transparent", corner_radius=0
        )
        self.form_area.grid(row=2, column=0, sticky="nsew")
        self.form_area.grid_columnconfigure(0, weight=1)

        self.config_description = ctk.CTkLabel(
            self.form_area,
            text="Select a configuration from the middle panel.\nIts settings and controls will be displayed here.",
            text_color=("#687386", "#8995A8"), justify="left", anchor="nw",
            font=ctk.CTkFont(size=13), wraplength=520
        )
        self.config_description.pack(fill="x", anchor="w", pady=(2, 16))

        self.inputs_frame = ctk.CTkFrame(self.form_area, fg_color="transparent")
        self.inputs_frame.pack(fill="x", expand=True)
        self.inputs_frame.grid_columnconfigure(0, weight=1)

        self.config_execute_button = ctk.CTkButton(
            self.form_area, text="Execute configuration", height=40,
            corner_radius=9, command=self._execute_selected_config
        )
        self.config_execute_button.pack(fill="x", pady=(14, 12))
        self.config_execute_button.pack_forget()

        # Command terminal remains available at the bottom of the right panel.
        terminal = ctk.CTkFrame(self.config_panel, corner_radius=12, border_width=1, height=245)
        terminal.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        terminal.grid_columnconfigure(0, weight=1)
        terminal.grid_rowconfigure(1, weight=1)
        terminal.grid_propagate(False)
        term_header = ctk.CTkFrame(terminal, fg_color="transparent")
        term_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            term_header, text="Command terminal",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")
        self.output = ctk.CTkTextbox(
            terminal, wrap="word", font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.output.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.output.configure(state="disabled")
        command_row = ctk.CTkFrame(terminal, fg_color="transparent")
        command_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(3, 10))
        command_row.grid_columnconfigure(0, weight=1)
        self.command_entry = ctk.CTkEntry(
            command_row, placeholder_text="Type a device command…", height=36
        )
        self.command_entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.command_entry.bind("<Return>", lambda _event: self._submit_command())
        self.run_button = ctk.CTkButton(
            command_row, text="Run", width=68, height=36, command=self._submit_command
        )
        self.run_button.grid(row=0, column=1)

    def _sidebar_section(self, title):
        ctk.CTkLabel(
            self.sidebar, text=title, anchor="w",
            text_color=("#687386", "#8995A8"),
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(fill="x", padx=18, pady=(0, 4))

    def _sidebar_detail(self, label, initial, attribute):
        ctk.CTkLabel(
            self.sidebar, text=label, anchor="w",
            text_color=("#687386", "#8995A8"), font=ctk.CTkFont(size=10)
        ).pack(fill="x", padx=18, pady=(5, 0))
        value = ctk.CTkLabel(
            self.sidebar, text=initial, anchor="w", wraplength=165,
            font=ctk.CTkFont(size=12)
        )
        value.pack(fill="x", padx=18, pady=(0, 4))
        setattr(self, attribute, value)

    def load(self, payload):
        self.device_client = payload.get("client")
        self.interfaces = []
        self.device_name_label.configure(text=payload.get("brand", "Unknown"))
        self.connection_value.configure(text=payload["protocol"])
        self.username_value.configure(text=payload.get("username", "—"))
        self.host_value.configure(text=payload["host"])
        self.model_value.configure(text=payload.get("model", "Model not identified"))
        self.connection_badge.configure(text="● Connected")
        self.append_text(
            f"Connected to {payload['host']} using {payload['protocol']}.\n"
            f"{payload['info']}\n\nReady for commands.\n"
        )
        self.config_title.configure(text=f"{payload.get('brand', 'Device')} workspace")
        self.current_vendor = payload.get("brand", "").strip()
        self._load_vendor_configs()
        self.command_entry.focus_set()

    def _clear_options(self):
        for widget in self.options_list.winfo_children():
            widget.destroy()

    def _load_vendor_configs(self):
        self._clear_options()
        try:
            configs = self.config_manager.get_configs(self.current_vendor)
        except (FileNotFoundError, OSError, ValueError) as exc:
            configs = []
            self.empty_options = ctk.CTkLabel(
                self.options_list, text=f"Could not load configurations:\n{exc}",
                justify="left", anchor="w", wraplength=175,
                text_color=("#B42318", "#FF8B82")
            )
            self.empty_options.pack(fill="x", padx=8, pady=12)
            return

        if not configs:
            self.empty_options = ctk.CTkLabel(
                self.options_list, text=f"No configurations found for {self.current_vendor}.",
                justify="left", anchor="w", wraplength=175,
                text_color=("#687386", "#8995A8")
            )
            self.empty_options.pack(fill="x", padx=8, pady=12)
            return

        for item in configs:
            button = ctk.CTkButton(
                self.options_list, text=item.get("name", item["id"]),
                anchor="w", height=38, corner_radius=8,
                fg_color="transparent", border_width=1,
                text_color=("#202938", "#E7ECF5"),
                command=lambda config_id=item["id"]: self._select_config(config_id)
            )
            button.pack(fill="x", padx=4, pady=4)

    def _clear_form(self):
        for widget in self.inputs_frame.winfo_children():
            widget.destroy()
        self.input_widgets.clear()
        self.config_execute_button.pack_forget()

    def _get_device_interfaces(self):
        """Read interface names from the connected device."""
        if self.interfaces:
            return self.interfaces

        if not self.device_client:
            return []

        vendor = self.current_vendor.lower()
        try:
            if "mikrotik" in vendor:
                # RouterOS terse output contains name=<interface> fields.
                output = self.device_client.command("/interface/print terse") or ""
                names = re.findall(r"(?:^|\s)name=([^\s]+)", str(output), re.MULTILINE)

                # Fallback for devices/versions that do not return terse output.
                if not names:
                    output = self.device_client.command("/interface/print") or ""
                    for line in str(output).splitlines():
                        match = re.match(r"^\s*\d+\s+(?:[A-Z]+\s+)?([^\s]+)\s+", line)
                        if match:
                            names.append(match.group(1))

            elif "cisco" in vendor:
                output = self.device_client.command("show interfaces status") or ""
                names = []
                for line in str(output).splitlines():
                    line = line.strip()
                    if not line or line.lower().startswith(("port ", "----")):
                        continue
                    first = line.split()[0]
                    if re.match(
                        r"^(?:Gi|GigabitEthernet|Fa|FastEthernet|Te|TenGigabitEthernet|"
                        r"Eth|Ethernet|Po|Port-channel|Hu|HundredGigE)",
                        first,
                        re.IGNORECASE,
                    ):
                        names.append(first)
            else:
                names = []

            # Keep order while removing duplicates and empty values.
            self.interfaces = list(dict.fromkeys(name.strip() for name in names if name.strip()))
            return self.interfaces

        except Exception as exc:
            messagebox.showwarning(
                "Interface list unavailable",
                f"Could not retrieve interfaces from the device.\n\n{exc}",
                parent=self,
            )
            return []

    def _select_config(self, config_id):
        try:
            config = self.config_manager.load_config(self.current_vendor, config_id)
        except (FileNotFoundError, ValueError, OSError) as exc:
            messagebox.showerror("Configuration error", str(exc), parent=self)
            return

        self.selected_config = config
        self._clear_form()
        self.config_title.configure(text=config.get("name", config_id))
        self.config_description.configure(
            text=config.get("description", "No description available."),
            wraplength=520
        )

        for row, field in enumerate(config.get("inputs", [])):
            name = field["name"]
            label = field.get("label", name.replace("_", " ").title())
            required = field.get("required", True)
            label_text = f"{label}{' *' if required else ''}"

            ctk.CTkLabel(
                self.inputs_frame, text=label_text, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=row * 2, column=0, sticky="w", padx=2, pady=(10, 4))

            choices = field.get("choices")
            default = field.get("default")
            field_type = field.get("type")

            if field_type == "interface":
                interfaces = self._get_device_interfaces()
                if interfaces:
                    widget = ctk.CTkOptionMenu(
                        self.inputs_frame, values=interfaces,
                        height=36, corner_radius=8
                    )
                    if default in interfaces:
                        widget.set(str(default))
                else:
                    widget = ctk.CTkLabel(
                        self.inputs_frame,
                        text="No interfaces found. Check device access or command output.",
                        anchor="w",
                        text_color=("#B42318", "#FF8B82"),
                    )
                    # A label is not a valid input; the validation below prevents execution.
                    self.input_widgets[name] = widget
                    continue
            elif choices:
                widget = ctk.CTkOptionMenu(
                    self.inputs_frame, values=[str(choice) for choice in choices],
                    height=36, corner_radius=8
                )
                if default is not None:
                    widget.set(str(default))
            else:
                placeholder = f"Enter {label.lower()}"
                if field_type == "integer":
                    placeholder = "Enter a number"
                widget = ctk.CTkEntry(
                    self.inputs_frame, height=36, corner_radius=8,
                    placeholder_text=placeholder
                )
                if default is not None:
                    widget.insert(0, str(default))

            widget.grid(row=row * 2 + 1, column=0, sticky="ew", padx=2, pady=(0, 3))
            self.input_widgets[name] = widget

        self.config_execute_button.pack(fill="x", pady=(16, 12))

        # A long form may have been scrolled down. Return to the top whenever
        # a new configuration is selected so short forms are immediately visible.
        self.after_idle(self._scroll_form_to_top)

    def _scroll_form_to_top(self):
        try:
            self.update_idletasks()
            self.form_area._parent_canvas.yview_moveto(0)
        except (AttributeError, tk.TclError):
            pass

    def _execute_selected_config(self):
        if not self.selected_config:
            return

        values = {}
        for name, widget in self.input_widgets.items():
            if isinstance(widget, ctk.CTkLabel):
                messagebox.showwarning(
                    "Missing interface",
                    "The interface list is unavailable. Refresh the connection or check device permissions.",
                    parent=self,
                )
                return
            if isinstance(widget, ctk.CTkOptionMenu):
                values[name] = widget.get()
            else:
                values[name] = widget.get().strip()

        try:
            commands = self.config_manager.build_commands(self.selected_config, values)
            if not commands:
                raise ValueError("This configuration does not contain any commands.")
        except (KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        preview = "\n".join(commands)
        confirmed = messagebox.askyesno(
            "Confirm configuration",
            "The following commands will be sent to the connected device:\n\n"
            f"{preview}\n\nDo you want to continue?",
            parent=self
        )
        if confirmed:
            self.on_execute_config(commands)

    def _submit_command(self):
        command = self.command_entry.get().strip()
        if command:
            self.command_entry.delete(0, "end")
            self.on_command(command)

    def append_result(self, command, result):
        self.append_text(f"\n$ {command}\n{result}\n")

    def append_text(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def set_busy(self, busy):
        self.run_button.configure(
            state="disabled" if busy else "normal",
            text="…" if busy else "Run"
        )
        self.config_execute_button.configure(
            state="disabled" if busy else "normal",
            text="Executing…" if busy else "Execute configuration"
        )

    def clear_terminal(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def reset(self):
        self.clear_terminal()
        self.device_name_label.configure(text="Unknown device")
        self.connection_value.configure(text="—")
        self.username_value.configure(text="—")
        self.host_value.configure(text="—")
        self.model_value.configure(text="—")
        self.config_title.configure(text="Choose a configuration")
        self.config_description.configure(
            text="Select a configuration from the middle panel.\n"
                 "Its settings and controls will be displayed here."
        )
        self.current_vendor = ""
        self.selected_config = None
        self._clear_form()
        self._clear_options()
        self.empty_options = ctk.CTkLabel(
            self.options_list, text="Connect to a supported device\nto load its configurations.",
            justify="left", anchor="w", wraplength=175,
            text_color=("#687386", "#8995A8")
        )
        self.empty_options.pack(fill="x", padx=8, pady=12)

    def focus_command(self):
        self.command_entry.focus_set()


if __name__ == "__main__":
    app = SecondMindApp()
    app.mainloop()
