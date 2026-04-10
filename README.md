# BigFile Editor

A lightweight, memory-efficient desktop viewer for reading and searching **extremely large files** (10 GB+) without loading the entire file into RAM.

Built with Python and Tkinter, it uses `mmap` (memory-mapped file I/O) to access only the parts of the file you actually need — making it fast even on files that would crash a standard text editor.

---

## Features

- **Opens files of any size** — 10 MB or 100 GB, it doesn't matter
- **Memory-mapped I/O** — reads only a 512 KB chunk at a time, not the whole file
- **Full-text search** across the entire file, with:
  - Plain text and **regex** support
  - Case-sensitive / case-insensitive toggle
  - Up to 5,000 results, navigable with Prev / Next
  - Background search thread with live progress and cancel button
- **Go to line or byte offset** — jump directly to any position in the file
- **Block navigation** — move forward/backward through 512 KB chunks
- **Auto encoding detection** — UTF-8, UTF-8 BOM, Latin-1, or binary
- **Dark themed UI** — easy on the eyes during long sessions

---

## Requirements

- Python 3.10 or higher
- No external dependencies — uses only the Python standard library (`tkinter`, `mmap`, `threading`, `re`)

---

## Installation

```bash
git clone https://github.com/mustafadincmd/bigfileeditor.git
cd bigfileeditor
python bigfile_reader.py
```

No `pip install` needed.

---

## Usage

### Opening a file

1. Launch the app: `python bigfile_reader.py`
2. Click **Open File** and select any file
3. The first 512 KB chunk is displayed immediately

### Navigating

| Control | Action |
|---|---|
| **Next Block / Prev Block** | Move forward or backward by 512 KB |
| **Start / End** | Jump to the beginning or end of the file |
| **Go to (line/byte)** | Type a number and press Enter — if the number is less than the file size it is treated as a byte offset; otherwise as a line number |

### Searching

1. Type your query in the **Search** field
2. Optionally enable **Regex** and/or **Case-sensitive**
3. Click **Search** or press Enter
4. Use **Prev** / **Next** to navigate through matches
5. Click **Cancel** to stop an in-progress search

Matched text is highlighted in the current view. The active match is shown in green; other visible matches in yellow.

---

## How It Works

BigFile Editor uses Python's `mmap` module to memory-map the opened file. The OS manages paging so only the bytes actually accessed are loaded from disk — the app never holds more than a single 512 KB chunk in memory at a time.

Search runs on a background thread in 4 MB buffer increments so the UI stays responsive. Results are stored as byte offsets to avoid a full file scan on every navigation step.

---

## Supported File Types

Works with any file that contains readable text:

- Log files (`.log`)
- CSV / TSV datasets
- SQL dumps
- JSON / XML exports
- Plain text files
- Backup and archive text exports

Binary files can be opened but content may appear garbled.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Contributing

Pull requests are welcome. For major changes please open an issue first to discuss what you would like to change.
