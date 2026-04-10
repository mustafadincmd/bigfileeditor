#!/usr/bin/env python3
"""
BigFile Reader - Çok büyük dosyaları (10GB+) okuma ve arama uygulaması
mmap tabanlı bellek-verimli dosya erişimi kullanır
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mmap
import os
import threading
import re
import time
from pathlib import Path


CHUNK_SIZE = 512 * 1024       # Ekranda gösterilecek blok: 512 KB
SEARCH_BUFFER = 4 * 1024 * 1024  # Arama tamponu: 4 MB
MAX_RESULTS = 5000            # Maksimum arama sonucu


def detect_encoding(filepath: str, sample: int = 65536) -> str:
    """Basit encoding tespiti: UTF-8, Latin-1 veya binary."""
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
        self.geometry("1200x750")
        self.configure(bg="#1e1e2e")

        # Dosya durumu
        self.filepath: str | None = None
        self.filesize: int = 0
        self.encoding: str = "utf-8"
        self._mmap: mmap.mmap | None = None
        self._file = None
        self.current_offset: int = 0

        # Arama durumu
        self.search_results: list[int] = []   # byte offset listesi
        self.search_index: int = -1
        self._search_thread: threading.Thread | None = None
        self._search_cancel = threading.Event()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TButton", background="#313244", foreground="#cdd6f4",
                        relief="flat", padding=(8, 4))
        style.map("TButton",
                  background=[("active", "#45475a")],
                  foreground=[("active", "#cba6f7")])
        style.configure("Accent.TButton", background="#7c3aed", foreground="white",
                        relief="flat", padding=(8, 4))
        style.map("Accent.TButton",
                  background=[("active", "#6d28d9")])
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4",
                        insertcolor="#cba6f7", relief="flat")
        style.configure("Horizontal.TProgressbar",
                        troughcolor="#313244", background="#7c3aed")

        # ── Üst araç çubuğu ──
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))

        ttk.Button(toolbar, text="Dosya Aç", style="Accent.TButton",
                   command=self._open_file).pack(side="left", padx=(0, 6))

        ttk.Label(toolbar, text="Git (satır/byte):").pack(side="left")
        self.goto_var = tk.StringVar()
        goto_entry = ttk.Entry(toolbar, textvariable=self.goto_var, width=14)
        goto_entry.pack(side="left", padx=(4, 2))
        goto_entry.bind("<Return>", lambda _: self._goto())
        ttk.Button(toolbar, text="Git", command=self._goto).pack(side="left", padx=(0, 12))

        # Sağ taraf: dosya bilgisi
        self.info_label = ttk.Label(toolbar, text="Dosya açık değil",
                                    foreground="#6c7086")
        self.info_label.pack(side="right")

        # ── Arama çubuğu ──
        search_bar = ttk.Frame(self)
        search_bar.pack(fill="x", padx=8, pady=6)

        ttk.Label(search_bar, text="Ara:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", padx=(4, 4))
        search_entry.bind("<Return>", lambda _: self._start_search())

        self.regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_bar, text="Regex", variable=self.regex_var,
                        style="TLabel").pack(side="left", padx=(0, 4))

        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_bar, text="Büyük/küçük harf", variable=self.case_var,
                        style="TLabel").pack(side="left", padx=(0, 8))

        ttk.Button(search_bar, text="▶ Ara", style="Accent.TButton",
                   command=self._start_search).pack(side="left", padx=(0, 4))
        ttk.Button(search_bar, text="✕ İptal",
                   command=self._cancel_search).pack(side="left", padx=(0, 16))

        ttk.Button(search_bar, text="◀ Önceki",
                   command=self._prev_result).pack(side="left", padx=(0, 2))
        self.result_label = ttk.Label(search_bar, text="", foreground="#a6e3a1",
                                      width=18)
        self.result_label.pack(side="left")
        ttk.Button(search_bar, text="Sonraki ▶",
                   command=self._next_result).pack(side="left")

        # ── İlerleme çubuğu ──
        self.progress = ttk.Progressbar(self, orient="horizontal",
                                        mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=8, pady=(0, 4))
        self.progress_label = ttk.Label(self, text="", foreground="#6c7086",
                                        font=("Menlo", 10))
        self.progress_label.pack(anchor="w", padx=10)

        # ── Ana metin alanı ──
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.text = tk.Text(
            text_frame,
            bg="#181825", fg="#cdd6f4",
            font=("Menlo", 12),
            insertbackground="#cba6f7",
            selectbackground="#45475a",
            relief="flat",
            wrap="none",
            state="disabled",
        )
        self.text.tag_configure("highlight", background="#f9e2af", foreground="#1e1e2e")
        self.text.tag_configure("active_hl", background="#a6e3a1", foreground="#1e1e2e")

        vsb = ttk.Scrollbar(text_frame, orient="vertical",
                            command=self.text.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal",
                            command=self.text.xview)
        self.text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        # ── Alt durum çubuğu ──
        status_bar = ttk.Frame(self)
        status_bar.pack(fill="x", padx=8, pady=(0, 6))

        self.offset_label = ttk.Label(status_bar, text="Offset: -",
                                      foreground="#6c7086", font=("Menlo", 10))
        self.offset_label.pack(side="left", padx=(0, 16))
        self.line_label = ttk.Label(status_bar, text="Satır: -",
                                    foreground="#6c7086", font=("Menlo", 10))
        self.line_label.pack(side="left", padx=(0, 16))

        # Blok gezinme
        nav_frame = ttk.Frame(status_bar)
        nav_frame.pack(side="right")
        ttk.Button(nav_frame, text="◀◀ Başa",
                   command=self._go_start).pack(side="left", padx=2)
        ttk.Button(nav_frame, text="◀ Önceki Blok",
                   command=self._prev_chunk).pack(side="left", padx=2)
        ttk.Button(nav_frame, text="Sonraki Blok ▶",
                   command=self._next_chunk).pack(side="left", padx=2)
        ttk.Button(nav_frame, text="Sona ▶▶",
                   command=self._go_end).pack(side="left", padx=2)

    # --------------------------------------------------------------- Dosya --
    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Dosya Seç",
            filetypes=[("Tüm dosyalar", "*.*"),
                       ("Metin dosyaları", "*.txt *.log *.csv *.json *.xml"),
                       ("Yedek dosyalar", "*.bak *.backup *.sql *.dump")]
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
            self.result_label.config(text="")
            self.title(f"BigFile Reader — {Path(path).name}")
            self.info_label.config(
                text=f"{Path(path).name}  |  {human_size(self.filesize)}  |  {self.encoding}"
            )
            self._load_chunk(0)
        except Exception as e:
            messagebox.showerror("Hata", f"Dosya açılamadı:\n{e}")

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

    # --------------------------------------------------------------- Görüntü --
    def _load_chunk(self, offset: int):
        """Dosyadan offset'ten itibaren CHUNK_SIZE kadar oku ve göster."""
        if not self._mmap or self.filesize == 0:
            return
        offset = max(0, min(offset, self.filesize - 1))
        # Satır başına hizala
        self._mmap.seek(offset)
        raw = self._mmap.read(CHUNK_SIZE)
        text = raw.decode(self.encoding, errors="replace")

        self.current_offset = offset
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.config(state="disabled")

        # Durum güncelle
        self.offset_label.config(
            text=f"Offset: {offset:,}  /  {self.filesize:,}"
        )
        approx_line = self._estimate_line(offset)
        self.line_label.config(text=f"~Satır: {approx_line:,}")
        self.progress["value"] = (offset / self.filesize) * 100 if self.filesize else 0
        self.progress_label.config(
            text=f"{human_size(offset)} / {human_size(self.filesize)}"
        )

    def _estimate_line(self, offset: int) -> int:
        """Offset'e kadar newline sayısını hızlıca tahmin et (örnekleme ile)."""
        if not self._mmap or offset == 0:
            return 1
        sample_step = max(1, offset // 200)
        count = 0
        for i in range(0, offset, sample_step):
            end = min(i + sample_step, offset)
            count += self._mmap[i:end].count(b"\n")
        return count + 1

    def _go_start(self):
        self._load_chunk(0)

    def _go_end(self):
        self._load_chunk(max(0, self.filesize - CHUNK_SIZE))

    def _next_chunk(self):
        self._load_chunk(self.current_offset + CHUNK_SIZE)

    def _prev_chunk(self):
        self._load_chunk(self.current_offset - CHUNK_SIZE)

    def _goto(self):
        """Satır numarası veya byte offset'e git."""
        val = self.goto_var.get().strip()
        if not val or not self._mmap:
            return
        try:
            n = int(val)
        except ValueError:
            messagebox.showwarning("Uyarı", "Geçerli bir sayı girin.")
            return

        # n < filesize → byte offset, aksi halde satır numarası
        if n < self.filesize:
            self._load_chunk(n)
        else:
            self._goto_line(n)

    def _goto_line(self, target_line: int):
        """Satır numarasına giderek o satırı göster."""
        if not self._mmap:
            return
        self.progress_label.config(text=f"Satır {target_line:,} aranıyor...")
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
                # Bu blok içinde
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

    # --------------------------------------------------------------- Arama --
    def _start_search(self):
        query = self.search_var.get()
        if not query or not self._mmap:
            return
        self._cancel_search()
        self._search_cancel.clear()
        self.search_results.clear()
        self.search_index = -1
        self.result_label.config(text="Aranıyor...")
        self._clear_highlights()

        self._search_thread = threading.Thread(
            target=self._search_worker,
            args=(query, self.regex_var.get(), self.case_var.get()),
            daemon=True
        )
        self._search_thread.start()

    def _cancel_search(self):
        self._search_cancel.set()
        if self._search_thread and self._search_thread.is_alive():
            self._search_thread.join(timeout=1)

    def _search_worker(self, query: str, use_regex: bool, case_sensitive: bool):
        """Arka planda dosyayı tara, sonuçları topla."""
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            if use_regex:
                pattern = re.compile(query.encode(self.encoding, errors="replace"),
                                     flags)
            else:
                needle = query.encode(self.encoding, errors="replace")
                if not case_sensitive:
                    needle_lower = needle.lower()

            results = []
            offset = 0
            self._mmap.seek(0)
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
                            needle_lower if not case_sensitive else needle, pos
                        )
                        if idx == -1:
                            break
                        results.append(offset + idx)
                        pos = idx + 1
                        if len(results) >= MAX_RESULTS:
                            break

                offset += SEARCH_BUFFER - len(query.encode()) - 1

                # İlerleme güncelle (UI thread'ine gönder)
                pct = (offset / self.filesize) * 100
                elapsed = time.time() - t0
                self.after(0, self._update_search_progress, pct, len(results), elapsed)

                if len(results) >= MAX_RESULTS:
                    break

            if not self._search_cancel.is_set():
                self.search_results = results
                self.after(0, self._search_done)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Arama Hatası", str(e)))

    def _update_search_progress(self, pct: float, count: int, elapsed: float):
        self.progress["value"] = pct
        self.progress_label.config(
            text=f"Aranıyor... {pct:.1f}%  |  {count} sonuç  |  {elapsed:.1f}s"
        )

    def _search_done(self):
        n = len(self.search_results)
        if n == 0:
            self.result_label.config(text="Sonuç bulunamadı", foreground="#f38ba8")
            self.progress_label.config(text="Arama tamamlandı")
        else:
            limit_note = f" (ilk {MAX_RESULTS})" if n == MAX_RESULTS else ""
            self.result_label.config(
                text=f"{n}{limit_note} sonuç", foreground="#a6e3a1"
            )
            self.progress_label.config(text=f"Arama tamamlandı — {n} eşleşme")
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
        self.result_label.config(text=f"{idx + 1} / {n}", foreground="#a6e3a1")

        # Bloğu yenile (sonuç görünürse yeniden yükleme)
        chunk_start = self.current_offset
        chunk_end = chunk_start + CHUNK_SIZE
        if not (chunk_start <= offset < chunk_end):
            self._load_chunk(max(0, offset - 2048))

        # Metin alanında vurgula
        self._highlight_in_view(idx)

    def _highlight_in_view(self, active_idx: int):
        """Görünür chunk içindeki tüm sonuçları vurgula."""
        self._clear_highlights()
        chunk_start = self.current_offset
        chunk_end = chunk_start + CHUNK_SIZE
        query = self.search_var.get()
        query_bytes = query.encode(self.encoding, errors="replace")

        for i, byte_off in enumerate(self.search_results):
            if byte_off < chunk_start or byte_off >= chunk_end:
                continue
            rel = byte_off - chunk_start
            # Byte offset → karakter offset
            raw_before = self._mmap[chunk_start:byte_off]
            char_start = len(raw_before.decode(self.encoding, errors="replace"))
            char_end = char_start + len(query)

            start = f"1.0 + {char_start} chars"
            end = f"1.0 + {char_end} chars"
            tag = "active_hl" if i == active_idx else "highlight"
            self.text.tag_add(tag, start, end)

        if active_idx is not None:
            # Aktif sonuca kaydır
            byte_off = self.search_results[active_idx]
            if chunk_start <= byte_off < chunk_end:
                rel = byte_off - chunk_start
                raw_before = self._mmap[chunk_start:byte_off]
                char_start = len(raw_before.decode(self.encoding, errors="replace"))
                self.text.see(f"1.0 + {char_start} chars")

    def _clear_highlights(self):
        self.text.tag_remove("highlight", "1.0", "end")
        self.text.tag_remove("active_hl", "1.0", "end")


if __name__ == "__main__":
    app = BigFileReader()
    app.mainloop()
