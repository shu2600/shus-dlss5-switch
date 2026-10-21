"""Shu's DLSS 5 Switch - the engine room: find games, judge them, install and remove.

Nothing here ships or downloads NVIDIA's model. The model (nvngx_dlssnr.dll) is found on this PC,
in a game that already has it, and is only used if NVIDIA's signature on it checks out.
The OptiScaler DLSS NR engine (GPL-3.0, github.com/Dagherbou/OptiScaler_DLSSNR) is downloaded from
its own GitHub release and refused unless its SHA-256 matches the one pinned below.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import winreg
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

APP = "Shu's DLSS 5 Switch"
HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ShusDLSS5Switch"
SETTINGS = HOME / "switch_settings.json"
HERE = Path(__file__).resolve().parent
NO_WINDOW = 0x08000000

ENGINE = {
    "version": "v0.2.0-dlssnr",
    "url": "https://github.com/Dagherbou/OptiScaler_DLSSNR/releases/download/v0.2.0-dlssnr/OptiScaler-DLSSNR-v0.2.0.zip",
    "sha256": "8eece7a4d7de6de5917f0c99ac60540b2d77022e7699bba717b0a6d9e1829bce",
}
ENGINE_SKIP = {"setup_windows.bat", "setup_linux.sh", "!! extract all files to game folder !!"}
MODEL = "nvngx_dlssnr.dll"
MANIFEST = ".dlss5switch.json"
PROXIES = ["dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "wininet.dll", "winhttp.dll"]
MIN_DRIVER = (616, 56)
TOGGLE_KEY = "0x79"  # F10: flicks the DLSS 5 pass on and off in game (Windows virtual-key code)

ANTI_CHEAT = [  # (pattern on any file or folder name, lower case) -> name shown to the user
    (r"^easyanticheat", "Easy Anti-Cheat"), (r"^start_protected_game\.exe$", "Easy Anti-Cheat"),
    (r"^battleye$", "BattlEye"), (r"^beservice", "BattlEye"), (r"^bedaisy", "BattlEye"),
    (r"^eaanticheat", "EA Javelin"), (r"^vgk\.sys$|^vgc\.exe$", "Riot Vanguard"),
    (r"^gameguard|^npgg|^nprotect", "nProtect GameGuard"), (r"^xigncode", "XIGNCODE"),
    (r"^mhyprot", "miHoYo anti-cheat"), (r"^ace-base|^sguard", "ACE anti-cheat"),
    (r"^pnkbstr|^punkbuster", "PunkBuster"), (r"^ricochet", "Ricochet"),
]


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - first run or a hand-edited file
        return {"extra_folders": [], "model": None}


def save_settings(s: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def known_games() -> list[dict]:
    try:
        return json.loads((HERE / "games.json").read_text(encoding="utf-8"))["games"]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------- the PC
def log(msg: str) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with (HOME / "switch_log.txt").open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def run(cmd: list[str], timeout: int = 60) -> str:
    try:
        env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}  # PS7's paths break Windows PowerShell
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, env=env)
        if r.stderr.strip():
            log(f"stderr {cmd[:2]}: {r.stderr.strip()[:400]}")
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        log(f"run failed {cmd[:3]}: {e!r}")
        return ""


def gpu() -> dict:
    """Card name, driver version, and whether both are good enough."""
    out = run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if not out:
        return {"name": "No NVIDIA card found", "driver": "", "card_ok": False, "driver_ok": False}
    name, _, drv = out.splitlines()[0].partition(",")
    name, drv = name.strip(), drv.strip()
    m = re.match(r"(\d+)\.(\d+)", drv)
    ver = (int(m[1]), int(m[2])) if m else (0, 0)
    return {"name": name, "driver": drv, "card_ok": bool(re.search(r"RTX\s*50\d\d", name)),
            "driver_ok": ver >= MIN_DRIVER}


def psq(p: Path | str) -> str:
    """A path as a PowerShell single-quoted literal (powershell -Command does not pass $args)."""
    return "'" + str(p).replace("'", "''") + "'"


def signature(path: Path) -> dict:
    """NVIDIA's Authenticode signature and the file's own description."""
    ps = (f"$p={psq(path)}; "
          "$s=Get-AuthenticodeSignature -LiteralPath $p; $v=(Get-Item -LiteralPath $p).VersionInfo; "
          "'{0}|{1}|{2}|{3}' -f $s.Status, $s.SignerCertificate.Subject, $v.FileDescription, $v.FileVersion")
    out = run(["powershell", "-NoProfile", "-Command", ps], timeout=300)
    status, subject, desc, ver = (out.split("|") + ["", "", "", ""])[:4]
    log(f"signature {path}: {out or '<no output>'}")
    ok = status == "Valid" and "NVIDIA Corporation" in subject and "DLSSNR" in desc.upper().replace(" ", "")
    return {"ok": ok, "status": status, "signer": subject, "description": desc, "version": ver}


# ---------------------------------------------------------------- libraries
def _reg(root, key: str, value: str) -> str | None:
    try:
        with winreg.OpenKey(root, key) as k:
            return winreg.QueryValueEx(k, value)[0]
    except OSError:
        return None


def _subkeys(root, key: str):
    try:
        with winreg.OpenKey(root, key) as k:
            i = 0
            while True:
                try:
                    yield key + "\\" + winreg.EnumKey(k, i)
                except OSError:
                    return
                i += 1
    except OSError:
        return


def steam_games() -> list[tuple[str, Path, str]]:
    steam = _reg(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")
    if not steam:
        return []
    libs = {Path(steam)}
    vdf = Path(steam) / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
            libs.add(Path(p.replace("\\\\", "\\")))
    out = []
    for lib in libs:
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            t = acf.read_text(encoding="utf-8", errors="ignore")
            name = re.search(r'"name"\s+"([^"]+)"', t)
            inst = re.search(r'"installdir"\s+"([^"]+)"', t)
            if name and inst:
                d = lib / "steamapps" / "common" / inst[1]
                if d.is_dir():
                    out.append((name[1], d, "Steam"))
    return out


def gog_games() -> list[tuple[str, Path, str]]:
    out = []
    for k in _subkeys(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games"):
        name, path = _reg(winreg.HKEY_LOCAL_MACHINE, k, "gameName"), _reg(winreg.HKEY_LOCAL_MACHINE, k, "path")
        if name and path and Path(path).is_dir():
            out.append((name, Path(path), "GOG"))
    return out


def epic_games() -> list[tuple[str, Path, str]]:
    out = []
    for f in Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests").glob("*.item"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if Path(j["InstallLocation"]).is_dir():
                out.append((j["DisplayName"], Path(j["InstallLocation"]), "Epic"))
        except Exception:  # noqa: BLE001
            pass
    return out


def ubisoft_games() -> list[tuple[str, Path, str]]:
    out = []
    for k in _subkeys(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"):
        p = _reg(winreg.HKEY_LOCAL_MACHINE, k, "InstallDir")
        if p and Path(p).is_dir():
            out.append((Path(p).name, Path(p), "Ubisoft"))
    return out


def ea_games() -> list[tuple[str, Path, str]]:
    out = []
    for base in (r"SOFTWARE\WOW6432Node\Electronic Arts", r"SOFTWARE\WOW6432Node\EA Games"):
        for k in _subkeys(winreg.HKEY_LOCAL_MACHINE, base):
            p = _reg(winreg.HKEY_LOCAL_MACHINE, k, "Install Dir")
            if p and Path(p).is_dir():
                out.append((k.rsplit("\\", 1)[1], Path(p), "EA"))
    return out


def folder_games(folders: list[str]) -> list[tuple[str, Path, str]]:
    out = []
    for f in folders:
        p = Path(f)
        if p.is_dir():
            for d in sorted(p.iterdir()):
                if d.is_dir() and not d.name.startswith((".", "$")):
                    out.append((d.name, d, "Folder"))
    return out


def all_games(settings: dict) -> list[tuple[str, Path, str]]:
    seen, out = set(), []
    for src in (steam_games, gog_games, epic_games, ubisoft_games, ea_games):
        try:
            got = src()
        except Exception:  # noqa: BLE001 - one broken launcher must not hide the rest
            got = []
        for g in got:
            key = str(g[1]).lower().rstrip("\\/")
            if key not in seen and "redistributable" not in g[0].lower():
                seen.add(key)
                out.append(g)
    for g in folder_games(settings.get("extra_folders", [])):
        key = str(g[1]).lower().rstrip("\\/")
        if key not in seen and not any(key.startswith(s + "\\") or s.startswith(key + "\\") for s in seen):
            seen.add(key)
            out.append(g)
    return sorted(out, key=lambda g: g[0].lower())


# ---------------------------------------------------------------- judging one game
@dataclass
class Game:
    name: str
    root: Path
    store: str
    state: str = "cant"          # ready | on | hand | cant
    why: str = ""                # plain reason shown to the user
    folder: Path | None = None   # where the exe is, and where the engine goes
    api: str = ""
    tested: bool = False
    manifest: dict = field(default_factory=dict)


def _walk(root: Path, depth: int = 10):
    stack = [(root, 0)]
    while stack:
        d, n = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            yield e
            if e.is_dir(follow_symlinks=False) and n < depth:
                stack.append((Path(e.path), n + 1))


def _api(exe: Path) -> str:
    try:
        data = exe.read_bytes().lower()
    except OSError:
        return ""
    found = [n for n, k in (("DirectX 12", b"d3d12.dll"), ("DirectX 11", b"d3d11.dll"), ("Vulkan", b"vulkan-1.dll"))
             if k in data]
    return found[0] if found else ""


def judge(name: str, root: Path, store: str, known: list[dict]) -> Game:
    g = Game(name, root, store)
    k = next((x for x in known if x["match"].lower() in name.lower()), None)
    if k and k.get("status") == "blocked":
        g.why = k["why"]
        return g
    exes, dlss, cheat = [], [], None
    for e in _walk(root):
        n = e.name.lower()
        if cheat is None:
            for pat, label in ANTI_CHEAT:
                if re.search(pat, n):
                    cheat = label
                    break
        if e.is_file(follow_symlinks=False):
            if n in ("nvngx_dlss.dll", "sl.dlss.dll"):
                dlss.append(Path(e.path).parent)
            elif n.endswith(".exe") and not re.search(r"unins|crash|setup|redist|vc_|dxsetup|launcher|helper|report|install|update", n):
                exes.append(Path(e.path))
    if cheat:
        g.why = f"{cheat}: touching it could get you banned, so it's left alone"
        return g
    if not dlss:
        g.why = "This game has no DLSS for DLSS 5 to work through"
        return g
    folder = None
    if k and k.get("folder"):
        folder = root / k["folder"]
    if not folder or not folder.is_dir():
        shipping = [x for x in exes if x.name.lower().endswith("-shipping.exe")]  # Unreal: the game's real exe
        with_exe = [d for d in dlss if any(x.parent == d for x in exes)]
        if shipping:
            folder = max(shipping, key=lambda x: x.stat().st_size).parent
        elif with_exe:
            folder = with_exe[0]
        else:
            folder = max(exes, key=lambda x: x.stat().st_size).parent if exes else None
    if not folder:
        g.why = "Couldn't find the game's .exe"
        return g
    g.folder = folder
    main = [x for x in exes if x.parent == folder]
    g.api = _api(max(main, key=lambda x: x.stat().st_size)) if main else ""
    if g.api == "":
        g.api = "DirectX 12"  # DLSS titles are DX11/12/Vulkan; the engine reports in its overlay if not
    g.tested = bool(k and k.get("status") == "works")
    man = folder / MANIFEST
    if man.is_file():
        g.manifest = json.loads(man.read_text(encoding="utf-8"))
        g.state = "on"
    elif any((folder / p).is_file() and _is_opti(folder / p) for p in PROXIES):
        g.state = "hand"
        g.why = "OptiScaler is already here, put in by hand"
    else:
        g.state = "ready"
    return g


def _is_opti(p: Path) -> bool:
    out = run(["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath {psq(p)}).VersionInfo.OriginalFilename"])
    return out.strip().lower() == "optiscaler.dll"


# ---------------------------------------------------------------- the model
def find_model(games: list[Game], progress=None) -> dict | None:
    """Look for NVIDIA's signed nvngx_dlssnr.dll in games already on this PC."""
    seen = set()
    for g in games:
        if progress:
            progress(g.name)
        for e in _walk(g.root):
            if e.name.lower() == MODEL and e.is_file():
                p = Path(e.path)
                if p.stat().st_size < 100_000_000 or str(p).lower() in seen:
                    continue
                seen.add(str(p).lower())
                s = signature(p)
                if s["ok"]:
                    return keep_model(p, g.name, s["version"])
    return None


