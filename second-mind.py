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
            self.container, self.run_command, self.disconnect, self.toggle_theme
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

    def __init__(self, master, on_command, on_disconnect, toggle_theme):
        super().__init__(master, corner_radius=0)
        self.on_command = on_command
        self.on_disconnect = on_disconnect

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
            text="Device-specific options\nwill appear here later.",
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
        self.config_description = ctk.CTkLabel(
            self.config_panel,
            text="Select a device tool from the middle panel.\nIts settings and controls will be displayed here.",
            text_color=("#687386", "#8995A8"), justify="left", anchor="nw",
            font=ctk.CTkFont(size=13)
        )
        self.config_description.grid(row=2, column=0, sticky="new")

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
        self.config_description.configure(
            text="The device-specific option list is intentionally empty for now.\n"
                 "We'll decide how options and their configuration forms work next."
        )
        self.command_entry.focus_set()

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
            text="Select a device tool from the middle panel.\n"
                 "Its settings and controls will be displayed here."
        )

    def focus_command(self):
        self.command_entry.focus_set()


if __name__ == "__main__":
    app = SecondMindApp()
    app.mainloop()
