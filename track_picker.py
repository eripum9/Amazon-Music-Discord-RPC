# MIT License - Copyright (c) 2026 eripum9

import sys
import json
import io
import tkinter as tk
from tkinter import font as tkfont
from urllib.request import urlopen, Request

BG = "#202020"
CARD_BG = "#2d2d2d"
FG = "#e4e4e4"
FG_DIM = "#999"
ACCENT = "#5865f2"
BTN_BG = "#383838"
BORDER = "#3d3d3d"

_photo_refs = []


def _load_thumbnail(url, size=50):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urlopen(req, timeout=5).read()
        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(raw))
        img = img.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def _track_payload(track):
    return {
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "album": track.get("album", ""),
        "art_url": track.get("art_url", ""),
        "track_link": track.get("track_link", ""),
        "duration": track.get("duration", 0) or 0,
    }


def _search_page(query, page_size, page, search_fn=None):
    offset = max(0, int(page)) * max(1, int(page_size))
    if search_fn:
        try:
            return search_fn(query, limit=page_size, offset=offset)
        except TypeError:
            if offset:
                return []
            return search_fn(query, limit=page_size)
    from album_art import search_tracks
    return search_tracks(query, limit=page_size, offset=offset)


def _center_window(root, min_width):
    root.update_idletasks()
    w = max(root.winfo_reqwidth(), min_width)
    h = root.winfo_reqheight()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")


