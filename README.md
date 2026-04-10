# BigFile Editor — Large Text File Viewer for Windows, macOS & Linux

**Open, read, and search large text files** of any size — 1 GB, 10 GB, even 100 GB — instantly, without freezing or running out of memory.

BigFile Editor is a free, open-source desktop app built with Python 3 and Tkinter. It uses memory-mapped I/O (`mmap`) so it never loads the entire file into RAM — only the part you are viewing is read from disk.

> Tired of your text editor crashing on a 2 GB log file? This tool was built for exactly that.

---

## Who Is This For?

- Developers and sysadmins inspecting **large log files**
- Data engineers browsing **multi-gigabyte CSV or TSV exports**
- DBAs reading **SQL dumps** that are too big for any IDE
- Anyone who has ever seen _"file too large to open"_ in their editor

---

## Features

- **Open files of any size** — tested with files over 10 GB
- **Memory-mapped I/O** — only 512 KB loaded at a time, RAM usage stays flat
- **Full-file search** — scans the entire file without loading it all into memory
  - Plain text and **regular expression (regex)** search
  - Case-sensitive and case-insensitive modes
  - Up to 5,000 results, highlighted and navigable with Prev / Next
  - Runs in a background thread — UI never freezes, cancel anytime
- **Jump to line or byte offset** — go directly to any position in the file
- **Block navigation** — step through the file in 512 KB chunks
- **Auto encoding detection** — UTF-8, UTF-8 BOM, Latin-1, binary
- **Dark themed UI** — comfortable for long reading sessions
- **No installation, no dependencies** — just Python 3 and the standard library

---

## Requirements

- Python 3 (any version with Tkinter — typically Python 3.6+)
- No `pip install` needed — uses only the standard library

---

## Installation & Quick Start

```bash
git clone https://github.com/mustafadincmd/bigfileeditor.git
cd bigfileeditor
python3 bigfile_reader.py
```

That's it. No virtual environment, no dependencies.

---

## Usage

### Opening a File

1. Run `python3 bigfile_reader.py`
2. Click **Open File** and select any text file — regardless of size
3. The first 512 KB is displayed immediately

### Navigating Large Files

| Control | Action |
|---|---|
| **Next Block** | Move forward 512 KB |
| **Prev Block** | Move backward 512 KB |
| **Start** | Jump to the beginning of the file |
| **End** | Jump to the end of the file |
| **Go to** | Enter a number and press Enter — treated as a byte offset if smaller than the file size, otherwise as a line number |

### Searching

1. Type your keyword or regex pattern in the **Search** box
2. Toggle **Regex** for pattern matching, or **Case-sensitive** as needed
3. Press Enter or click **Search**
4. Navigate results with **Prev** / **Next**
5. Hit **Cancel** to stop a running search at any time

Active match is highlighted in **green**, other visible matches in **yellow**.

---

## Supported File Types

Any file that contains readable text:

| Type | Examples |
|---|---|
| Log files | `.log`, `.out`, access logs, error logs |
| Tabular data | `.csv`, `.tsv` |
| Database exports | `.sql`, `.dump` |
| Structured data | `.json`, `.xml`, `.yaml` |
| Plain text | `.txt`, `.md` |
| Backup files | `.bak`, `.backup` |

---

## How It Works

Python's `mmap` module maps the file into the process's virtual address space. The operating system handles paging — bytes are only read from disk when accessed, and immediately freed when no longer needed. BigFile Editor reads one 512 KB chunk at a time for display.

Search runs on a separate background thread, scanning the file in 4 MB increments. Results are stored as byte offsets (not line numbers) so navigation never requires a re-scan.

This approach keeps **RAM usage constant** regardless of file size.

---

## Keywords

large file viewer, big text file reader, open large log file, view 10gb file, large csv viewer, read large file python, big file editor, log file viewer, memory efficient text viewer, mmap file reader

---

## License

MIT — free to use, modify, and distribute.

---

## Contributing

Pull requests are welcome. Please open an issue first for larger changes.
