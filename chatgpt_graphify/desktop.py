"""Small cross-platform desktop launcher for chatgpt-graphify."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class GraphifyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ChatGPT Graphify")
        self.root.geometry("760x560")
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self.folder = tk.StringVar()
        self.api_key = tk.StringVar()
        self.deep = tk.BooleanVar()
        self.no_viz = tk.BooleanVar()
        self.svg = tk.BooleanVar()
        self.status = tk.StringVar(value="Choose a folder to analyze.")

        self._build_ui()
        self.root.after(100, self._drain_output)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Folder to analyze").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.folder).grid(row=0, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(frame, text="Browse…", command=self._browse).grid(row=0, column=2, pady=5)

        ttk.Label(frame, text="OpenAI API key (optional)").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.api_key, show="•").grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=5)

        options = ttk.Frame(frame)
        options.grid(row=2, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Checkbutton(options, text="Deep analysis", variable=self.deep).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Checkbutton(options, text="Skip visualizations", variable=self.no_viz).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Checkbutton(options, text="Export SVG", variable=self.svg).pack(side=tk.LEFT)

        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        self.run_button = ttk.Button(controls, text="Analyze folder", command=self._run)
        self.run_button.pack(side=tk.LEFT)
        self.open_button = ttk.Button(controls, text="Open output folder", command=self._open_output, state=tk.DISABLED)
        self.open_button.pack(side=tk.LEFT, padx=8)
        ttk.Label(frame, textvariable=self.status).grid(row=4, column=0, columnspan=3, sticky="w", pady=5)

        self.output = tk.Text(frame, wrap=tk.WORD, state=tk.DISABLED)
        self.output.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.output.yview)
        scrollbar.grid(row=5, column=3, sticky="ns", pady=(8, 0))
        self.output.configure(yscrollcommand=scrollbar.set)

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="Choose a folder to analyze")
        if selected:
            self.folder.set(selected)

    def _write(self, text: str) -> None:
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _run(self) -> None:
        folder = Path(self.folder.get()).expanduser()
        if not folder.is_dir():
            messagebox.showerror("Choose a folder", "Select an existing folder before starting.")
            return

        command = [sys.executable, "-m", "chatgpt_graphify", str(folder)]
        if self.deep.get():
            command.append("--deep")
        if self.no_viz.get():
            command.append("--no-viz")
        if self.svg.get():
            command.append("--svg")

        environment = os.environ.copy()
        if self.api_key.get().strip():
            environment["OPENAI_API_KEY"] = self.api_key.get().strip()

        self.run_button.configure(state=tk.DISABLED)
        self.open_button.configure(state=tk.DISABLED)
        self.status.set("Analyzing…")
        self._write("$ " + " ".join(command) + "\n\n")
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=environment,
        )
        threading.Thread(target=self._read_process, daemon=True).start()

    def _read_process(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(line)
        code = self.process.wait()
        self.output_queue.put(f"\nFinished with exit code {code}.\n")
        self.output_queue.put(f"__DONE__:{code}\n")

    def _drain_output(self) -> None:
        try:
            while True:
                line = self.output_queue.get_nowait()
                if line.startswith("__DONE__:"):
                    code = line.rstrip().split(":", 1)[1]
                    self.run_button.configure(state=tk.NORMAL)
                    self.open_button.configure(state=tk.NORMAL if code == "0" else tk.DISABLED)
                    self.status.set("Complete. Results are in graphify-out." if code == "0" else "The run failed. See the output above.")
                else:
                    self._write(line)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_output)

    def _open_output(self) -> None:
        output = Path(self.folder.get()).expanduser() / "graphify-out"
        if not output.is_dir():
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(output)])
        elif os.name == "nt":
            os.startfile(str(output))
        else:
            subprocess.Popen(["xdg-open", str(output)])


def main() -> None:
    root = tk.Tk()
    GraphifyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
