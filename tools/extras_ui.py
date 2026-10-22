"""The v2 tabs of Shu's DLSS 5 Switch: Newest DLSS, Desktop Icons, Games Folder. Same look as the switch page."""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import dlss5core as core
import extras

BG, PANEL, CARD, FG, MUTED = "#101317", "#181c22", "#1e232a", "#f1efe9", "#9aa0a6"
CYAN, GREEN, AMBER = "#10bad8", "#5fd38d", "#e6b24a"
F = "Segoe UI"


def _title(parent, text, sub):
    tk.Label(parent, text=text, bg=BG, fg=FG, font=(F, 22, "bold")).pack(anchor="w", padx=32, pady=(22, 2))
    tk.Label(parent, text=sub, bg=BG, fg=MUTED, font=(F, 14), wraplength=1050, justify="left").pack(anchor="w", padx=32)


def _box(parent):
    b = tk.Frame(parent, bg=PANEL, padx=24, pady=18)
    b.pack(fill="x", padx=32, pady=(18, 0))
    return b


def _row(parent):
    r = tk.Frame(parent, bg=BG)
    r.pack(anchor="w", padx=32, pady=16)
    return r


def _note(parent, text):
    tk.Label(parent, text=text, bg=BG, fg=MUTED, font=(F, 12), wraplength=1050, justify="left").pack(anchor="w", padx=32)


def build(app, key: str) -> tk.Frame:
    return {"newest": _newest, "icons": _icons, "folder": _folder}[key](app)


# ------------------------------------------------------------------ Newest DLSS
def _newest(app) -> tk.Frame:
    f = tk.Frame(app, bg=BG)
    _title(f, "Newest DLSS For Every Game",
           "Your NVIDIA Driver Keeps The Newest DLSS. One Click Makes Every DLSS Game Use It, With NVIDIA's "
           "Recommended Preset. Games Still Need DLSS Switched On In Their Own Menu.")
    box = _box(f)
    lines: dict[str, tk.Label] = {}
    for _sid, (name, _v) in extras.DLSS_SETTINGS.items():
        r = tk.Frame(box, bg=PANEL)
        r.pack(fill="x", pady=3)
        tk.Label(r, text=name, bg=PANEL, fg=FG, font=(F, 15)).pack(side="left")
        lines[name] = tk.Label(r, text="Press Check", bg=PANEL, fg=MUTED, font=(F, 14, "bold"))
        lines[name].pack(side="right")

    def show(st):
        for n, ok in st.items():
            lines[n].configure(text="On" if ok else "Not Set", fg=GREEN if ok else MUTED)

    def go(label, work):
        app.status.configure(text=label)

        def done(res, err):
            app.status.configure(text="")
            if err:
                messagebox.showerror(core.APP, str(err))
            else:
                show(res)
        def task():
            if not extras.npi_ready():
                extras.get_npi()
            return work()
        app.bg(task, done)

    row = _row(f)
    app.button(row, "Turn On Newest DLSS", lambda: go("Updating Your Driver Settings...", extras.dlss_on), big=True).pack(side="left")
    app.button(row, "Check", lambda: go("Reading Your Driver Settings...", extras.dlss_status), primary=False).pack(side="left", padx=10)
    app.button(row, "Undo", lambda: go("Putting It Back...", extras.dlss_undo), primary=False).pack(side="left")
    _note(f, "Windows Asks For Permission Each Time: NVIDIA Profile Inspector (Free, Open Source, By Orbmu2k) Makes "
             "The Change. It's Downloaded Once From Its GitHub And Checked First. Your Settings Are Backed Up Before "
             "Anything Changes. The NVIDIA App Can Change These Back If You Use Its DLSS Override.")
    return f


