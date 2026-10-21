"""Shu's DLSS 5 Switch - the window. Run: pyw dlss5switch.py (setup.bat does it for you)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dlss5core as core  # noqa: E402

BG, PANEL, ROW, FG, MUTED, ACCENT, OK, BAD = "#14161a", "#1d2026", "#23272e", "#e9e6df", "#9a9a94", "#d9a441", "#7fbf6a", "#d0675b"
OFFSW = "#3a3f47"
F = "Segoe UI"


class Toggle(tk.Canvas):
    """A big pill switch. Clicking it calls on_change(new_state)."""

    def __init__(self, master, on: bool, on_change, enabled=True):
        super().__init__(master, width=78, height=38, bg=ROW, highlightthickness=0, cursor="hand2" if enabled else "")
        self.on, self.on_change, self.enabled = on, on_change, enabled
        self.bind("<Button-1>", self._click)
        self.draw()

    def draw(self):
        self.delete("all")
        col = OK if self.on else OFFSW
        if not self.enabled:
            col = "#2b2f36"
        self.create_oval(2, 2, 36, 36, fill=col, outline=col)
        self.create_oval(42, 2, 76, 36, fill=col, outline=col)
        self.create_rectangle(19, 2, 59, 36, fill=col, outline=col)
        x = 59 if self.on else 19
        self.create_oval(x - 14, 5, x + 14, 33, fill="#f4f2ec", outline="#f4f2ec")

    def _click(self, _e):
        if self.enabled:
            self.on_change(not self.on)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(core.APP)
        self.configure(bg=BG)
        self.geometry("1120x800")
        self.minsize(900, 620)
        self.settings = core.load_settings()
        self.known = core.known_games()
        self.games: list[core.Game] = []
        self.gpu = {}
        self.busy = set()
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.render())
        self.show_cant = False
        self._build()
        self.after(100, self.scan)

    # ------------------------------------------------------------ layout
    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=28, pady=(22, 6))
        tk.Label(top, text=core.APP, bg=BG, fg=FG, font=(F, 24, "bold")).pack(anchor="w")
        tk.Label(top, text="Flick DLSS 5 On For Any Game That Can Take It. Flick It Off And The Game Is Exactly As It Was.",
                 bg=BG, fg=MUTED, font=(F, 12)).pack(anchor="w", pady=(2, 0))

        self.checks = tk.Frame(self, bg=BG)
        self.checks.pack(fill="x", padx=28, pady=(14, 8))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=28, pady=(6, 8))
        tk.Label(bar, text="Search", bg=BG, fg=MUTED, font=(F, 11)).pack(side="left")
        e = tk.Entry(bar, textvariable=self.filter, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=(F, 13), width=30)
        e.pack(side="left", padx=(8, 18), ipady=5)
        self._btn(bar, "Scan Again", self.scan).pack(side="left")
        self._btn(bar, "Add A Games Folder", self.add_folder).pack(side="left", padx=8)
        self.status = tk.Label(bar, text="", bg=BG, fg=MUTED, font=(F, 11))
        self.status.pack(side="right")

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=28, pady=(0, 6))
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

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=28, pady=(4, 16))
        tk.Label(foot, text="In Game: Set The Upscaler To DLSS.  F10 Flicks DLSS 5 On And Off.  "
                            "Insert Opens The Overlay, Which Says Why If It Can't Run.", bg=BG, fg=MUTED, font=(F, 11)).pack(side="left")

    def _btn(self, parent, text, cmd, primary=False):
        b = tk.Label(parent, text=text, bg=ACCENT if primary else PANEL, fg="#14161a" if primary else FG,
                     font=(F, 11, "bold" if primary else "normal"), padx=14, pady=7, cursor="hand2")
        b.bind("<Button-1>", lambda _e: cmd())
        return b

    # ------------------------------------------------------------ the four checks
    def render_checks(self):
        for w in self.checks.winfo_children():
            w.destroy()
        g, m = self.gpu, self.settings.get("model")
        items = [
            ("Graphics Card", g.get("name", "Checking..."), g.get("card_ok"),
             None if g.get("card_ok") else "DLSS 5 Needs An RTX 50 Series Card"),
            ("Driver", g.get("driver") or "Not Found", g.get("driver_ok"),
             None if g.get("driver_ok") else "Update To 616.56 Or Newer"),
            ("DLSS 5 Model", f"Found In {m['from']}" if m else "Not Found Yet", bool(m),
             None if m else "Find It"),
            ("Engine", f"OptiScaler DLSS NR {core.ENGINE['version'].split('-')[0]}" if core.engine_ready() else "Not Downloaded",
             core.engine_ready(), None if core.engine_ready() else "Download (130 MB)"),
        ]
        for i, (label, value, ok, action) in enumerate(items):
            box = tk.Frame(self.checks, bg=PANEL, padx=16, pady=12)
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            self.checks.grid_columnconfigure(i, weight=1, uniform="c")
            head = tk.Frame(box, bg=PANEL)
            head.pack(anchor="w", fill="x")
            tk.Label(head, text="✓" if ok else "✕", bg=PANEL, fg=OK if ok else BAD, font=(F, 14, "bold")).pack(side="left")
            tk.Label(head, text=label, bg=PANEL, fg=MUTED, font=(F, 11)).pack(side="left", padx=(6, 0))
            tk.Label(box, text=value, bg=PANEL, fg=FG, font=(F, 12, "bold"), wraplength=230, justify="left").pack(anchor="w", pady=(4, 0))
            if action:
                if label == "DLSS 5 Model":
                    row = tk.Frame(box, bg=PANEL)
                    row.pack(anchor="w", pady=(8, 0))
                    self._btn(row, action, self.find_model, primary=True).pack(side="left")
                    self._btn(row, "Pick The File", self.pick_model).pack(side="left", padx=(8, 0))
                elif label == "Engine":
                    self._btn(box, action, self.download_engine, primary=True).pack(anchor="w", pady=(8, 0))
                else:
                    tk.Label(box, text=action, bg=PANEL, fg=BAD, font=(F, 11)).pack(anchor="w", pady=(6, 0))

    def ready_to_switch(self) -> bool:
        return bool(self.gpu.get("card_ok") and self.gpu.get("driver_ok") and self.settings.get("model") and core.engine_ready())

    # ------------------------------------------------------------ the game list
    def render(self):
        for w in self.list.winfo_children():
            w.destroy()
        q = self.filter.get().strip().lower()
        shown = [g for g in self.games if q in g.name.lower()]
        on = [g for g in shown if g.state in ("on", "hand")]
        ready = [g for g in shown if g.state == "ready"]
        cant = [g for g in shown if g.state == "cant"]
        self._section(f"On ({len(on)})", on)
        self._section(f"Ready For DLSS 5 ({len(ready)})", ready)
        hdr = tk.Frame(self.list, bg=BG)
        hdr.pack(fill="x", pady=(18, 6))
        tk.Label(hdr, text=f"Can't Run DLSS 5 ({len(cant)})", bg=BG, fg=FG, font=(F, 15, "bold")).pack(side="left")
        self._btn(hdr, "Hide" if self.show_cant else "Show", self.toggle_cant).pack(side="left", padx=12)
        if self.show_cant:
            for g in cant:
                r = tk.Frame(self.list, bg=PANEL, padx=16, pady=9)
                r.pack(fill="x", pady=2)
                tk.Label(r, text=g.name, bg=PANEL, fg=MUTED, font=(F, 12)).pack(side="left")
                tk.Label(r, text=g.why, bg=PANEL, fg=MUTED, font=(F, 11)).pack(side="right")

    def toggle_cant(self):
        self.show_cant = not self.show_cant
        self.render()

    def _section(self, title, games):
        if not games:
            return
        tk.Label(self.list, text=title, bg=BG, fg=FG, font=(F, 15, "bold")).pack(anchor="w", pady=(14, 6))
        for g in games:
            self._row(g)

    def _row(self, g: core.Game):
        r = tk.Frame(self.list, bg=ROW, padx=18, pady=12)
        r.pack(fill="x", pady=3)
        left = tk.Frame(r, bg=ROW)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=g.name, bg=ROW, fg=FG, font=(F, 14, "bold")).pack(anchor="w")
        sub = f"{g.store}  ·  {g.api}" + ("  ·  Tested" if g.tested else "")
        if g.name in self.busy:
            sub += "  ·  Working..."
        tk.Label(left, text=sub, bg=ROW, fg=MUTED, font=(F, 11)).pack(anchor="w")

        right = tk.Frame(r, bg=ROW)
        right.pack(side="right")
        if g.state == "hand":
            tk.Label(left, text="OptiScaler Was Put In By Hand. Take It Over So The Switch Can Turn It Off Cleanly.",
                     bg=ROW, fg=ACCENT, font=(F, 11)).pack(anchor="w", pady=(4, 0))
            self._btn(right, "Take It Over", lambda g=g: self.take_over(g), primary=True).pack(side="left", padx=(0, 12))
        self._btn(right, "Open Folder", lambda g=g: os.startfile(g.folder)).pack(side="left", padx=(0, 14))
        Toggle(right, g.state in ("on", "hand"), lambda v, g=g: self.flip(g, v),
               enabled=g.state != "hand" and g.name not in self.busy and (self.ready_to_switch() or g.state == "on")).pack(side="left")

        if g.state == "on":
            tune = tk.Frame(r, bg=ROW)
            tune.pack(fill="x", side="bottom", pady=(10, 0))
            self._slider(tune, g, "Detail", "TransferStrength", 0.0, 1.5, 1.0,
                         "How Much Of DLSS 5's Picture You Get. 0 Is The Game As It Was.")
            self._slider(tune, g, "Colour", "ColourStrength", 0.0, 1.0, 1.0,
                         "0 Keeps The Game's Own Colours, 1 Takes DLSS 5's.")

    def _slider(self, parent, g, label, key, lo, hi, default, tip):
        f = tk.Frame(parent, bg=ROW)
        f.pack(side="left", padx=(0, 30))
        tk.Label(f, text=label, bg=ROW, fg=FG, font=(F, 11, "bold")).pack(anchor="w")
        cur = core.get_ini(g.folder, key)
        v = tk.DoubleVar(value=default if cur == "auto" else float(cur))
        s = tk.Scale(f, from_=lo, to=hi, resolution=0.05, orient="horizontal", variable=v, length=240, showvalue=True,
                     bg=ROW, fg=FG, troughcolor=PANEL, highlightthickness=0, activebackground=ACCENT, font=(F, 10))
        s.pack(anchor="w")
        s.bind("<ButtonRelease-1>", lambda _e: self.tune(g, key, v.get()))
        tk.Label(f, text=tip, bg=ROW, fg=MUTED, font=(F, 10)).pack(anchor="w")

    # ------------------------------------------------------------ actions
    def bg(self, work, done):
        def run():
            try:
                res = work()
                self.after(0, lambda: done(res, None))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda e=e: done(None, e))
        threading.Thread(target=run, daemon=True).start()

    def scan(self):
        self.status.configure(text="Looking At Your Games...")

        def work():
            gpu = core.gpu()
            games = [core.judge(n, r, s, self.known) for n, r, s in core.all_games(self.settings)]
            return gpu, games

        def done(res, err):
            if err:
                messagebox.showerror(core.APP, str(err))
                return
            self.gpu, self.games = res
            n_ready = sum(g.state == "ready" for g in self.games)
            self.status.configure(text=f"{len(self.games)} Games Found, {n_ready} Can Take DLSS 5")
            self.render_checks()
            self.render()
            if not self.settings.get("model"):
                self.find_model()
        self.bg(work, done)

    def find_model(self):
        self.status.configure(text="Looking For NVIDIA's DLSS 5 Model In Your Games...")
        candidates = [g for g in self.games if g.folder] or self.games

        def done(m, err):
            if err:
                messagebox.showerror(core.APP, str(err))
                return
            self.settings["model"] = m
            core.save_settings(self.settings)
            self.status.configure(text="DLSS 5 Model Found" if m else "No DLSS 5 Model On This PC")
            if not m:
                messagebox.showinfo(core.APP, "DLSS 5's model file (nvngx_dlssnr.dll) wasn't found in any of your games.\n\n"
                                    "It ships inside games that have DLSS 5 built in. Install one, then press Find It again.\n"
                                    "This switch never downloads it: it only uses NVIDIA's own signed copy.")
            self.render_checks()
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
            self.status.configure(text="DLSS 5 Model Found")
            self.render_checks()
            self.render()
        self.bg(lambda: core.model_from_file(Path(f)), done)

    def download_engine(self):
        self.status.configure(text="Downloading The Engine...")

        def prog(f):
            self.after(0, lambda: self.status.configure(text=f"Downloading The Engine... {int(f * 100)}%"))

        def done(_r, err):
            if err:
                messagebox.showerror(core.APP, str(err))
            self.status.configure(text="Engine Ready" if core.engine_ready() else "")
            self.render_checks()
            self.render()
        self.bg(lambda: core.get_engine(prog), done)

    def flip(self, g: core.Game, on: bool):
        self.busy.add(g.name)
        self.render()

        def work():
            if on:
                core.turn_on(g, self.settings["model"])
            else:
                core.turn_off(g)
            return core.judge(g.name, g.root, g.store, self.known)

        def done(new, err):
            self.busy.discard(g.name)
            if err:
                messagebox.showerror(core.APP, f"{g.name}\n\n{err}")
            else:
                self.games[self.games.index(g)] = new
                self.status.configure(text=f"DLSS 5 {'On' if on else 'Off'} For {g.name}")
            self.render()
        self.bg(work, done)

    def take_over(self, g: core.Game):
        if messagebox.askyesno(core.APP, f"Take over the OptiScaler files already in {g.name}?\n\n"
                                         "Nothing is changed now. The switch just learns which files they are, "
                                         "so turning it off removes them cleanly."):
            core.take_over(g)
            self.games[self.games.index(g)] = core.judge(g.name, g.root, g.store, self.known)
            self.render()

    def tune(self, g: core.Game, key: str, value: float):
        try:
            core.set_tuning(g.folder, key, f"{value:.2f}")
            self.status.configure(text=f"Saved. Restart {g.name} Or Change It Live In The Overlay.")
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