def show_choice_picker(title, choices, search_query=None, page_size=5, prompt="No artist found. Select the correct track:", remember=True, search_fn=None):
    result = {"index": -1, "remember": False, "track": None}
    _photo_refs.clear()
    page_size = max(1, int(page_size or 5))

    root = tk.Tk()
    root.title("Amazon Music RPC")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    main_font = tkfont.Font(family="Segoe UI", size=10)
    title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    small_font = tkfont.Font(family="Segoe UI", size=9)

    tk.Label(
        root, text=f'"{title}"', bg=BG, fg=FG, font=title_font,
        wraplength=440, justify="left"
    ).pack(padx=20, pady=(16, 4), anchor="w")

    tk.Label(
        root, text=prompt,
        bg=BG, fg=FG_DIM, font=small_font
    ).pack(padx=20, pady=(0, 10), anchor="w")

    selected = tk.IntVar(value=-1)
    pages = {0: list(choices or [])}
    current_page = [0]
    exhausted_pages = set()
    list_frame = tk.Frame(root, bg=BG)
    list_frame.pack(fill="x")
    status_label = tk.Label(root, text="", bg=BG, fg=FG_DIM, font=small_font)
    status_label.pack(padx=20, pady=(4, 2), anchor="w")

    def render_choices():
        for child in list_frame.winfo_children():
            child.destroy()
        _photo_refs.clear()
        selected.set(-1)
        page_choices = pages.get(current_page[0], [])
        if not page_choices:
            tk.Label(
                list_frame, text="No results found on this page.",
                bg=BG, fg=FG_DIM, font=small_font
            ).pack(padx=20, pady=12, anchor="w")
        for i, c in enumerate(page_choices):
            row_frame = tk.Frame(list_frame, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
            row_frame.pack(fill="x", padx=16, pady=2)

            rb = tk.Radiobutton(
                row_frame, variable=selected, value=i,
                bg=CARD_BG, selectcolor=BTN_BG,
                activebackground=CARD_BG, highlightthickness=0, bd=0
            )
            rb.pack(side="left", padx=(8, 4), pady=6)

            thumb = _load_thumbnail(c.get("art_url", ""), 48) if c.get("art_url") else None
            if thumb:
                _photo_refs.append(thumb)
                tk.Label(row_frame, image=thumb, bg=CARD_BG, bd=0).pack(side="left", padx=(0, 8), pady=4)
            else:
                placeholder = tk.Frame(row_frame, bg="#444", width=48, height=48)
                placeholder.pack_propagate(False)
                placeholder.pack(side="left", padx=(0, 8), pady=4)

            info_frame = tk.Frame(row_frame, bg=CARD_BG)
            info_frame.pack(side="left", fill="x", expand=True, pady=4)

            tk.Label(
                info_frame, text=c.get("title", ""), bg=CARD_BG, fg="#fff",
                font=main_font, anchor="w"
            ).pack(anchor="w")
            tk.Label(
                info_frame, text=c.get("artist", ""), bg=CARD_BG, fg=FG,
                font=small_font, anchor="w"
            ).pack(anchor="w")
            album_text = c.get("album", "")
            if album_text:
                tk.Label(
                    info_frame, text=album_text, bg=CARD_BG, fg=FG_DIM,
                    font=small_font, anchor="w"
                ).pack(anchor="w")
        page_label.configure(text=f"Page {current_page[0] + 1}")
        prev_btn.configure(state="normal" if current_page[0] > 0 else "disabled")
        can_next = bool(search_query) and current_page[0] not in exhausted_pages and len(page_choices) >= page_size
        next_btn.configure(state="normal" if can_next else "disabled")
        _center_window(root, 500)

    def load_page(page):
        if page < 0:
            return
        if page in pages:
            current_page[0] = page
            status_label.configure(text="")
            render_choices()
            return
        if not search_query:
            return
        status_label.configure(text="Searching...")
        root.update_idletasks()
        tracks = _search_page(search_query, page_size, page, search_fn)
        if not tracks:
            exhausted_pages.add(page - 1)
            status_label.configure(text="No more results.")
            render_choices()
            return
        pages[page] = tracks
        current_page[0] = page
        status_label.configure(text="")
        if len(tracks) < page_size:
            exhausted_pages.add(page)
        render_choices()

    remember_var = tk.BooleanVar(value=False)
    if remember:
        tk.Checkbutton(
            root, text="Always use this for this title", variable=remember_var,
            bg=BG, fg=FG_DIM, selectcolor=BTN_BG,
            activebackground=BG, activeforeground=FG,
            font=small_font, highlightthickness=0, bd=0
        ).pack(padx=20, pady=(6, 8), anchor="w")

    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(fill="x", padx=16, pady=(0, 14))

    def on_select():
        selected_index = selected.get()
        page_choices = pages.get(current_page[0], [])
        if selected_index >= 0 and selected_index < len(page_choices):
            chosen = page_choices[selected_index]
            result["index"] = current_page[0] * page_size + selected_index
            result["remember"] = remember_var.get()
            result["track"] = _track_payload(chosen)
        root.destroy()

    def on_skip():
        root.destroy()

    prev_btn = tk.Button(
        btn_frame, text="Previous", command=lambda: load_page(current_page[0] - 1),
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=12, pady=4, cursor="hand2"
    )
    prev_btn.pack(side="left")

    page_label = tk.Label(btn_frame, text="Page 1", bg=BG, fg=FG_DIM, font=small_font)
    page_label.pack(side="left", padx=8)

    next_btn = tk.Button(
        btn_frame, text="Next", command=lambda: load_page(current_page[0] + 1),
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=12, pady=4, cursor="hand2"
    )
    next_btn.pack(side="left")

    tk.Button(
        btn_frame, text="Select", command=on_select,
        bg=ACCENT, fg="#fff", font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right", padx=(5, 0))

    tk.Button(
        btn_frame, text="Skip", command=on_skip,
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right")

    render_choices()

    root.protocol("WM_DELETE_WINDOW", on_skip)
    root.mainloop()

    return result


def _show_confirm(root, track_info, main_font, small_font):
    _photo_refs.clear()
    confirm_result = {"accepted": False}

    win = tk.Toplevel(root)
    win.title("Amazon Music RPC")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.grab_set()

    tk.Label(
        win, text="Is this the right track?",
        bg=BG, fg=FG, font=tkfont.Font(family="Segoe UI", size=11, weight="bold")
    ).pack(padx=20, pady=(16, 10), anchor="w")

    card = tk.Frame(win, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
    card.pack(fill="x", padx=16, pady=(0, 10))

    thumb = _load_thumbnail(track_info.get("art_url", ""), 64) if track_info.get("art_url") else None
    if thumb:
        _photo_refs.append(thumb)
        tk.Label(card, image=thumb, bg=CARD_BG, bd=0).pack(side="left", padx=(12, 10), pady=10)
    else:
        placeholder = tk.Frame(card, bg="#444", width=64, height=64)
        placeholder.pack_propagate(False)
        placeholder.pack(side="left", padx=(12, 10), pady=10)

    info = tk.Frame(card, bg=CARD_BG)
    info.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 12))

    tk.Label(info, text=track_info.get("title", ""), bg=CARD_BG, fg="#fff", font=main_font, anchor="w").pack(anchor="w")
    tk.Label(info, text=track_info.get("artist", ""), bg=CARD_BG, fg=FG, font=main_font, anchor="w").pack(anchor="w")
    album = track_info.get("album", "")
    if album:
        tk.Label(info, text=album, bg=CARD_BG, fg=FG_DIM, font=small_font, anchor="w").pack(anchor="w")

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(fill="x", padx=16, pady=(0, 14))

    def on_yes():
        confirm_result["accepted"] = True
        win.destroy()

    def on_no():
        win.destroy()

    tk.Button(
        btn_frame, text="Yes", command=on_yes,
        bg=ACCENT, fg="#fff", font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right", padx=(5, 0))

    tk.Button(
        btn_frame, text="Try Again", command=on_no,
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right")

    win.update_idletasks()
    w = max(win.winfo_reqwidth(), 400)
    h = win.winfo_reqheight()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

    win.protocol("WM_DELETE_WINDOW", on_no)
    win.wait_window()
    return confirm_result["accepted"]


def show_input_picker(artist, search_fn=None):
    result = {"title": "", "artist": "", "album": "", "art_url": ""}

    root = tk.Tk()
    root.title("Amazon Music RPC")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    main_font = tkfont.Font(family="Segoe UI", size=10)
    title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    small_font = tkfont.Font(family="Segoe UI", size=9)

    tk.Label(
        root, text=f'Artist: "{artist}"', bg=BG, fg=FG, font=title_font
    ).pack(padx=20, pady=(16, 4), anchor="w")

    tk.Label(
        root, text="Could not identify the song. Enter the title:",
        bg=BG, fg=FG_DIM, font=small_font
    ).pack(padx=20, pady=(0, 10), anchor="w")

    entry = tk.Entry(
        root, bg=BTN_BG, fg=FG, insertbackground=FG,
        font=main_font, relief="flat", bd=5
    )
    entry.pack(fill="x", padx=20, pady=(0, 10))
    entry.focus_set()

    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(fill="x", padx=16, pady=(0, 14))
    status_label = tk.Label(root, text="", bg=BG, fg=FG_DIM, font=small_font)
    status_label.pack(padx=20, pady=(0, 8), anchor="w")

    def on_search(event=None):
        query = entry.get().strip()
        if not query:
            return
        search_query = f"{query} {artist}"
        status_label.configure(text="Searching...")
        root.update_idletasks()
        tracks = _search_page(search_query, 5, 0, search_fn)
        if not tracks:
            status_label.configure(text="No results found.")
            return
        root.destroy()
        picked = show_choice_picker(
            query,
            tracks,
            search_query=search_query,
            page_size=5,
            prompt="Select the correct track:",
            remember=False,
            search_fn=search_fn,
        )
        track_info = picked.get("track") or {}
        if track_info:
            result["title"] = track_info.get("title", query)
            result["artist"] = track_info.get("artist", artist)
            result["album"] = track_info.get("album", "")
            result["art_url"] = track_info.get("art_url", "")
            result["track_link"] = track_info.get("track_link", "")
            result["duration"] = track_info.get("duration", 0) or 0

    def on_skip():
        root.destroy()

    entry.bind("<Return>", on_search)

    tk.Button(
        btn_frame, text="Search", command=on_search,
        bg=ACCENT, fg="#fff", font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right", padx=(5, 0))

    tk.Button(
        btn_frame, text="Skip", command=on_skip,
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(side="right")

    _center_window(root, 400)

    root.protocol("WM_DELETE_WINDOW", on_skip)
    root.mainloop()

    return result


def show_wrong_song_dialog():
    result = {"choice": ""}

    root = tk.Tk()
    root.title("Amazon Music RPC")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    main_font = tkfont.Font(family="Segoe UI", size=10)

    tk.Label(
        root, text="Did we make a mistake?",
        bg=BG, fg=FG, font=title_font
    ).pack(padx=24, pady=(20, 16))

    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(fill="x", padx=24, pady=(0, 8))

    def pick_artist():
        result["choice"] = "artist"
        root.destroy()

    def pick_title():
        result["choice"] = "title"
        root.destroy()

    tk.Button(
        btn_frame, text="Wrong Artist", command=pick_artist,
        bg=ACCENT, fg="#fff", font=main_font, relief="flat",
        padx=18, pady=8, cursor="hand2", width=14
    ).pack(side="left", padx=(0, 6), expand=True)

    tk.Button(
        btn_frame, text="Wrong Song", command=pick_title,
        bg=ACCENT, fg="#fff", font=main_font, relief="flat",
        padx=18, pady=8, cursor="hand2", width=14
    ).pack(side="right", padx=(6, 0), expand=True)

    cancel_frame = tk.Frame(root, bg=BG)
    cancel_frame.pack(fill="x", padx=24, pady=(0, 16))

    tk.Button(
        cancel_frame, text="Cancel", command=root.destroy,
        bg=BTN_BG, fg=FG, font=main_font, relief="flat",
        padx=16, pady=4, cursor="hand2"
    ).pack(expand=True)

    root.update_idletasks()
    w = max(root.winfo_reqwidth(), 340)
    h = root.winfo_reqheight()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

    return result


def show_console(log_file_path):
    root = tk.Tk()
    root.title("Amazon Music RPC - Console")
    root.configure(bg="#1a1a1a")
    root.geometry("700x420")
    root.minsize(400, 200)

    mono_font = tkfont.Font(family="Consolas", size=9)

    text = tk.Text(
        root, bg="#1a1a1a", fg="#cccccc", font=mono_font,
        insertbackground="#ccc", selectbackground="#3a3a5a",
        relief="flat", bd=8, wrap="word", state="disabled"
    )
    scrollbar = tk.Scrollbar(root, command=text.yview, bg="#2a2a2a", troughcolor="#1a1a1a")
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    text.pack(fill="both", expand=True)

    last_pos = [0]

    def poll_log():
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_pos[0])
                new_data = f.read()
                if new_data:
                    last_pos[0] = f.tell()
                    text.configure(state="normal")
                    text.insert("end", new_data)
                    text.see("end")
                    text.configure(state="disabled")
        except FileNotFoundError:
            pass
        except Exception:
            pass
        root.after(500, poll_log)

    poll_log()

    root.mainloop()


def run_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        request = json.load(f)

    mode = request.get("mode")

    if mode == "choice":
        response = show_choice_picker(
            request["title"],
            request["choices"],
            search_query=request.get("search_query") or request.get("title", ""),
            page_size=request.get("page_size", 5),
        )
    elif mode == "input":
        response = show_input_picker(request["artist"])
    elif mode == "wrongsong":
        response = show_wrong_song_dialog()
    else:
        response = {}

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(response, f)


if __name__ == "__main__":
    if '--console' in sys.argv:
        idx = sys.argv.index('--console')
        if idx + 1 < len(sys.argv):
            show_console(sys.argv[idx + 1])
    elif len(sys.argv) > 1:
        run_from_file(sys.argv[1])