# ------------------------------------------------------------------ Desktop Icons
def _icons(app) -> tk.Frame:
    f = tk.Frame(app, bg=BG)
    _title(f, "Big Matching Desktop Icons",
           "Windows Loves To Break Game Icons. This Gives Every Game Shortcut On Your Desktop A Big, Matching Icon "
           "That Updates Can't Break.")
    box = _box(f)
    for t in ("1.  Your Own Pick: Put An Image Named After The Game In Your Custom Folder.",
              "2.  SteamGridDB: The Best-Voted Community Icon, Artist Credited. Needs Your Own Free Key (Below).",
              "3.  Steam's Own Library Art, Already On Your PC.",
              "4.  The Game's Own Icon, Made Big."):
        tk.Label(box, text=t, bg=PANEL, fg=FG, font=(F, 14)).pack(anchor="w", pady=2)
    msg = tk.Label(f, text="", bg=BG, fg=GREEN, font=(F, 15, "bold"))

    def run(label, work):
        app.status.configure(text=label)

        def done(res, err):
            app.status.configure(text="")
            if err:
                messagebox.showerror(core.APP, str(err))
            else:
                msg.configure(text=res + "   ·   Press F5 On Your Desktop If Any Old Ones Show")

        def prog(frac, game):
            app.after(0, lambda: app.status.configure(text=f"Making Icons...  {int(frac * 100)}%  {game}"))
        app.bg(lambda: work(prog), done)

    row = _row(f)
    app.button(row, "Make My Icons", lambda: run("Making Icons...", lambda p: extras.icons_apply(app.settings, p)), big=True).pack(side="left")
    app.button(row, "Put My Old Icons Back", lambda: run("Undoing...", lambda p: extras.icons_undo()), primary=False).pack(side="left", padx=10)
    app.button(row, "Custom Folder", lambda: _open(extras.CUSTOM), primary=False).pack(side="left")
    app.button(row, "Credits", lambda: _open(extras.CREDITS), primary=False).pack(side="left", padx=10)
    msg.pack(anchor="w", padx=32)

    keyrow = tk.Frame(f, bg=BG)
    keyrow.pack(anchor="w", padx=32, pady=(18, 4))
    has = extras.SGDB_KEY.exists() and extras.SGDB_KEY.read_text(encoding="utf-8").strip()
    tk.Label(keyrow, text="SteamGridDB Key:", bg=BG, fg=FG, font=(F, 14, "bold")).pack(side="left")
    state = tk.Label(keyrow, text="Saved" if has else "Not Set", bg=BG, fg=GREEN if has else MUTED, font=(F, 14))
    state.pack(side="left", padx=10)

    def set_key():
        k = _ask_key(app)
        if k:
            extras.SGDB_KEY.parent.mkdir(parents=True, exist_ok=True)
            extras.SGDB_KEY.write_text(k.strip(), encoding="utf-8")
            state.configure(text="Saved", fg=GREEN)
    app.button(keyrow, "Paste My Key", set_key, primary=False).pack(side="left", padx=10)
    app.link(keyrow, "Get A Free Key (Sign In, Then Preferences, API)", "https://www.steamgriddb.com/profile/preferences/api").pack(side="left")
    if not extras.pillow_ok():
        tk.Label(f, text="Desktop Icons Needs Pillow. Run setup.bat Again And It Installs It.", bg=BG, fg=AMBER,
                 font=(F, 14)).pack(anchor="w", padx=32, pady=8)
    return f


def _ask_key(app) -> str:
    win = tk.Toplevel(app, bg=PANEL, padx=24, pady=20)
    win.title("SteamGridDB Key")
    win.transient(app)
    tk.Label(win, text="Paste Your SteamGridDB API Key", bg=PANEL, fg=FG, font=(F, 15, "bold")).pack(anchor="w")
    v = tk.StringVar()
    e = tk.Entry(win, textvariable=v, show="•", width=44, bg=CARD, fg=FG, insertbackground=FG, relief="flat", font=(F, 14))
    e.pack(pady=12, ipady=6)
    e.focus_set()
    out = {"k": ""}

    def ok():
        out["k"] = v.get()
        win.destroy()
    app.button(win, "Save", ok).pack(anchor="e")
    win.bind("<Return>", lambda _e: ok())
    win.grab_set()
    app.wait_window(win)
    return out["k"]


def _open(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix == "":
        p.mkdir(parents=True, exist_ok=True)
    if p.exists():
        os.startfile(p)
    else:
        messagebox.showinfo(core.APP, "Nothing There Yet. Make Your Icons First.")


# ------------------------------------------------------------------ Games Folder
def _folder(app) -> tk.Frame:
    f = tk.Frame(app, bg=BG)
    _title(f, "A Proper Games Folder",
           "A Games Folder On Your Desktop With A Gaming Icon Of Your Choice. Made For You If You Don't Have One.")
    box = _box(f)
    tk.Label(box, text="1.  Pick An Icon You Like. We Love This Free One By Juicy Fish On Flaticon:", bg=PANEL, fg=FG,
             font=(F, 14)).pack(anchor="w", pady=2)
    app.link(box, "flaticon.com  ·  Game Folder", extras.FOLDER_ICON_PAGE, bg=PANEL).pack(anchor="w", padx=28)
    tk.Label(box, text="     Download The PNG (512 px). Free Icons Ask For A Credit To Their Artist.", bg=PANEL, fg=MUTED,
             font=(F, 13)).pack(anchor="w")
    tk.Label(box, text="2.  Press Choose Icon And Pick The File (PNG Or ICO).", bg=PANEL, fg=FG, font=(F, 14)).pack(anchor="w", pady=(10, 2))
    msg = tk.Label(f, text="", bg=BG, fg=GREEN, font=(F, 15, "bold"))

    def run(work):
        def done(res, err):
            if err:
                messagebox.showerror(core.APP, str(err))
            else:
                msg.configure(text=res)
        app.bg(work, done)

    def choose():
        p = filedialog.askopenfilename(title="Pick A Folder Icon", filetypes=[("Images", "*.png *.ico")])
        if p:
            run(lambda: extras.folder_apply(p))
    row = _row(f)
    app.button(row, "Choose Icon", choose, big=True).pack(side="left")
    app.button(row, "Put It Back", lambda: run(extras.folder_undo), primary=False).pack(side="left", padx=10)
    msg.pack(anchor="w", padx=32)
    _note(f, f"Folder: {extras.games_folder()}")
    return f
