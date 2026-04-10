#!/usr/bin/env python3
"""
BigFile Reader - Read and search very large files (10 GB+)
Uses mmap-based memory-efficient file access
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mmap
import os
import threading
import re
import time
from pathlib import Path


CHUNK_SIZE = 512 * 1024          # Display block: 512 KB
SEARCH_BUFFER = 4 * 1024 * 1024  # Search buffer: 4 MB
MAX_RESULTS = 5000               # Maximum search results

# Catppuccin Mocha palette
C = {
    "base":     "#1e1e2e",
    "mantle":   "#181825",
    "crust":    "#11111b",
    "surface0": "#313244",
    "surface1": "#45475a",
    "surface2": "#585b70",
    "overlay0": "#6c7086",
    "subtext0": "#a6adc8",
    "text":     "#cdd6f4",
    "lavender": "#b4befe",
    "mauve":    "#cba6f7",
    "sapphire": "#74c7ec",
    "green":    "#a6e3a1",
    "yellow":   "#f9e2af",
    "red":      "#f38ba8",
    "peach":    "#fab387",
    "accent":   "#7c3aed",
    "accent2":  "#6d28d9",
}


def detect_encoding(filepath: str, sample: int = 65536) -> str:
    with open(filepath, "rb") as f:
        raw = f.read(sample)
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class BigFileReader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BigFile Reader")
        self.geometry("1280x800")
        self.minsize(860, 520)
        self.configure(bg=C["base"])

        # File state
        self.filepath: str | None = None
        self.filesize: int = 0
        self.encoding: str = "utf-8"
        self._mmap: mmap.mmap | None = None
        self._file = None
        self.current_offset: int = 0
        self.font_size: int = 12

        # Search state
        self.search_results: list[int] = []
        self.search_index: int = -1
        self._search_thread: threading.Thread | None = None
        self._search_cancel = threading.Event()

        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================== UI ==

    def _build_ui(self):
        self._setup_styles()
        self._build_menu()
        self._build_toolbar()
        self._build_search_bar()
        self._build_text_area()
        self._build_status_bar()

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("TFrame",     background=C["base"])
        s.configure("TLabel",     background=C["base"], foreground=C["text"],
                    font=("Helvetica Neue", 11))
        s.configure("Dim.TLabel", background=C["base"], foreground=C["overlay0"],
                    font=("Menlo", 10))

        s.configure("TButton",
                    background=C["surface0"], foreground=C["text"],
                    relief="flat", padding=(10, 5),
                    font=("Helvetica Neue", 11))
        s.map("TButton",
              background=[("active", C["surface1"])],
              foreground=[("active", C["mauve"])])

        s.configure("Accent.TButton",
                    background=C["accent"], foreground="white",
                    relief="flat", padding=(10, 5),
                    font=("Helvetica Neue", 11, "bold"))
        s.map("Accent.TButton",
              background=[("active", C["accent2"])])

        s.configure("Nav.TButton",
                    background=C["crust"], foreground=C["subtext0"],
                    relief="flat", padding=(8, 3),
                    font=("Menlo", 11))
        s.map("Nav.TButton",
              background=[("active", C["surface0"])],
              foreground=[("active", C["lavender"])])

        s.configure("Sm.TButton",
                    background=C["surface0"], foreground=C["text"],
                    relief="flat", padding=(5, 2),
                    font=("Helvetica Neue", 10))
        s.map("Sm.TButton",
              background=[("active", C["surface1"])])

        s.configure("TEntry",
                    fieldbackground=C["surface0"],
                    foreground=C["text"],
                    insertcolor=C["mauve"],
                    relief="flat", padding=(6, 4))

        s.configure("Search.TCheckbutton",
                    background=C["mantle"], foreground=C["subtext0"],
                    font=("Helvetica Neue", 10))
        s.map("Search.TCheckbutton",
              background=[("active", C["mantle"])],
              foreground=[("active", C["text"])])

        s.configure("Horizontal.TProgressbar",
                    troughcolor=C["surface0"],
                    background=C["accent"],
                    thickness=3)

        for orient in ("Vertical", "Horizontal"):
            s.configure(f"{orient}.TScrollbar",
                        background=C["surface0"],
                        troughcolor=C["mantle"],
                        arrowcolor=C["overlay0"],
                        relief="flat", arrowsize=12)

    def _build_menu(self):
        def menu(**kw):
            return tk.Menu(bg=C["surface0"], fg=C["text"],
                           activebackground=C["accent"], activeforeground="white",
                           relief="flat", bd=0, tearoff=0, **kw)

        bar = tk.Menu(self, bg=C["mantle"], fg=C["text"],
                      activebackground=C["accent"], activeforeground="white",
                      relief="flat", bd=0)

        # File
        m = menu()
        m.add_command(label="Open File…         Ctrl+O", command=self._open_file)
        m.add_separator()
        m.add_command(label="Exit               Alt+F4", command=self._on_close)
        bar.add_cascade(label="File", menu=m)

        # Navigate
        m = menu()
        m.add_command(label="Go to Start      Ctrl+Home", command=self._go_start)
        m.add_command(label="Go to End         Ctrl+End", command=self._go_end)
        m.add_separator()
        m.add_command(label="Previous Block     Page Up", command=self._prev_chunk)
        m.add_command(label="Next Block       Page Down", command=self._next_chunk)
        m.add_separator()
        m.add_command(label="Go to Line/Byte…   Ctrl+G", command=self._focus_goto)
        bar.add_cascade(label="Navigate", menu=m)

        # Search
        m = menu()
        m.add_command(label="Find…              Ctrl+F", command=self._focus_search)
        m.add_command(label="Next Match             F3", command=self._next_result)
        m.add_command(label="Previous Match   Shift+F3", command=self._prev_result)
        m.add_command(label="Cancel Search      Escape", command=self._cancel_search)
        bar.add_cascade(label="Search", menu=m)

        # View
        m = menu()
        m.add_command(label="Increase Font Size  Ctrl++", command=self._font_increase)
        m.add_command(label="Decrease Font Size  Ctrl+-", command=self._font_decrease)
        m.add_command(label="Reset Font Size     Ctrl+0", command=self._font_reset)
        bar.add_cascade(label="View", menu=m)

        self.config(menu=bar)

    def _build_toolbar(self):
        toolbar = tk.Frame(self, bg=C["mantle"], height=50)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        def sep():
            tk.Frame(toolbar, bg=C["surface0"], width=1).pack(
                side="left", fill="y", padx=10, pady=10)

        # Open File
        left = tk.Frame(toolbar, bg=C["mantle"])
        left.pack(side="left", padx=(14, 0), pady=8)
        ttk.Button(left, text="  Open File",
                   style="Accent.TButton",
                   command=self._open_file).pack(side="left")

        sep()

        # Go to line/byte
        goto_grp = tk.Frame(toolbar, bg=C["mantle"])
        goto_grp.pack(side="left", pady=8)
        tk.Label(goto_grp, text="Go to:", bg=C["mantle"],
                 fg=C["overlay0"], font=("Helvetica Neue", 11)).pack(side="left")
        self.goto_var = tk.StringVar()
        self.goto_entry = ttk.Entry(goto_grp, textvariable=self.goto_var, width=14)
        self.goto_entry.pack(side="left", padx=(6, 4))
        self.goto_entry.bind("<Return>", lambda _: self._goto())
        ttk.Button(goto_grp, text="Go", command=self._goto).pack(side="left")

        sep()

        # Font size
        font_grp = tk.Frame(toolbar, bg=C["mantle"])
        font_grp.pack(side="left", pady=8)
        tk.Label(font_grp, text="Font:", bg=C["mantle"],
                 fg=C["overlay0"], font=("Helvetica Neue", 11)).pack(side="left")
        ttk.Button(font_grp, text="−", style="Sm.TButton",
                   command=self._font_decrease).pack(side="left", padx=(6, 2))
        self.font_size_lbl = tk.Label(font_grp, text=str(self.font_size),
                                      bg=C["mantle"], fg=C["subtext0"],
                                      font=("Menlo", 10), width=3)
        self.font_size_lbl.pack(side="left")
        ttk.Button(font_grp, text="+", style="Sm.TButton",
                   command=self._font_increase).pack(side="left", padx=(2, 0))

        # File info (right-aligned)
        self.info_lbl = tk.Label(toolbar, text="No file open",
                                 bg=C["mantle"], fg=C["overlay0"],
                                 font=("Menlo", 10))
        self.info_lbl.pack(side="right", padx=16)

        tk.Frame(self, bg=C["surface0"], height=1).pack(fill="x")

    def _build_search_bar(self):
        bar = tk.Frame(self, bg=C["mantle"])
        bar.pack(fill="x")

        inner = tk.Frame(bar, bg=C["mantle"])
        inner.pack(fill="x", padx=14, pady=7)

        tk.Label(inner, text="Find:", bg=C["mantle"],
                 fg=C["overlay0"], font=("Helvetica Neue", 11)).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(inner, textvariable=self.search_var, width=36)
        self.search_entry.pack(side="left", padx=(6, 10))
        self.search_entry.bind("<Return>", lambda _: self._start_search())

        self.regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Regex", variable=self.regex_var,
                        style="Search.TCheckbutton").pack(side="left", padx=(0, 6))

        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(inner, text="Case sensitive", variable=self.case_var,
                        style="Search.TCheckbutton").pack(side="left", padx=(0, 12))

        ttk.Button(inner, text="▶  Search", style="Accent.TButton",
                   command=self._start_search).pack(side="left", padx=(0, 4))
        ttk.Button(inner, text="✕", style="Sm.TButton",
                   command=self._cancel_search).pack(side="left", padx=(0, 18))

        # Result navigation
        nav = tk.Frame(inner, bg=C["mantle"])
        nav.pack(side="left")
        ttk.Button(nav, text="◀", style="Nav.TButton",
                   command=self._prev_result).pack(side="left", padx=(0, 6))
        self.result_lbl = tk.Label(nav, text="—",
                                   bg=C["mantle"], fg=C["overlay0"],
                                   font=("Menlo", 10), width=16)
        self.result_lbl.pack(side="left")
        ttk.Button(nav, text="▶", style="Nav.TButton",
                   command=self._next_result).pack(side="left", padx=(6, 0))

        tk.Frame(self, bg=C["surface0"], height=1).pack(fill="x")

        # Progress bar
        prog_frame = tk.Frame(self, bg=C["base"])
        prog_frame.pack(fill="x")
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal",
                                        mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill="x")
        self.progress_lbl = ttk.Label(prog_frame, text="", style="Dim.TLabel")
        self.progress_lbl.pack(anchor="w", padx=14, pady=(2, 2))

        tk.Frame(self, bg=C["surface0"], height=1).pack(fill="x")

    def _build_text_area(self):
        outer = tk.Frame(self, bg=C["mantle"])
        outer.pack(fill="both", expand=True)

        # Line numbers gutter
        self.line_nums = tk.Text(
            outer,
            width=7,
            bg=C["crust"], fg=C["surface2"],
            font=("Menlo", self.font_size),
            state="disabled", relief="flat",
            cursor="arrow", wrap="none",
            selectbackground=C["crust"],
            takefocus=False,
        )
        self.line_nums.pack(side="left", fill="y")

        tk.Frame(outer, bg=C["surface0"], width=1).pack(side="left", fill="y")

        # Main text + scrollbars
        text_frame = tk.Frame(outer, bg=C["mantle"])
        text_frame.pack(side="left", fill="both", expand=True)

        self.vsb = ttk.Scrollbar(text_frame, orient="vertical")
        hsb = ttk.Scrollbar(text_frame, orient="horizontal")

        self.text = tk.Text(
            text_frame,
            bg=C["mantle"], fg=C["text"],
            font=("Menlo", self.font_size),
            insertbackground=C["mauve"],
            selectbackground=C["surface1"],
            selectforeground=C["text"],
            relief="flat", wrap="none",
            state="disabled",
            padx=14, pady=10,
            yscrollcommand=self._on_text_yscroll,
            xscrollcommand=hsb.set,
        )
        self.text.tag_configure("highlight",
                                background=C["yellow"], foreground=C["crust"])
        self.text.tag_configure("active_hl",
                                background=C["green"],  foreground=C["crust"])

        self.vsb.config(command=self.text.yview)
        hsb.config(command=self.text.xview)

        hsb.pack(side="bottom", fill="x")
        self.vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

    def _on_text_yscroll(self, first, last):
        self.vsb.set(first, last)
        self.line_nums.yview_moveto(float(first))

    def _build_status_bar(self):
        tk.Frame(self, bg=C["surface0"], height=1).pack(fill="x")

        bar = tk.Frame(self, bg=C["crust"], height=30)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        def vsep(parent):
            tk.Frame(parent, bg=C["surface0"], width=1).pack(
                side="left", fill="y", pady=5)

        left = tk.Frame(bar, bg=C["crust"])
        left.pack(side="left", fill="y")

        self.offset_lbl = tk.Label(left, text="Offset: —",
                                   bg=C["crust"], fg=C["overlay0"],
                                   font=("Menlo", 10), padx=12)
        self.offset_lbl.pack(side="left", fill="y")
        vsep(left)

        self.line_lbl = tk.Label(left, text="~Line: —",
                                 bg=C["crust"], fg=C["overlay0"],
                                 font=("Menlo", 10), padx=12)
        self.line_lbl.pack(side="left", fill="y")
        vsep(left)

        self.enc_lbl = tk.Label(left, text="—",
                                bg=C["crust"], fg=C["overlay0"],
                                font=("Menlo", 10), padx=12)
        self.enc_lbl.pack(side="left", fill="y")

        # Block navigation (right-aligned)
        nav = tk.Frame(bar, bg=C["crust"])
        nav.pack(side="right", fill="y", padx=10)

        for label, cmd in [
            ("◀◀", self._go_start),
            ("◀ Prev", self._prev_chunk),
            ("Next ▶", self._next_chunk),
            ("▶▶", self._go_end),
        ]:
            ttk.Button(nav, text=label, style="Nav.TButton",
                       command=cmd).pack(side="left", padx=2, pady=4)

    # ============================================================= Shortcuts ==

    def _bind_shortcuts(self):
        self.bind("<Control-o>",     lambda _: self._open_file())
        self.bind("<Control-f>",     lambda _: self._focus_search())
        self.bind("<Control-g>",     lambda _: self._focus_goto())
        self.bind("<F3>",            lambda _: self._next_result())
        self.bind("<Shift-F3>",      lambda _: self._prev_result())
        self.bind("<Escape>",        lambda _: self._cancel_search())
        self.bind("<Control-Home>",  lambda _: self._go_start())
        self.bind("<Control-End>",   lambda _: self._go_end())
        self.bind("<Prior>",         lambda _: self._prev_chunk())
        self.bind("<Next>",          lambda _: self._next_chunk())
        self.bind("<Control-equal>", lambda _: self._font_increase())
        self.bind("<Control-minus>", lambda _: self._font_decrease())
        self.bind("<Control-0>",     lambda _: self._font_reset())

    def _focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def _focus_goto(self):
        self.goto_entry.focus_set()
        self.goto_entry.select_range(0, "end")

    # ================================================================= Font ==

    def _font_increase(self):
        self.font_size = min(30, self.font_size + 1)
        self._apply_font()

    def _font_decrease(self):
        self.font_size = max(8, self.font_size - 1)
        self._apply_font()

    def _font_reset(self):
        self.font_size = 12
        self._apply_font()

    def _apply_font(self):
        font = ("Menlo", self.font_size)
        self.text.config(font=font)
        self.line_nums.config(font=font)
        self.font_size_lbl.config(text=str(self.font_size))
        if self._mmap:
            self._update_line_nums()

    # ================================================================= File ==

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open File",
            filetypes=[
                ("All files",   "*.*"),
                ("Text files",  "*.txt *.log *.csv *.json *.xml"),
                ("Backup files", "*.bak *.backup *.sql *.dump"),
            ]
        )
        if not path:
            return
        self._close_file()
        try:
            self.filepath = path
            self.filesize = os.path.getsize(path)
            self.encoding = detect_encoding(path)
            self._file = open(path, "rb")
            if self.filesize > 0:
                self._mmap = mmap.mmap(self._file.fileno(), 0,
                                       access=mmap.ACCESS_READ)
            self.current_offset = 0
            self.search_results.clear()
            self.search_index = -1
            self.result_lbl.config(text="—", fg=C["overlay0"])
            self.title(f"BigFile Reader — {Path(path).name}")
            self.info_lbl.config(
                text=f"{Path(path).name}   {human_size(self.filesize)}   {self.encoding}"
            )
            self.enc_lbl.config(text=self.encoding)
            self._load_chunk(0)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file:\n{e}")

    def _close_file(self):
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._file:
            self._file.close()
            self._file = None

    def _on_close(self):
        self._cancel_search()
        self._close_file()
        self.destroy()

    # ============================================================== Display ==

    def _load_chunk(self, offset: int):
        if not self._mmap or self.filesize == 0:
            return
        offset = max(0, min(offset, self.filesize - 1))
        self._mmap.seek(offset)
        raw = self._mmap.read(CHUNK_SIZE)
        text = raw.decode(self.encoding, errors="replace")

        self.current_offset = offset
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.config(state="disabled")

        self._update_line_nums()
        self._update_status(offset)

    def _update_line_nums(self):
        line_count = int(self.text.index("end-1c").split(".")[0])
        start = self._estimate_line(self.current_offset)
        content = "\n".join(str(start + i) for i in range(line_count))

        self.line_nums.config(state="normal")
        self.line_nums.delete("1.0", "end")
        self.line_nums.insert("1.0", content)
        self.line_nums.config(state="disabled")

    def _update_status(self, offset: int):
        self.offset_lbl.config(text=f"Offset: {offset:,} / {self.filesize:,}")
        approx_line = self._estimate_line(offset)
        self.line_lbl.config(text=f"~Line: {approx_line:,}")
        self.progress["value"] = (offset / self.filesize) * 100 if self.filesize else 0
        self.progress_lbl.config(
            text=f"{human_size(offset)} / {human_size(self.filesize)}"
        )

    def _estimate_line(self, offset: int) -> int:
        if not self._mmap or offset == 0:
            return 1
        sample_step = max(1, offset // 200)
        count = 0
        for i in range(0, offset, sample_step):
            end = min(i + sample_step, offset)
            count += self._mmap[i:end].count(b"\n")
        return count + 1

    def _go_start(self):   self._load_chunk(0)
    def _go_end(self):     self._load_chunk(max(0, self.filesize - CHUNK_SIZE))
    def _next_chunk(self): self._load_chunk(self.current_offset + CHUNK_SIZE)
    def _prev_chunk(self): self._load_chunk(self.current_offset - CHUNK_SIZE)

    def _goto(self):
        val = self.goto_var.get().strip()
        if not val or not self._mmap:
            return
        try:
            n = int(val)
        except ValueError:
            messagebox.showwarning("Warning", "Enter a valid number.")
            return
        if n < self.filesize:
            self._load_chunk(n)
        else:
            self._goto_line(n)

    def _goto_line(self, target_line: int):
        if not self._mmap:
            return
        self.progress_lbl.config(text=f"Seeking line {target_line:,}…")
        self.update_idletasks()

        offset = 0
        line = 1
        step = SEARCH_BUFFER
        self._mmap.seek(0)
        while offset < self.filesize:
            buf = self._mmap.read(step)
            if not buf:
                break
            nl_count = buf.count(b"\n")
            if line + nl_count >= target_line:
                pos = 0
                while line < target_line:
                    idx = buf.find(b"\n", pos)
                    if idx == -1:
                        break
                    pos = idx + 1
                    line += 1
                self._load_chunk(offset + pos)
                return
            line += nl_count
            offset += len(buf)
        self._load_chunk(max(0, self.filesize - CHUNK_SIZE))

    # ================================================================ Search ==

    def _start_search(self):
        query = self.search_var.get()
        if not query or not self._mmap:
            return
        self._cancel_search()
        self._search_cancel.clear()
        self.search_results.clear()
        self.search_index = -1
        self.result_lbl.config(text="Searching…", fg=C["peach"])
        self._clear_highlights()

        self._search_thread = threading.Thread(
            target=self._search_worker,
            args=(query, self.regex_var.get(), self.case_var.get()),
            daemon=True,
        )
        self._search_thread.start()

    def _cancel_search(self):
        self._search_cancel.set()
        if self._search_thread and self._search_thread.is_alive():
            self._search_thread.join(timeout=1)

    def _search_worker(self, query: str, use_regex: bool, case_sensitive: bool):
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            if use_regex:
                pattern = re.compile(
                    query.encode(self.encoding, errors="replace"), flags)
            else:
                needle = query.encode(self.encoding, errors="replace")
                needle_lower = needle.lower()

            results = []
            offset = 0
            t0 = time.time()

            while offset < self.filesize and not self._search_cancel.is_set():
                buf = self._mmap[offset: offset + SEARCH_BUFFER]
                if not buf:
                    break

                if use_regex:
                    for m in pattern.finditer(buf):
                        results.append(offset + m.start())
                        if len(results) >= MAX_RESULTS:
                            break
                else:
                    search_buf = buf.lower() if not case_sensitive else buf
                    pos = 0
                    while True:
                        idx = search_buf.find(
                            needle_lower if not case_sensitive else needle, pos)
                        if idx == -1:
                            break
                        results.append(offset + idx)
                        pos = idx + 1
                        if len(results) >= MAX_RESULTS:
                            break

                offset += SEARCH_BUFFER - len(query.encode()) - 1
                pct = (offset / self.filesize) * 100
                elapsed = time.time() - t0
                self.after(0, self._update_search_progress, pct, len(results), elapsed)

                if len(results) >= MAX_RESULTS:
                    break

            if not self._search_cancel.is_set():
                self.search_results = results
                self.after(0, self._search_done)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Search Error", str(e)))

    def _update_search_progress(self, pct: float, count: int, elapsed: float):
        self.progress["value"] = pct
        self.progress_lbl.config(
            text=f"Searching… {pct:.1f}%   {count} matches   {elapsed:.1f}s"
        )

    def _search_done(self):
        n = len(self.search_results)
        if n == 0:
            self.result_lbl.config(text="No results", fg=C["red"])
            self.progress_lbl.config(text="Search complete — no matches found")
        else:
            limit = f" (first {MAX_RESULTS})" if n == MAX_RESULTS else ""
            self.result_lbl.config(text=f"{n}{limit} matches", fg=C["green"])
            self.progress_lbl.config(text=f"Search complete — {n} matches")
            self.search_index = 0
            self._jump_to_result(0)

    def _next_result(self):
        if not self.search_results:
            return
        self.search_index = (self.search_index + 1) % len(self.search_results)
        self._jump_to_result(self.search_index)

    def _prev_result(self):
        if not self.search_results:
            return
        self.search_index = (self.search_index - 1) % len(self.search_results)
        self._jump_to_result(self.search_index)

    def _jump_to_result(self, idx: int):
        offset = self.search_results[idx]
        n = len(self.search_results)
        self.result_lbl.config(text=f"{idx + 1} / {n}", fg=C["green"])

        chunk_start = self.current_offset
        chunk_end = chunk_start + CHUNK_SIZE
        if not (chunk_start <= offset < chunk_end):
            self._load_chunk(max(0, offset - 2048))

        self._highlight_in_view(idx)

    def _highlight_in_view(self, active_idx: int):
        self._clear_highlights()
        chunk_start = self.current_offset
        chunk_end = chunk_start + CHUNK_SIZE
        query = self.search_var.get()

        for i, byte_off in enumerate(self.search_results):
            if byte_off < chunk_start or byte_off >= chunk_end:
                continue
            raw_before = self._mmap[chunk_start:byte_off]
            char_start = len(raw_before.decode(self.encoding, errors="replace"))
            char_end = char_start + len(query)
            tag = "active_hl" if i == active_idx else "highlight"
            self.text.tag_add(tag,
                              f"1.0 + {char_start} chars",
                              f"1.0 + {char_end} chars")

        if active_idx is not None:
            byte_off = self.search_results[active_idx]
            if chunk_start <= byte_off < chunk_end:
                raw_before = self._mmap[chunk_start:byte_off]
                char_start = len(raw_before.decode(self.encoding, errors="replace"))
                self.text.see(f"1.0 + {char_start} chars")

    def _clear_highlights(self):
        self.text.tag_remove("highlight", "1.0", "end")
        self.text.tag_remove("active_hl", "1.0", "end")


if __name__ == "__main__":
    app = BigFileReader()
    app.mainloop()