def keep_model(p: Path, source: str, version: str) -> dict:
    """Keep the Switch's own copy of the user's signed model, so turning a game off can never take it away."""
    dest = HOME / "model" / MODEL
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = sha256(p)
    if not dest.is_file() or sha256(dest) != h:
        shutil.copy2(p, dest)
    if sha256(dest) != h or not signature(dest)["ok"]:
        raise RuntimeError("Couldn't keep a clean copy of the DLSS 5 model")
    return {"path": str(dest), "from": source, "version": version, "sha256": h}


def model_from_file(p: Path) -> dict:
    """The user pointed at a file: accept it only if it's NVIDIA's signed DLSS 5 model."""
    p = Path(p)
    if p.name.lower() != MODEL:
        raise RuntimeError(f"That file isn't {MODEL}.")
    s = signature(p)
    if not s["ok"]:
        raise RuntimeError("That file isn't NVIDIA's signed DLSS 5 model "
                           f"(signature: {s['status'] or 'none'}, description: {s['description'] or 'none'}), so it won't be used.")
    return keep_model(p, p.parent.name, s["version"])


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- the engine
def engine_dir() -> Path:
    return HOME / "engine" / ENGINE["version"]


def engine_ready() -> bool:
    return (engine_dir() / "OptiScaler.dll").is_file() and (engine_dir() / "OptiScaler.ini").is_file()


