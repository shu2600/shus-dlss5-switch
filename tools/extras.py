"""Shu's DLSS 5 Switch v2 extras: Newest DLSS (driver), Desktop Icons, Games Folder.
Every change is backed up first and can be undone. Nothing here ships NVIDIA files.
Newest DLSS uses NVIDIA Profile Inspector (MIT, Orbmu2k), downloaded once from its GitHub release and checked by sha256."""
from __future__ import annotations

import ctypes
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import dlss5core as core

HOME = core.HOME
BACKUPS = HOME / "backups"
ICONS = HOME / "icons"
CUSTOM = ICONS / "custom"
CREDITS = ICONS / "CREDITS.md"
SGDB_KEY = HOME / "steamgriddb_key.txt"
NO_WINDOW = core.NO_WINDOW
UA = "ShusDLSS5Switch/2.0"


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ps(script: str, timeout: int = 180) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-600:])
    return r.stdout


# =============================================================== Newest DLSS (driver profile)
NPI = {"url": "https://github.com/Orbmu2k/nvidiaProfileInspector/releases/download/v3.0.2.1/nvidiaProfileInspector.zip",
       "sha256": "88dcf3514111e8de630688467c03c36d8c2a8ad9ebc8073f27c069f82b75bb40"}
NPI_DIR = HOME / "npi"
NPI_EXE = NPI_DIR / "nvidiaProfileInspector.exe"
DLSS_SETTINGS = {  # NVIDIA Profile Inspector setting ids (v3.0.2.1)
    0x10E41E01: ("DLSS Upscaling: Newest Version", 1),
    0x10E41E02: ("DLSS Ray Reconstruction: Newest Version", 1),
    0x10E41E03: ("DLSS Frame Generation: Newest Version", 1),
    0x10E41DF3: ("DLSS Preset: NVIDIA's Recommended", 0x00FFFFFF),
}


def npi_ready() -> bool:
    return NPI_EXE.is_file()


