from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from command_run import DEFAULT_OUTPUT_DIR, configure_logging, run_inventory

COLOR_BG = "#071226"
COLOR_CARD = "#101b31"
COLOR_ACCENT = "#0072bc"
COLOR_TEXT = "#f4f7fb"
COLOR_MUTED = "#aab6c8"
DATA_FILETYPES = (("CSV/Excel files", "*.csv *.xlsx *.xls *.xlsm"), ("All files", "*.*"))
logger = logging.getLogger("NetworkAutomation")


class OutputExtractorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Log Capture - Device Command Collector")
        self.configure(bg=COLOR_BG)
        self.minsize(980, 560)

        self.devices_path: Path | None = None
        self.commands_path: Path | None = None
        self.output_dir: Path = DEFAULT_OUTPUT_DIR

        self.devices_var = tk.StringVar(value="No devices file selected")
        self.commands_var = tk.StringVar(value="No commands file selected")
        self.output_var = tk.StringVar(value=str(self.output_dir))
        self.status_var = tk.StringVar(value="Select the two input files to begin.")
        self.workers_var = tk.StringVar(value="1")
        self.timeout_var = tk.StringVar(value="30")
        self.read_timeout_var = tk.StringVar(value="60")
        self.dry_run_var = tk.BooleanVar(value=False)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui()
        configure_logging(self.output_dir / "logs")

    def _build_ui(self) -> None:
        wrapper = tk.Frame(self, bg=COLOR_BG)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=22, pady=22)
        wrapper.columnconfigure(0, weight=1)

        header = tk.Frame(wrapper, bg=COLOR_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        tk.Label(header, text="Log Capture", font=("Segoe UI", 24, "bold"), fg=COLOR_TEXT, bg=COLOR_BG).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Run approved commands on network devices and save timestamped output files.",
            font=("Segoe UI", 11),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        guide = tk.Frame(wrapper, bg=COLOR_CARD, padx=16, pady=14)
        guide.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        guide.columnconfigure((0, 1, 2, 3), weight=1)
        for index, text in enumerate(["1. Select devices", "2. Select commands", "3. Choose output", "4. Start run"]):
            tk.Label(guide, text=text, fg=COLOR_TEXT, bg=COLOR_CARD, font=("Segoe UI", 10, "bold")).grid(row=0, column=index, sticky="w", padx=8)

        form = tk.Frame(wrapper, bg=COLOR_BG)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        self._add_file_row(form, 0, "Devices file", self.devices_var, self._choose_devices)
        self._add_file_row(form, 1, "Commands file", self.commands_var, self._choose_commands)
        self._add_file_row(form, 2, "Output folder", self.output_var, self._choose_output_dir, folder=True)

        options = tk.Frame(wrapper, bg=COLOR_CARD, padx=16, pady=14)
        options.grid(row=3, column=0, sticky="ew", pady=16)
        for col in range(4):
            options.columnconfigure(col, weight=1)
        self._add_option(options, 0, "Workers", self.workers_var)
        self._add_option(options, 1, "Connect timeout", self.timeout_var)
        self._add_option(options, 2, "Command timeout", self.read_timeout_var)
        tk.Checkbutton(
            options,
            text="Dry run only",
            variable=self.dry_run_var,
            fg=COLOR_TEXT,
            bg=COLOR_CARD,
            selectcolor=COLOR_BG,
            activebackground=COLOR_CARD,
            activeforeground=COLOR_TEXT,
        ).grid(row=0, column=3, sticky="w", padx=8)

        actions = tk.Frame(wrapper, bg=COLOR_BG)
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        tk.Label(actions, textvariable=self.status_var, fg=COLOR_MUTED, bg=COLOR_BG).grid(row=0, column=0, sticky="w")
        self.start_btn = tk.Button(
            actions,
            text="Start capture",
            command=self.on_start,
            fg=COLOR_TEXT,
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT,
            activeforeground=COLOR_TEXT,
            relief="flat",
            padx=22,
            pady=12,
            state="disabled",
        )
        self.start_btn.grid(row=0, column=1, sticky="e")

    def _add_file_row(self, parent, row: int, label: str, variable: tk.StringVar, callback, folder: bool = False) -> None:
        tk.Label(parent, text=label, fg=COLOR_TEXT, bg=COLOR_BG, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=8)
        tk.Label(parent, textvariable=variable, fg=COLOR_TEXT, bg=COLOR_CARD, anchor="w", padx=10, pady=10).grid(row=row, column=1, sticky="ew", pady=8, padx=10)
        tk.Button(parent, text="Browse folder" if folder else "Browse file", command=callback, fg=COLOR_TEXT, bg=COLOR_ACCENT, relief="flat", padx=12, pady=8).grid(row=row, column=2, sticky="e", pady=8)

    def _add_option(self, parent, column: int, label: str, variable: tk.StringVar) -> None:
        box = tk.Frame(parent, bg=COLOR_CARD)
        box.grid(row=0, column=column, sticky="ew", padx=8)
        tk.Label(box, text=label, fg=COLOR_MUTED, bg=COLOR_CARD).grid(row=0, column=0, sticky="w")
        tk.Entry(box, textvariable=variable, width=10).grid(row=1, column=0, sticky="ew", pady=(4, 0))

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
        ready = bool(self.devices_path and self.commands_path)
        self.start_btn.config(state="normal" if ready else "disabled")
        if ready:
            self.status_var.set("Ready. Review options, then start capture.")

    def _number(self, value: str, fallback: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except ValueError:
            return fallback

    def on_start(self) -> None:
        if not (self.devices_path and self.commands_path):
            messagebox.showwarning("Missing files", "Select both a devices file and a commands file.")
            return

        self.start_btn.config(state="disabled")
        self.status_var.set("Running. Do not close this window.")
        workers = self._number(self.workers_var.get(), 1, 1, 20)
        timeout = self._number(self.timeout_var.get(), 30, 5, 300)
        read_timeout = self._number(self.read_timeout_var.get(), 60, 5, 600)

        def worker() -> None:
            try:
                summary = run_inventory(
                    self.devices_path,
                    self.commands_path,
                    self.output_dir,
                    workers=workers,
                    timeout=timeout,
                    read_timeout=read_timeout,
                    dry_run=self.dry_run_var.get(),
                )
                msg = (
                    f"Processed: {summary['total']}\n"
                    f"Successful: {summary['successful']}\n"
                    f"Failed: {summary['failed']}\n"
                    f"Success rate: {summary['success_rate']}%\n"
                    f"CSV report: {summary['csv_report']}\n"
                    f"Output: {summary['output_dir']}"
                )
                self.after(0, lambda message=msg: messagebox.showinfo("Capture completed", message))
                self.after(0, lambda: self.status_var.set("Completed. Review the output folder and reports."))
            except Exception as error:
                logger.exception("Automation run failed")
                message = str(error)
                self.after(0, lambda message=message: messagebox.showerror("Capture failed", message))
                self.after(0, lambda: self.status_var.set("Failed. Check the error message and logs."))
            finally:
                self.after(0, lambda: self.start_btn.config(state="normal" if self.devices_path and self.commands_path else "disabled"))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = OutputExtractorApp()
    app.mainloop()
