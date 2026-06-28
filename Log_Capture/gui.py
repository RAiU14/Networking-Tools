"""Tkinter GUI for Log_Capture."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from command_run import DEFAULT_OUTPUT_DIR, configure_logging, run_inventory

COLOR_BG_PRIMARY = "#070f26"
COLOR_BG_SECONDARY = "#1f2a3a"
COLOR_ACCENT = "#0072bc"
COLOR_TEXT = "#d4d5d6"
DATA_FILETYPES = (("CSV/Excel files", "*.csv *.xlsx *.xls *.xlsm"), ("All files", "*.*"))
logger = logging.getLogger("NetworkAutomation")


class OutputExtractorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Network Automation: Output Extractor")
        self.configure(bg=COLOR_BG_PRIMARY)
        self.minsize(900, 420)

        self.devices_path: Path | None = None
        self.commands_path: Path | None = None
        self.output_dir: Path = DEFAULT_OUTPUT_DIR

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui()
        configure_logging(self.output_dir / "logs")

    def _build_ui(self) -> None:
        wrapper = tk.Frame(self, bg=COLOR_BG_PRIMARY)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        wrapper.columnconfigure(1, weight=1)

        title = tk.Label(
            wrapper,
            text="Network Automation: Output Extractor",
            font=("Segoe UI", 18, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG_PRIMARY,
        )
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self.devices_var = tk.StringVar(value="No file selected")
        self.commands_var = tk.StringVar(value="No file selected")
        self.output_var = tk.StringVar(value=str(self.output_dir))

        self._add_file_row(wrapper, 1, "Devices file", self.devices_var, self._choose_devices)
        self._add_file_row(wrapper, 2, "Commands file", self.commands_var, self._choose_commands)
        self._add_file_row(wrapper, 3, "Output folder", self.output_var, self._choose_output_dir, folder=True)

        self.start_btn = tk.Button(
            wrapper,
            text="Start",
            command=self.on_start,
            fg=COLOR_TEXT,
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT,
            activeforeground=COLOR_TEXT,
            relief="flat",
            padx=18,
            pady=10,
            state="disabled",
        )
        self.start_btn.grid(row=4, column=2, sticky="e", pady=(18, 0))

    def _add_file_row(self, parent, row: int, label: str, variable: tk.StringVar, callback, folder: bool = False) -> None:
        tk.Label(parent, text=label + ":", fg=COLOR_TEXT, bg=COLOR_BG_PRIMARY).grid(row=row, column=0, sticky="w", pady=8)
        tk.Label(parent, textvariable=variable, fg=COLOR_TEXT, bg=COLOR_BG_SECONDARY, anchor="w", padx=8).grid(
            row=row, column=1, sticky="ew", pady=8, padx=8
        )
        tk.Button(
            parent,
            text="Choose Folder" if folder else "Choose File",
            command=callback,
            fg=COLOR_TEXT,
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT,
            activeforeground=COLOR_TEXT,
            relief="flat",
            padx=10,
            pady=6,
        ).grid(row=row, column=2, sticky="e", pady=8)

    def _choose_devices(self) -> None:
        path = filedialog.askopenfilename(title="Select devices file", filetypes=DATA_FILETYPES)
        if path:
            self.devices_path = Path(path)
            self.devices_var.set(str(self.devices_path))
            self._refresh_start_button()

    def _choose_commands(self) -> None:
        path = filedialog.askopenfilename(title="Select commands file", filetypes=DATA_FILETYPES)
        if path:
            self.commands_path = Path(path)
            self.commands_var.set(str(self.commands_path))
            self._refresh_start_button()

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir = Path(path)
            self.output_var.set(str(self.output_dir))
            configure_logging(self.output_dir / "logs")

    def _refresh_start_button(self) -> None:
        self.start_btn.config(state="normal" if self.devices_path and self.commands_path else "disabled")

    def on_start(self) -> None:
        if not (self.devices_path and self.commands_path):
            messagebox.showwarning("Missing files", "Please select both a devices file and a commands file.")
            return

        self.start_btn.config(state="disabled")

        def worker() -> None:
            try:
                summary = run_inventory(self.devices_path, self.commands_path, self.output_dir)
                msg = (
                    f"Processed: {summary['total']}\n"
                    f"Successful: {summary['successful']}\n"
                    f"Failed: {summary['failed']}\n"
                    f"Output: {summary['output_dir']}"
                )
                self.after(0, lambda: messagebox.showinfo("Completed", msg))
            except Exception as exc:
                logger.exception("Automation run failed")
                self.after(0, lambda: messagebox.showerror("Failed", str(exc)))
            finally:
                self.after(0, self._refresh_start_button)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = OutputExtractorApp()
    app.mainloop()