def get_npi() -> None:
    NPI_DIR.mkdir(parents=True, exist_ok=True)
    z = NPI_DIR / "npi.zip"
    req = urllib.request.Request(NPI["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, z.open("wb") as f:
        shutil.copyfileobj(r, f)
    if core.sha256(z) != NPI["sha256"]:
        z.unlink()
        raise RuntimeError("NVIDIA Profile Inspector download didn't match its checksum, so it wasn't used.")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(NPI_DIR)
    z.unlink()


def _npi(*args: str) -> None:
    """Profile Inspector asks Windows for admin, so it starts through ShellExecute and we wait for it."""
    quoted = ",".join("'" + a.replace("'", "''") + "'" for a in args)
    _ps(f"Start-Process -FilePath '{NPI_EXE}' -ArgumentList {quoted} -Wait -WindowStyle Hidden")


def _export() -> Path:
    before = set(NPI_DIR.glob("CustomProfiles_*.nip"))
    _npi("-exportCustomized")
    new = sorted(set(NPI_DIR.glob("CustomProfiles_*.nip")) - before, key=lambda p: p.stat().st_mtime)
    if not new:
        raise RuntimeError("NVIDIA Profile Inspector didn't write its export.")
    return new[-1]


def _base_values(nip: Path) -> dict[int, int]:
    text = nip.read_bytes().decode("utf-8-sig")  # UTF-8 with a BOM that declares utf-16
    root = ET.fromstring(text.split("?>", 1)[1] if text.startswith("<?xml") else text)
    for prof in root.findall("Profile"):
        if prof.findtext("ProfileName") == "Base Profile":
            out = {}
            for s in prof.find("Settings").findall("ProfileSetting"):
                try:
                    out[int(s.findtext("SettingID"))] = int(s.findtext("SettingValue"))
                except (TypeError, ValueError):
                    pass
            return out
    return {}


def _nip(values: dict[int, int], path: Path) -> None:
    root = ET.Element("ArrayOfProfile")
    prof = ET.SubElement(root, "Profile")
    ET.SubElement(prof, "ProfileName").text = "Base Profile"
    ET.SubElement(prof, "Executeables")
    sets = ET.SubElement(prof, "Settings")
    for sid, val in values.items():
        s = ET.SubElement(sets, "ProfileSetting")
        ET.SubElement(s, "SettingNameInfo").text = DLSS_SETTINGS.get(sid, ("", 0))[0]
        ET.SubElement(s, "SettingID").text = str(sid)
        ET.SubElement(s, "SettingValue").text = str(val)
        ET.SubElement(s, "ValueType").text = "Dword"
    ET.indent(root)
    path.write_bytes(b"\xef\xbb\xbf" + ('<?xml version="1.0" encoding="utf-16"?>\r\n' + ET.tostring(root, encoding="unicode")).encode())


def dlss_status() -> dict[str, bool]:
    cur = _base_values(_export())
    return {name: cur.get(sid) == want for sid, (name, want) in DLSS_SETTINGS.items()}


def dlss_on() -> dict[str, bool]:
    bdir = BACKUPS / "nvidia" / _stamp()
    bdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_export(), bdir / "before.nip")
    nip = bdir / "newest_dlss.nip"
    _nip({sid: v for sid, (_, v) in DLSS_SETTINGS.items()}, nip)
    _npi(str(nip), "-silentImport", "-mergeImport")
    core.log(f"Newest DLSS on, backup {bdir}")
    return dlss_status()


def dlss_undo() -> dict[str, bool]:
    d = BACKUPS / "nvidia"
    last = sorted(p for p in d.iterdir() if p.is_dir())[-1] if d.is_dir() else None
    if not last:
        raise RuntimeError("Nothing to undo yet.")
    before = _base_values(last / "before.nip")
    nip = last / "undo.nip"
    _nip({sid: before.get(sid, 0) for sid in DLSS_SETTINGS}, nip)
    _npi(str(nip), "-silentImport", "-mergeImport")
    core.log(f"Newest DLSS undone from {last.name}")
    return dlss_status()


# =============================================================== Desktop Icons
SIZE = 256
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
STEAM_CACHE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "appcache" / "librarycache"


def pillow_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def desktops() -> list[Path]:
    out = [Path(os.environ["USERPROFILE"]) / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
           Path(os.environ["USERPROFILE"]) / "OneDrive" / "Desktop"]
    return [d for d in out if d.is_dir()]


def _lnk_targets(paths: list[Path]) -> dict[str, str]:
    if not paths:
        return {}
    lst = HOME / "_lnk_list.txt"
    lst.write_text("\n".join(str(p) for p in paths), encoding="utf-8")
    out = _ps(f"$w=New-Object -ComObject WScript.Shell; Get-Content -LiteralPath '{lst}' -Encoding UTF8 | % {{ "
              f"$_ + [char]9 + $w.CreateShortcut($_).TargetPath }}")
    res = {}
    for line in out.splitlines():
        if "\t" in line:
            a, b = line.split("\t", 1)
            res[a] = b
    return res


def find_shortcuts(settings: dict) -> list[dict]:
    """Game shortcuts on the desktops: Steam ones by their steam:// link, others by pointing into a known game folder."""
    roots = sorted(((str(r).lower().rstrip("\\"), n) for n, r, _s in core.all_games(settings)), key=lambda x: -len(x[0]))
    files = [f for d in desktops() for f in list(d.rglob("*.lnk")) + list(d.rglob("*.url"))]
    targets = _lnk_targets([f for f in files if f.suffix.lower() == ".lnk"])
    items = []
    for f in files:
        appid, target, name = "", "", None
        if f.suffix.lower() == ".url":
            m = re.search(r"steam://rungameid/(\d+)", f.read_text(encoding="utf-8", errors="ignore"))
            if m:
                appid, name = m.group(1), f.stem
        else:
            target = targets.get(str(f), "").lower()
            name = next((n for r, n in roots if target.startswith(r + "\\")), None)
        if name:
            items.append({"shortcut": str(f), "game": name, "appid": appid, "target": target})
    return items


def _round(tile):
    from PIL import Image, ImageDraw
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=44, fill=255)
    tile.putalpha(m)
    return tile