def get_engine(progress=None) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    zpath = HOME / "engine.zip"
    with urllib.request.urlopen(ENGINE["url"], timeout=120) as r, zpath.open("wb") as f:
        total, done = int(r.headers.get("Content-Length", 0)), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if sha256(zpath) != ENGINE["sha256"]:
        zpath.unlink()
        raise RuntimeError("The engine download didn't match its published fingerprint, so it was thrown away.")
    tmp = engine_dir().with_name(ENGINE["version"] + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            dest = (tmp / m.filename).resolve()
            if not str(dest).startswith(str(tmp.resolve())):
                raise RuntimeError("Unsafe path in the engine zip")
        z.extractall(tmp)
    shutil.rmtree(engine_dir(), ignore_errors=True)
    tmp.rename(engine_dir())
    zpath.unlink()


# ---------------------------------------------------------------- on / off
def _set_ini(ini: Path, section: str, key: str, value: str) -> None:
    lines = ini.read_text(encoding="utf-8", errors="ignore").splitlines()
    inside, done = False, False
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("[") and s.endswith("]"):
            inside = s[1:-1].lower() == section.lower()
        elif inside and s.split("=", 1)[0].strip().lower() == key.lower() and not s.startswith(";"):
            lines[i] = f"{key}={value}"
            done = True
            break
    if not done:
        raise RuntimeError(f"{key} not found under [{section}] in {ini.name}")
    ini.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_ini(folder: Path, key: str) -> str:
    ini = folder / "OptiScaler.ini"
    inside = False
    for l in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = l.strip()
        if s.startswith("[") and s.endswith("]"):
            inside = s[1:-1].lower() == "dlssnr"
        elif inside and s.split("=", 1)[0].strip().lower() == key.lower() and not s.startswith(";"):
            return s.split("=", 1)[1].strip()
    return "auto"


def set_tuning(folder: Path, key: str, value: str) -> None:
    _set_ini(folder / "OptiScaler.ini", "DlssNr", key, value)


def turn_on(g: Game, model: dict) -> dict:
    """Copy the engine and the model into the game folder. Never overwrites anything already there."""
    folder, src = g.folder, engine_dir()
    if not engine_ready():
        raise RuntimeError("The engine isn't downloaded yet")
    m = Path(model["path"])
    if not m.is_file() or sha256(m) != model["sha256"]:
        raise RuntimeError("The DLSS 5 model file has moved or changed. Search for it again.")
    proxy = next((p for p in (["winmm.dll"] if g.api == "Vulkan" else []) + PROXIES if not (folder / p).exists()), None)
    if not proxy:
        raise RuntimeError("Every name OptiScaler can load as is already taken in this folder")
    plan = []
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if rel.name.lower() in ENGINE_SKIP or rel.name.lower().startswith("read me") or rel.parts[0].lower() == "licenses":
            continue
        dest = folder / (proxy if rel.as_posix() == "OptiScaler.dll" else rel)
        plan.append((f, dest))
    plan.append((m, folder / MODEL))
    clash = [str(d.relative_to(folder)) for s, d in plan if s.is_file() and d.exists()]
    if clash:
        raise RuntimeError("These are already in the game folder, so nothing was changed: " + ", ".join(clash[:5]))
    added, made_dirs = [], []
    try:
        for s, d in plan:
            if s.is_dir():
                if not d.exists():
                    d.mkdir(parents=True)
                    made_dirs.append(str(d.relative_to(folder)))
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
                added.append(str(d.relative_to(folder)))
        lic = folder / "OptiScaler" / "Licenses"
        shutil.copytree(src / "Licenses", lic)
        added += [str(p.relative_to(folder)) for p in lic.rglob("*") if p.is_file()]
        made_dirs.append(str(lic.relative_to(folder)))
        _set_ini(folder / "OptiScaler.ini", "DlssNr", "Enabled", "true")
        _set_ini(folder / "OptiScaler.ini", "DlssNr", "ToggleKey", TOGGLE_KEY)
    except Exception:
        _remove(folder, added, made_dirs)
        raise
    man = {"app": APP, "engine": ENGINE["version"], "proxy": proxy, "model_from": model["from"],
           "model_sha256": model["sha256"], "added": added, "dirs": made_dirs}
    (folder / MANIFEST).write_text(json.dumps(man, indent=2), encoding="utf-8")
    return man


def _remove(folder: Path, added: list[str], dirs: list[str]) -> None:
    for rel in added:
        p = folder / rel
        if p.is_file():
            p.unlink()
    for rel in ("OptiScaler.log",):
        if (folder / rel).is_file():
            (folder / rel).unlink()
    cap = folder / "dlssnr-capture"
    if cap.is_dir():
        shutil.rmtree(cap)
    for rel in sorted(dirs, key=lambda r: -len(Path(r).parts)):
        p = folder / rel
        if p.is_dir():
            for sub in sorted(p.rglob("*"), key=lambda x: -len(x.parts)):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
            if not any(p.iterdir()):
                p.rmdir()


def turn_off(g: Game) -> None:
    """Remove exactly what turn_on added. The game is left as it was."""
    man = json.loads((g.folder / MANIFEST).read_text(encoding="utf-8"))
    _remove(g.folder, man["added"], man["dirs"])
    (g.folder / MANIFEST).unlink()


def take_over(g: Game) -> dict:
    """Write a manifest for an OptiScaler DLSS NR install that was done by hand, so Off can remove it."""
    folder = g.folder
    proxy = next(p for p in PROXIES if (folder / p).is_file() and _is_opti(folder / p))
    added = [proxy] + [n for n in ("OptiScaler.ini", "nvngx.dll_dlssnr.dll", MODEL) if (folder / n).is_file()]
    opt = folder / "OptiScaler"
    added += [str(p.relative_to(folder)) for p in opt.rglob("*") if p.is_file()] if opt.is_dir() else []
    man = {"app": APP, "engine": "by hand", "proxy": proxy, "model_from": "by hand", "model_sha256": "",
           "added": added, "dirs": ["OptiScaler"] if opt.is_dir() else []}
    (folder / MANIFEST).write_text(json.dumps(man, indent=2), encoding="utf-8")
    return man


if __name__ == "__main__":  # quick report without the window: py dlss5core.py
    s = load_settings()
    known = known_games()
    print(gpu())
    for name, root, store in all_games(s):
        g = judge(name, root, store, known)
        print(f"{g.state:6} {store:8} {name[:40]:40} {g.api:11} {str(g.folder or '')[-50:]:50} {g.why}")
