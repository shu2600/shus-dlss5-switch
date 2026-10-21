"""Shu's DLSS 5 Switch - the window. Run: pyw dlss5switch.py (setup.bat does it for you and makes a desktop shortcut)."""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dlss5core as core  # noqa: E402

# Shu's colours: the cyan comes from the Shu logo
BG, PANEL, CARD, FG, MUTED = "#101317", "#181c22", "#1e232a", "#f1efe9", "#9aa0a6"
CYAN, CYAN_DARK, GREEN, RED, AMBER = "#10bad8", "#07a6c7", "#5fd38d", "#e0705f", "#e6b24a"
OFF_TRACK = "#3a414b"
F = "Segoe UI"
SITE, GITHUB = "https://shuhq.com", "https://github.com/shu2600/shus-dlss5-switch"
ASSETS = next((d for d in (HERE.parent / "assets", HERE / "assets") if d.is_dir()), HERE / "assets")


class Switch(tk.Canvas):
    """A big ON / OFF switch with the word beside it. Clicking it calls on_change(new_state)."""

    def __init__(self, master, on: bool, on_change, enabled=True, bg=CARD):
        super().__init__(master, width=170, height=56, bg=bg, highlightthickness=0, cursor="hand2" if enabled else "")
        self.on, self.on_change, self.enabled, self.bgc = on, on_change, enabled, bg
        self.bind("<Button-1>", lambda _e: self.enabled and self.on_change(not self.on))
        self.draw()

    def draw(self):
        self.delete("all")
        col = (GREEN if self.on else OFF_TRACK) if self.enabled else "#2a2f36"
        x0, y0, x1, y1, r = 4, 6, 100, 50, 22
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=col, outline=col)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=col, outline=col)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=col, outline=col)
        kx = x1 - r if self.on else x0 + r
        self.create_oval(kx - 18, y0 + 4, kx + 18, y1 - 4, fill="#ffffff", outline="#ffffff")
        word = "ON" if self.on else "OFF"
        self.create_text(112, 28, text=word, anchor="w", fill=GREEN if self.on else MUTED, font=(F, 18, "bold"))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(core.APP)
        self.configure(bg=BG)
        self.geometry("1180x860")
        self.minsize(980, 680)
        self.settings = core.load_settings()
        self.known = core.known_games()
        self.games: list[core.Game] = []
        self.gpu: dict = {}
        self.busy: set[str] = set()
        self.tuning: set[str] = set()
        self.show_cant = False
        self.scanning = True
        self.imgs: dict[str, tk.PhotoImage] = {}
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.render())
        self._build()
        self.after(100, self.scan)

    # ------------------------------------------------------------ pieces
    def img(self, name):
        if name not in self.imgs:
            try:
                self.imgs[name] = tk.PhotoImage(file=str(ASSETS / name))
            except tk.TclError:
                self.imgs[name] = None
        return self.imgs[name]

    def button(self, parent, text, cmd, big=False, primary=True, bg=None):
        b = tk.Label(parent, text=text, bg=(CYAN if primary else (bg or PANEL)), fg=("#06222a" if primary else FG),
                     font=(F, 15 if big else 13, "bold" if primary else "normal"),
                     padx=26 if big else 16, pady=12 if big else 8, cursor="hand2")
        b.bind("<Button-1>", lambda _e: cmd())
        b.bind("<Enter>", lambda _e: b.configure(bg=CYAN_DARK if primary else "#2a3038"))
        b.bind("<Leave>", lambda _e: b.configure(bg=CYAN if primary else (bg or PANEL)))
        return b

    def link(self, parent, text, url, bg=BG, size=13):
        l = tk.Label(parent, text=text, bg=bg, fg=CYAN, font=(F, size, "underline"), cursor="hand2")
        l.bind("<Button-1>", lambda _e: webbrowser.open(url))
        return l

    # ------------------------------------------------------------ layout
    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=32, pady=(20, 4))
        if self.img("shu_logo_ui.png"):
            tk.Label(head, image=self.img("shu_logo_ui.png"), bg=BG).pack(side="left", padx=(0, 18))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="DLSS 5 Switch", bg=BG, fg=FG, font=(F, 30, "bold")).pack(anchor="w")
        tk.Label(titles, text="Turn DLSS 5 On For Your Games. One Switch Each.", bg=BG, fg=MUTED, font=(F, 14)).pack(anchor="w")
        right = tk.Frame(head, bg=BG)
        right.pack(side="right")
        if self.img("anima_logo_ui.png"):
            tk.Label(right, image=self.img("anima_logo_ui.png"), bg=BG).pack(anchor="e")
        self.link(right, "shuhq.com", SITE).pack(anchor="e", pady=(6, 0))

        self.setup = tk.Frame(self, bg=BG)
        self.setup.pack(fill="x", padx=32, pady=(14, 6))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=32, pady=(8, 6))
        tk.Label(bar, text="\U0001F50E", bg=BG, fg=MUTED, font=(F, 14)).pack(side="left")
        e = tk.Entry(bar, textvariable=self.filter, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=(F, 15), width=26)
        e.pack(side="left", padx=(8, 16), ipady=7)
        self.button(bar, "Look Again", self.scan, primary=False).pack(side="left")
        self.button(bar, "Add A Games Folder", self.add_folder, primary=False).pack(side="left", padx=8)
        self.status = tk.Label(bar, text="", bg=BG, fg=MUTED, font=(F, 13))
        self.status.pack(side="right")

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=32, pady=(4, 4))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.list = tk.Frame(self.canvas, bg=BG)
        self.list.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.list, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill="x", side="bottom")
        inner = tk.Frame(foot, bg=PANEL)
        inner.pack(fill="x", padx=32, pady=10)
        tk.Label(inner, text="In Game:  Set The Upscaler To DLSS   ·   F10 Flicks DLSS 5 On And Off   ·   Insert Opens The Overlay",
                 bg=PANEL, fg=FG, font=(F, 13)).pack(side="left")
        credit = tk.Frame(inner, bg=PANEL)
        credit.pack(side="right")
        for n in ("shu_logo_small.png", "anima_logo_small.png"):
            if self.img(n):
                tk.Label(credit, image=self.img(n), bg=PANEL).pack(side="left", padx=4)
        tk.Label(credit, text="Built By Shu And Anima  · ", bg=PANEL, fg=MUTED, font=(F, 12)).pack(side="left", padx=(6, 0))
        self.link(credit, "shuhq.com", SITE, bg=PANEL, size=12).pack(side="left")
        tk.Label(credit, text=" · ", bg=PANEL, fg=MUTED, font=(F, 12)).pack(side="left")
        self.link(credit, "GitHub", GITHUB, bg=PANEL, size=12).pack(side="left")

    # ------------------------------------------------------------ getting set up
    def all_set(self) -> bool:
        return bool(self.gpu.get("card_ok") and self.gpu.get("driver_ok") and self.settings.get("model") and core.engine_ready())

    def render_setup(self):
        for w in self.setup.winfo_children():
            w.destroy()
        if self.scanning and not self.gpu:
            tk.Label(self.setup, text="Looking At Your PC And Your Games...", bg=BG, fg=FG, font=(F, 18)).pack(anchor="w")
            return
        g, m = self.gpu, self.settings.get("model")
        if self.all_set():
            box = tk.Frame(self.setup, bg=PANEL, padx=20, pady=14)
            box.pack(fill="x")
            tk.Label(box, text="✓  All Set", bg=PANEL, fg=GREEN, font=(F, 18, "bold")).pack(side="left")
            tk.Label(box, text=f"{g['name'].replace('NVIDIA GeForce ', '')}   ·   Driver {g['driver']}   ·   "
                               f"DLSS 5 Model From {m['from']}   ·   Engine Ready",
                     bg=PANEL, fg=MUTED, font=(F, 13)).pack(side="left", padx=18)
            return
        box = tk.Frame(self.setup, bg=PANEL, padx=24, pady=18)
        box.pack(fill="x")
        tk.Label(box, text="Let's Get You Set Up", bg=PANEL, fg=FG, font=(F, 20, "bold")).pack(anchor="w", pady=(0, 10))
        steps = [
            ("Your Graphics Card", g.get("card_ok"), g.get("name", ""), None,
             "DLSS 5 Needs An NVIDIA RTX 50 Series Card."),
            ("Your Driver", g.get("driver_ok"), f"Driver {g.get('driver') or 'Not Found'}", None,
             "Update Your NVIDIA Driver To 616.56 Or Newer, Then Press Look Again."),
            ("The DLSS 5 Model", bool(m), f"Found In {m['from']}" if m else "", "model",
             "It Comes Inside Games That Ship DLSS 5. We Look For It On Your PC, Never Download It."),
            ("The Engine", core.engine_ready(), "OptiScaler DLSS NR, Downloaded And Checked", "engine",
             "A One-Off 130 MB Download From Its Author's GitHub, Checked Before Use."),
        ]
        first_missing = next((i for i, s in enumerate(steps) if not s[1]), None)
        for i, (title, ok, detail, action, help_) in enumerate(steps):
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill="x", pady=5)
            mark = "✓" if ok else str(i + 1)
            tk.Label(row, text=mark, bg=GREEN if ok else (CYAN if i == first_missing else OFF_TRACK), fg="#06222a",
                     font=(F, 15, "bold"), width=3, pady=4).pack(side="left")
            txt = tk.Frame(row, bg=PANEL)
            txt.pack(side="left", padx=14)
            tk.Label(txt, text=title, bg=PANEL, fg=FG if (ok or i == first_missing) else MUTED,
                     font=(F, 16, "bold")).pack(anchor="w")
            tk.Label(txt, text=detail if ok else help_, bg=PANEL, fg=MUTED, font=(F, 13)).pack(anchor="w")
            if not ok and i == first_missing and action:
                acts = tk.Frame(row, bg=PANEL)
                acts.pack(side="right")
                if action == "model":
                    self.button(acts, "Find It For Me", self.find_model, big=True).pack(side="left")
                    self.button(acts, "I'll Pick The File", self.pick_model, primary=False, bg="#2a3038").pack(side="left", padx=10)
                else:
                    self.button(acts, "Download The Engine", self.download_engine, big=True).pack(side="left")

    # ------------------------------------------------------------ the games
    def render(self):
        for w in self.list.winfo_children():
            w.destroy()
        if not self.games:
            return
        q = self.filter.get().strip().lower()
        shown = [g for g in self.games if q in g.name.lower()]
        on = [g for g in shown if g.state == "on"]
        ready = [g for g in shown if g.state in ("ready", "hand")]
        cant = [g for g in shown if g.state == "cant"]
        if on:
            self._heading("DLSS 5 Is On", len(on), GREEN)
            for g in on:
                self._card(g)
        self._heading("Ready To Go", len(ready), CYAN)
        if not self.all_set() and ready:
            tk.Label(self.list, text="Finish The Set Up Above And These Switches Wake Up.", bg=BG, fg=AMBER,
                     font=(F, 13)).pack(anchor="w", pady=(0, 6))
        for g in ready:
            self._card(g)
        if not ready:
            tk.Label(self.list, text="No Games Ready Yet. Press Add A Games Folder If Yours Live Somewhere Else.",
                     bg=BG, fg=MUTED, font=(F, 13)).pack(anchor="w")
        hdr = tk.Frame(self.list, bg=BG)
        hdr.pack(fill="x", pady=(22, 6))
        tk.Label(hdr, text=f"Can't Use DLSS 5  ({len(cant)})", bg=BG, fg=MUTED, font=(F, 17, "bold")).pack(side="left")
        self.button(hdr, "Hide" if self.show_cant else "Show Me Why", self.toggle_cant, primary=False).pack(side="left", padx=14)
        if self.show_cant:
            for g in cant:
                r = tk.Frame(self.list, bg=PANEL, padx=18, pady=10)
                r.pack(fill="x", pady=2)
                tk.Label(r, text=g.name, bg=PANEL, fg=FG, font=(F, 14)).pack(side="left")
                tk.Label(r, text=g.why, bg=PANEL, fg=MUTED, font=(F, 13)).pack(side="right")

    def _heading(self, text, n, colour):
        h = tk.Frame(self.list, bg=BG)
        h.pack(fill="x", pady=(16, 8))
        tk.Label(h, text=text, bg=BG, fg=FG, font=(F, 19, "bold")).pack(side="left")
        tk.Label(h, text=f" {n} ", bg=colour, fg="#06222a", font=(F, 13, "bold")).pack(side="left", padx=12)

    def _card(self, g: core.Game):
        on = g.state == "on"
        card = tk.Frame(self.list, bg=CARD, padx=22, pady=16)
        card.pack(fill="x", pady=5)
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        left = tk.Frame(top, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=g.name, bg=CARD, fg=FG, font=(F, 18, "bold")).pack(anchor="w")
        if g.name in self.busy:
            line, col = "Working On It...", AMBER
        elif on:
            line, col = "DLSS 5 Is On.  Start The Game, Set The Upscaler To DLSS, Press F10 To Compare.", GREEN
        else:
            line, col = "Ready.  Flick The Switch To Turn DLSS 5 On.", MUTED
        tk.Label(left, text=line, bg=CARD, fg=col, font=(F, 13)).pack(anchor="w", pady=(2, 0))
        extras = tk.Frame(left, bg=CARD)
        extras.pack(anchor="w", pady=(6, 0))
        tk.Label(extras, text=f"{g.store}  ·  {g.api}" + ("  ·  Tested" if g.tested else ""),
                 bg=CARD, fg="#6f767e", font=(F, 12)).pack(side="left")
        self.link(extras, "Open Folder", g.folder.as_uri(), bg=CARD, size=12).pack(side="left", padx=14)
        if on:
            self.link_btn(extras, "Fine Tune ▾" if g.name not in self.tuning else "Fine Tune ▴",
                          lambda g=g: self.toggle_tune(g)).pack(side="left")
        Switch(top, on, lambda v, g=g: self.flip(g, v),
               enabled=g.name not in self.busy and (self.all_set() or on)).pack(side="right")
        if on and g.name in self.tuning:
            tune = tk.Frame(card, bg=CARD)
            tune.pack(fill="x", pady=(14, 0))
            self._slider(tune, g, "Detail", "TransferStrength", 0.0, 1.5, 1.0, "0 = The Game As It Was.  1 = Full DLSS 5.")
            self._slider(tune, g, "Colour", "ColourStrength", 0.0, 1.0, 1.0, "0 = The Game's Own Colours.  1 = DLSS 5's.")

    def link_btn(self, parent, text, cmd):
        l = tk.Label(parent, text=text, bg=CARD, fg=CYAN, font=(F, 12, "underline"), cursor="hand2")
        l.bind("<Button-1>", lambda _e: cmd())
        return l

    def _slider(self, parent, g, label, key, lo, hi, default, tip):
        f = tk.Frame(parent, bg=CARD)
        f.pack(side="left", padx=(0, 40))
        tk.Label(f, text=label, bg=CARD, fg=FG, font=(F, 14, "bold")).pack(anchor="w")
        cur = core.get_ini(g.folder, key)
        v = tk.DoubleVar(value=default if cur == "auto" else float(cur))
        s = tk.Scale(f, from_=lo, to=hi, resolution=0.05, orient="horizontal", variable=v, length=280, showvalue=True,
                     bg=CARD, fg=FG, troughcolor=PANEL, highlightthickness=0, activebackground=CYAN, font=(F, 12), sliderlength=26)
        s.pack(anchor="w")
        s.bind("<ButtonRelease-1>", lambda _e: self.tune(g, key, v.get()))
        tk.Label(f, text=tip, bg=CARD, fg=MUTED, font=(F, 12)).pack(anchor="w")

    def toggle_cant(self):
        self.show_cant = not self.show_cant
        self.render()

    def toggle_tune(self, g):
        self.tuning ^= {g.name}
        self.render()

    # ------------------------------------------------------------ work
    def bg(self, work, done):
        def run():
            try:
                res = work()
                self.after(0, lambda: done(res, None))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda e=e: done(None, e))
        threading.Thread(target=run, daemon=True).start()

    def scan(self):
        self.scanning = True
        self.status.configure(text="Looking At Your Games...")
        self.render_setup()

        def work():
            gpu = core.gpu()
            games = [core.judge(n, r, s, self.known) for n, r, s in core.all_games(self.settings)]
            for i, g in enumerate(games):  # an install done by hand becomes a normal "On" game (only a list is written)
                if g.state == "hand":
                    core.take_over(g)
                    games[i] = core.judge(g.name, g.root, g.store, self.known)
            return gpu, games

        def done(res, err):
            self.scanning = False
            if err:
                messagebox.showerror(core.APP, str(err))
                return
            self.gpu, self.games = res
            m = self.settings.get("model")
            if m and not Path(m["path"]).is_file():
                self.settings["model"] = None
                core.save_settings(self.settings)
            n_ready = sum(g.state == "ready" for g in self.games)
            self.status.configure(text=f"{len(self.games)} Games  ·  {n_ready} Ready")
            self.render_setup()
            self.render()
            if not self.settings.get("model"):
                self.find_model(quiet=True)
        self.bg(work, done)

    def find_model(self, quiet=False):
        self.status.configure(text="Looking For The DLSS 5 Model...")
        candidates = [g for g in self.games if g.folder] or self.games

        def done(m, err):
            if err:
                messagebox.showerror(core.APP, str(err))
                return
            if m:
                self.settings["model"] = m
                core.save_settings(self.settings)
                self.status.configure(text="Found The DLSS 5 Model")
            else:
                self.status.configure(text="")
                if not quiet:
                    messagebox.showinfo(core.APP, "We Couldn't Find The DLSS 5 Model On This PC.\n\n"
                                        "It Comes Inside Games That Ship DLSS 5 (For Example NBA 2K27). "
                                        "Install One, Then Press Find It For Me Again, Or Press I'll Pick The File.")
            self.render_setup()
            self.render()
        self.bg(lambda: core.find_model(candidates), done)

    def pick_model(self):
        f = filedialog.askopenfilename(title="Pick nvngx_dlssnr.dll (About 165 MB)",
                                       filetypes=[("DLSS 5 model", "nvngx_dlssnr.dll"), ("DLL files", "*.dll")])
        if not f:
            return
        self.status.configure(text="Checking NVIDIA's Signature...")

        def done(m, err):
            if err:
                messagebox.showerror(core.APP, str(err))
                self.status.configure(text="")
                return
            self.settings["model"] = m
            core.save_settings(self.settings)
            self.status.configure(text="Found The DLSS 5 Model")
            self.render_setup()
            self.render()
        self.bg(lambda: core.model_from_file(Path(f)), done)

    def download_engine(self):
        def prog(f):
            self.after(0, lambda: self.status.configure(text=f"Downloading The Engine...  {int(f * 100)}%"))

        def done(_r, err):
            if err:
                messagebox.showerror(core.APP, str(err))
            self.status.configure(text="Engine Ready" if core.engine_ready() else "")
            self.render_setup()
            self.render()
        self.status.configure(text="Downloading The Engine...")
        self.bg(lambda: core.get_engine(prog), done)

    def flip(self, g: core.Game, on: bool):
        self.busy.add(g.name)
        self.render()

        def work():
            core.turn_on(g, self.settings["model"]) if on else core.turn_off(g)
            return core.judge(g.name, g.root, g.store, self.known)

        def done(new, err):
            self.busy.discard(g.name)
            if err:
                messagebox.showerror(core.APP, f"{g.name}\n\n{err}")
            else:
                self.games[self.games.index(g)] = new
                self.status.configure(text=f"DLSS 5 {'On' if on else 'Off'}  ·  {g.name}")
            self.render()
        self.bg(work, done)

    def tune(self, g: core.Game, key: str, value: float):
        try:
            core.set_tuning(g.folder, key, f"{value:.2f}")
            self.status.configure(text=f"Saved  ·  Takes Effect Next Time {g.name} Starts")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(core.APP, str(e))

    def add_folder(self):
        d = filedialog.askdirectory(title="Pick A Folder That Holds Games")
        if d:
            self.settings.setdefault("extra_folders", []).append(str(Path(d)))
            core.save_settings(self.settings)
            self.scan()


if __name__ == "__main__":
    App().mainloop()
