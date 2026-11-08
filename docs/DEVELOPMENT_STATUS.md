# YTDLP Studio v0.2.0 – fejlesztési állapot (1. munkamenet, 2026-11-08)

Kiindulópont: `v0.1.3` Git-tag (main ág). Mentés: `..\backup_v0.1.3\` (EXE, forrás-ZIP, régi portable ZIP).
A munka a `dev/v0.2.0` ágon folyik. **Ez az ág még nem futtatható**: az új Qt-felület nincs kész.

## Döntések
- Felület: Tkinter → **PySide6 (Qt 6.12, LGPL)**. Indok: megbízható legördülő listák, valódi DPI-skálázás,
  futás közbeni világos/sötét téma, beépített videóelőnézet (QtMultimedia, ellenőrizve: a 360p progresszív
  YouTube-URL FFmpeg-gel lejátszható). Build: PyInstaller **onedir** (gyorsabb indulás, LGPL-kompatibilis).
- Szerkezet: `src/ytstudio` (forrás), `build/` (szkriptek), `docs/` (licencek, jelentések), `assets/`, `tests/`,
  `dist/` (kimenet), `.build-cache/downloads` (FFmpeg/Deno ZIP-gyorsítótár, gitignore-olt).
- Adatok: `<app>/data/` (settings.json, yt-dlp és Deno cache) – USB-ről is működik, írásvédett helyen
  `%LOCALAPPDATA%\YTDLPStudio` a tartalék. v0.1-es settings.json automatikusan átvéve.

## Talált hibák a v0.1.3-ban (valós yt-dlp 2026.10.26-tal ellenőrizve)
1. **Ékezetes fájlnevek/naplók sérültek**: a yt-dlp Windows-pipe-ra ANSI-kódlappal ír; a `PYTHONIOENCODING`
   nem segít, csak az `--encoding utf-8` (javítva).
2. **A haladásjelző nem frissült**: a `--print` csendes módot kapcsol be (javítva: `--no-quiet --progress`
   + saját `--progress-template`).
3. **Az „eredeti hangsáv” sosem lett felismerve**: a yt-dlp nem ad `original_language` mezőt; az eredetit a
   `language_preference=10` / „original” megjegyzés jelzi (javítva).
4. **A hangsávválasztás konkrét formátum-ID-t rögzített** (gyakran DRC- vagy 6 csatornás változatot) → most
   nyelvi szűrő (`ba[language=xx]`), a yt-dlp választja a konténerhez illő legjobb sávot.
5. **Feliratletöltési hiba az egész videót elbuktatta** volna egy hívásban; a feliratok most külön, nem
   végzetes lépésben töltődnek. Kézi és automatikus azonos nyelvű felirat fájlnév-ütközése megoldva (`.auto`).
6. **Gyors vágásnál MKV-ban a feliratok elcsúsztak** (a hang ~1,6 mp-cel később indul a kulcskocka miatt):
   ffprobe-bal mért eltolás alapján igazítva.
7. Fájlnév-ütközésnél a yt-dlp kihagyta a letöltést („already downloaded”), vágott részlet felülírhatta a
   teljes videó nevét → feladatonkénti rejtett munkamappa + „(2)” utótagos véglegesítés.
8. Megszakításkor/összeomláskor árva FFmpeg-folyamatok maradhattak → Windows Job Object (kill-on-close).
9. Az elemzés stderr-t és JSON-t összekeverte; a GUI tesztje Windows alatt nem futott (shebang-os mock).
10. WebM-be nem lehetett feliratot ágyazni; a beágyazott feliratoknak nem volt nyelvi címkéje.
11. Frissítő: csak stable, nem volt visszaállítás; most stable/nightly, két SHA-256 forrás keresztellenőrzése,
    `.bak` mentés, automatikus és kézi visszaállítás.

## Kész (dev/v0.2.0 ágon, még nincs tesztekkel lefedve)
- `settings.py` – portable mappák, bővített, validált beállítások, v0.1 migráció.
- `langs.py` – ~160 nyelv magyar neve, ISO 639-2 megfeleltetés.
- `core.py` – metaadat-modellek (hangsáv-típusok: eredeti/szinkron/AI-szinkron csak YouTube-jelölés
  esetén/narrált; felirattípusok: eredeti/automatikus/fordítás forrásnyelvvel), lejátszási lista (flat),
  formátumválasztók (MP4/MKV/WebM, kodekpreferencia, minőségkorlát), hang mód (MP3/M4A/AAC/Opus/FLAC/WAV/
  eredeti), vágás, méretbecslés.
- `errors.py` – magyar hibamagyarázatok (403, 429, bot-ellenőrzés, privát, DRM, nincs net, lemez tele…).
- `engine.py` – elemzés, letöltési feladat (haladás, sebesség, ETA, utófeldolgozási állapot), feliratok,
  helyi vágás („teljes letöltés, majd vágás”), beágyazás, véglegesítés.
- `subtitles.py` – vágás + eltolás, VTT-fejléc megőrzése.
- `updater.py` – lásd fent (élőben ellenőrizve: stable 2026.10.26, nightly 2026.11.04.232659).
- `ui/icons.py` – saját SVG-ikonkészlet.

## Hátralévő lépések (következő munkamenet)
1. `ui/theme.py` (világos/sötét/rendszer, QSS, sötét címsor), `ui/widgets.py` (szegmentált választó,
   kereshető jelölőnégyzetes lista proxy-modellel, kétvégpontos idővonal, kapcsoló, banner, spinner).
2. `ui/main_window.py`: URL-sáv → videókártya (nagy bélyegkép, előnézet) → mód (Videó/Csak hang/Csak felirat)
   → hangsávok + feliratok egymás mellett → vágás → rögzített műveletsáv („Letöltés most”, „Hozzáadás a
   sorhoz”, mappa, becsült méret); lejátszási lista nézet; letöltési sor jobb oldali panelben
   (QListView + delegált kártyák, megszakítás/újra/megnyitás/mappa).
3. `ui/dialogs.py` (Beállítások, Eszközök és frissítés, Napló, Hibarészletek), `ui/player.py`, `ui/app.py`.
4. A régi `gui.py` és `widgets.py` (Tk) törlése; tesztek átírása (core, engine mock-yt-dlp .exe/.py
   Windows-kompatibilisen, subtitles, updater, Qt offscreen GUI-tesztek); valós letöltési tesztek
   (Big Buck Bunny CC-BY, „Me at the zoo” feliratok).
5. `build/build_windows.ps1` átírása (onedir, verzióinfó, új ikon, `.build-cache`), portable ZIP,
   README, CHANGELOG, licencek (PySide6/Qt LGPL), tesztjelentés.