def _tile_art(img, out: Path) -> Path:
    """Any art into the house tile: opaque square art fills it, cut-out art sits on a blurred copy of itself."""
    from PIL import Image, ImageFilter
    out.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGBA")
    s = max(img.size)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.alpha_composite(img, ((s - img.width) // 2, (s - img.height) // 2))
    sq = sq.resize((SIZE, SIZE), Image.LANCZOS)
    corners = [sq.getpixel(p)[3] for p in ((4, 4), (SIZE - 5, 4), (4, SIZE - 5), (SIZE - 5, SIZE - 5))]
    if min(corners) > 200:
        tile = sq
    else:
        bg = sq.convert("RGB").filter(ImageFilter.GaussianBlur(22))
        bg = Image.blend(bg, Image.new("RGB", bg.size, (12, 14, 18)), 0.55).convert("RGBA")
        fg = sq.resize((int(SIZE * 0.82),) * 2, Image.LANCZOS)
        bg.alpha_composite(fg, ((SIZE - fg.width) // 2, (SIZE - fg.height) // 2))
        tile = bg
    _round(tile).save(out, sizes=ICO_SIZES)
    return out


def _steam_tile(appid: str, out: Path) -> Path | None:
    """Steam's own library art from the local cache: logo over the blurred banner, backdrop by logo brightness."""
    from PIL import Image, ImageFilter
    out.parent.mkdir(parents=True, exist_ok=True)
    d = STEAM_CACHE / appid

    def find(n):
        h = list(d.rglob(n)) if d.is_dir() else []
        return h[0] if h else None
    hero, logo, cover = find("library_hero.jpg"), find("logo.png"), find("library_600x900.jpg")
    if hero and logo:
        bg = Image.open(hero).convert("RGB")
        w, h = bg.size
        s = min(w, h)
        bg = bg.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((SIZE, SIZE)).filter(ImageFilter.GaussianBlur(6))
        lg = Image.open(logo).convert("RGBA")
        lg.thumbnail((int(SIZE * 0.86), int(SIZE * 0.62)), Image.LANCZOS)
        a, lum = lg.getchannel("A"), lg.convert("L")
        tot = sum(a.getdata()) or 1
        light = sum(x * y for x, y in zip(lum.getdata(), a.getdata())) / tot > 70
        tone, halo = ((12, 14, 18), (0, 0, 0, 255)) if light else ((235, 236, 240), (255, 255, 255, 255))
        tile = Image.blend(bg, Image.new("RGB", bg.size, tone), 0.62).convert("RGBA")
        pos = ((SIZE - lg.width) // 2, (SIZE - lg.height) // 2)
        sh = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        k = Image.new("RGBA", lg.size, halo)
        k.putalpha(a.point(lambda v: int(v * 0.9)))
        sh.alpha_composite(k, pos)
        sh = sh.filter(ImageFilter.GaussianBlur(7))
        tile.alpha_composite(sh)
        tile.alpha_composite(sh)
        tile.alpha_composite(lg, pos)
        _round(tile).save(out, sizes=ICO_SIZES)
        return out
    if cover:
        return _tile_art(Image.open(cover), out)
    return None


def _exe_tile(exe: str, out: Path) -> Path | None:
    try:
        from icoextract import IconExtractor
        from PIL import Image
        ico = Image.open(io.BytesIO(IconExtractor(exe).get_icon().getvalue()))
        ico.size = max(ico.info.get("sizes", {ico.size}), key=lambda s: s[0])
        return _tile_art(ico, out)
    except Exception:  # noqa: BLE001 - no icoextract, or no icon in the exe
        return None


def _sgdb(item: dict, out_dir: Path) -> tuple[Path | None, str]:
    key = SGDB_KEY.read_text(encoding="utf-8").strip() if SGDB_KEY.exists() else ""
    if not key:
        return None, ""

    def get(path, params=None):
        url = "https://www.steamgriddb.com/api/v2" + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            b = json.load(r)
        return b.get("data") if b.get("success") else None
    gid = None
    try:
        if item["appid"]:
            gid = (get(f"/games/steam/{item['appid']}") or {}).get("id")
    except urllib.error.HTTPError:
        pass
    if not gid:
        hits = get("/search/autocomplete/" + urllib.parse.quote(item["game"])) or []
        gid = hits[0]["id"] if hits else None
    if not gid:
        return None, ""
    best = None
    for dims in ("512,1024", "256"):
        rows = get(f"/icons/game/{gid}", {"dimensions": dims, "types": "static", "mimes": "image/png",
                                          "nsfw": "false", "humor": "false", "epilepsy": "false"}) or []
        if rows:
            best = max(rows, key=lambda r: (r.get("score", 0), r.get("width", 0)))
            break
    if not best:
        return None, ""
    from PIL import Image
    req = urllib.request.Request(best["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        img = Image.open(io.BytesIO(r.read()))
    out = _tile_art(img, out_dir / f"sgdb_{best['id']}.ico")
    artist = (best.get("author") or {}).get("name", "unknown")
    return out, f"icon by {artist}, SteamGridDB https://www.steamgriddb.com/icon/{best['id']}"


def _icon_for(item: dict) -> tuple[Path | None, str]:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", item["game"]).strip("_")
    for ext in (".ico", ".png"):
        p = CUSTOM / f"{item['game']}{ext}"
        if p.exists():
            from PIL import Image
            return _tile_art(Image.open(p), ICONS / f"custom_{safe}.ico"), "your own pick (custom folder)"
    try:
        ico, credit = _sgdb(item, ICONS)
        if ico:
            return ico, credit
    except Exception:  # noqa: BLE001 - offline or bad key: fall back to art already on the PC
        pass
    if item["appid"]:
        ico = _steam_tile(item["appid"], ICONS / f"steam_{item['appid']}.ico")
        if ico:
            return ico, "Steam library art (the publisher's own), from your Steam folder"
    if item["target"].endswith(".exe") and Path(item["target"]).exists():
        ico = _exe_tile(item["target"], ICONS / f"exe_{safe}.ico")
        if ico:
            return ico, "the game's own icon"
    return None, ""


def _set_icon(path: Path, ico: Path) -> None:
    if path.suffix.lower() == ".url":
        lines = [l for l in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                 if not l.startswith(("IconFile=", "IconIndex="))]
        i = next((n for n, l in enumerate(lines) if l.strip() == "[InternetShortcut]"), 0)
        lines[i + 1:i + 1] = [f"IconFile={ico}", "IconIndex=0"]
        path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        return
    # Some launchers make shortcuts only admins can edit; you can still delete them, so edit a copy and swap it in.
    tmp = HOME / ("_tmp_" + path.name)
    shutil.copy2(path, tmp)
    _ps(f"$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('{str(tmp).replace(chr(39), chr(39) * 2)}'); "
        f"$s.IconLocation='{str(ico).replace(chr(39), chr(39) * 2)},0'; $s.Save()")
    path.unlink()
    shutil.move(str(tmp), str(path))


def _refresh_icons() -> None:
    subprocess.run(["ie4uinit.exe", "-show"], check=False, creationflags=NO_WINDOW)


def icons_apply(settings: dict, progress=None) -> str:
    if not pillow_ok():
        raise RuntimeError("Desktop Icons needs Pillow. Run setup.bat again and it installs it.")
    ICONS.mkdir(parents=True, exist_ok=True)
    CUSTOM.mkdir(parents=True, exist_ok=True)
    items = find_shortcuts(settings)
    bdir = BACKUPS / "icons" / _stamp()
    bdir.mkdir(parents=True, exist_ok=True)
    manifest, credits, failed = [], [], []
    for n, it in enumerate(items):
        if progress:
            progress(n / max(len(items), 1), it["game"])
        ico, credit = _icon_for(it)
        if not ico:
            failed.append(it["game"])
            continue
        src = Path(it["shortcut"])
        keep = bdir / f"{n:03d}_{src.name}"
        shutil.copy2(src, keep)
        manifest.append({"original": str(src), "backup": str(keep)})
        (bdir / "restore.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        try:
            _set_icon(src, ico)
            credits.append(f"- {it['game']}: {credit}")
        except Exception:  # noqa: BLE001
            failed.append(it["game"])
    CREDITS.write_text("# Icon art credits\n\n" + "\n".join(sorted(set(credits))) + "\n", encoding="utf-8")
    _refresh_icons()
    core.log(f"Desktop icons: {len(credits)} done, backup {bdir}")
    return f"{len(credits)} Game Icons Done" + (f"  ·  {len(failed)} Skipped" if failed else "")


def icons_undo() -> str:
    d = BACKUPS / "icons"
    runs = sorted(p for p in d.iterdir() if p.is_dir() and (p / "restore.json").exists()) if d.is_dir() else []
    if not runs:
        raise RuntimeError("Nothing to undo yet.")
    first = runs[0]  # the first run holds the icons as they were before the Switch ever touched them
    for m in json.loads((first / "restore.json").read_text(encoding="utf-8")):
        if Path(m["backup"]).exists():
            shutil.copy2(m["backup"], m["original"])
    _refresh_icons()
    return "Your Original Icons Are Back"


# =============================================================== Games Folder
FOLDER_ICON_PAGE = "https://www.flaticon.com/free-icon/game-folder_8316894"


def games_folder() -> Path:
    return Path(os.environ["USERPROFILE"]) / "Desktop" / "Games"


def folder_apply(icon_file: str, folder: Path | None = None) -> str:
    folder = folder or games_folder()
    src = Path(icon_file)
    keep = ICONS / "folder"
    keep.mkdir(parents=True, exist_ok=True)
    ico = keep / (src.stem + ".ico")
    if src.suffix.lower() == ".ico":
        shutil.copy2(src, ico)
    else:
        from PIL import Image
        Image.open(src).convert("RGBA").save(ico, sizes=ICO_SIZES)
    folder.mkdir(parents=True, exist_ok=True)
    ini = folder / "desktop.ini"
    bdir = BACKUPS / "folder" / _stamp()
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "folder.txt").write_text(str(folder), encoding="utf-8")
    k32 = ctypes.windll.kernel32
    if ini.exists():
        k32.SetFileAttributesW(str(ini), 0x80)
        shutil.copy2(ini, bdir / "desktop.ini")
    ini.write_text(f"[.ShellClassInfo]\r\nIconResource={ico},0\r\n", encoding="utf-16")
    k32.SetFileAttributesW(str(ini), 0x2 | 0x4)      # hidden + system
    k32.SetFileAttributesW(str(folder), 0x1)         # read-only folder: Explorer only reads desktop.ini then
    ctypes.windll.shell32.SHChangeNotify(0x2000, 0x0005, str(folder), None)
    _refresh_icons()
    return f"{folder.name} Folder Icon Set"


def folder_undo(folder: Path | None = None) -> str:
    folder = folder or games_folder()
    d = BACKUPS / "folder"
    runs = sorted(p for p in d.iterdir() if p.is_dir() and (p / "folder.txt").read_text(encoding="utf-8") == str(folder)) if d.is_dir() else []
    if not runs:
        raise RuntimeError("Nothing to undo yet.")
    first = runs[0]
    ini = folder / "desktop.ini"
    if ini.exists():
        ctypes.windll.kernel32.SetFileAttributesW(str(ini), 0x80)
        ini.unlink()
    if (first / "desktop.ini").exists():
        shutil.copy2(first / "desktop.ini", ini)
        ctypes.windll.kernel32.SetFileAttributesW(str(ini), 0x2 | 0x4)
    _refresh_icons()
    return "Folder Put Back"
