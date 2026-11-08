# YTDLP Studio v0.1.3 — portable, magyar nyelvű yt-dlp kezelőfelület

**Állapot:** fejlesztői első kiadás. A forráskód elkészült és egységteszteket
futtatunk rajta; a Windows 11-es működést és az élő YouTube-letöltéseket külön,
valós Windows gépen kell tesztelni. A forrás ZIP **nem** tartalmaz kész Windows
EXE-t vagy harmadik felektől származó binárisokat.

## Windows portable ZIP elkészítése

Ajánlott: töltsd fel a projekt teljes tartalmát egy GitHub-repozitóriumba, és
indítsd el az **Actions → Windows x64 portable EXE → Run workflow** futtatást.
A `YTDLPStudio-Windows-x64-portable` artifact egy teljes ZIP-csomag, benne:

```text
YTDLPStudio.exe
bin/yt-dlp.exe
bin/ffmpeg.exe
bin/ffprobe.exe
bin/deno.exe
README.md
licenses/...
```

A GitHub Actions útvonal a Windows-fordítást és a függőségek hivatalos
kiadásaiból történő beszerzését is elvégzi. A folyamatnak internethozzáférés
kell. **A kész ZIP futtatásához Python/.NET telepítés nem szükséges.**

Helyi Windows build: telepítsd a Python 3.12 (ajánlott), 3.11 vagy 3.13 64 bites kiadását, majd indítsd
a `build_windows.cmd` fájlt (vagy PowerShellből a `build_windows.ps1` fájlt). A folyamat a legfrissebb yt-dlp
stable kiadást, FFmpeg GPL Windows buildet és Deno runtimet tölti le.

## Használat

1. Csomagold ki a teljes portable ZIP-et tetszőleges írható mappába.
2. Indítsd el a `YTDLPStudio.exe` programot.
3. Illessz be egy videó-URL-t, majd kattints **Elemzés**.
4. Kattints a **formátum-mező jobb oldalán lévő háromszögre** (ezek natív Windows menük).
   Az elemzés után válassz videó-/hangformátumot, szükség esetén hangsávot és feliratot.
   A hangsávok és feliratok **jelölőnégyzetekkel**, Ctrl/Shift nélkül választhatók.
   A keresővel szűrhetsz a nyelvekre; a kijelölések szűrés után is megmaradnak.
   A jobb alsó részen a videó **nagy bélyegképes előnézete** látható;
   a lejátszáshoz a „Videó megnyitása böngészőben” gombot használd.
5. Opcionálisan add meg a `00:15:30` és `01:42:00` vágási határokat.
6. Válaszd a **Hozzáadás a sorhoz** gombot.
7. A **Eszközök / Frissítés** menüvel ellenőrizheted a legújabb stabil yt-dlp-t.

**Feliratok:** A kézi és automatikus feliratok külön szerepelnek. Az
„automatikus / fordított” címke nem garantálja, hogy az adott felirat
YouTube-fordítás; az API ezt a különbséget nem mindig közli. A letöltés
sikeressége az adott videótól függ. Ha egy nyelvhez kézi és automatikus
felirat is kijelölésre kerül, a kézi felirat élvez elsőbbséget.

**Hangsávok:** A lista az egyes nyelvekhez legjobb elérhető formátumot mutatja.
A YouTube által biztosított többnyelvű hangsávokat képes kezelni, az AI
szinkron tényét nem találja ki. Több kiválasztott hangsávhoz MKV szükséges.
Ha nincs kijelölés, a yt-dlp választja az alapértelmezett hangot.

**Időbeli vágás:** a `--download-sections` + FFmpeg funkciót használja.
Forrástól függően még így is letöltődhet több adat, vagy a vágás keyframe
pontosságú lehet. A pontos vágás újrakódolhat. A letöltött SRT/VTT-feliratokat
az alkalmazás a vágott szakaszhoz igazítja. A beágyazás MKV/MP4 esetén
próbálkozás, és sikertelen esetben külső felirat marad.

**Kompatibilitási korlát:** A program mindig a yt-dlp hivatalos parancssori
szolgáltatásait használja; a webhelyek formátum- és jogosultsági korlátozásait
nem kerüli meg. Ne használd DRM-megkerülésre vagy engedély nélküli letöltésre.

## Forrásból indítás (teszt vagy fejlesztés)

Python 3.11+ és Tkinter szükséges (Windows Python disztribúció tartalmazza).
A bélyegképhez opcionálisan Pillow. Tedd a `yt-dlp`, `ffmpeg`, `ffprobe` és
`deno` programokat a `bin` mappába, vagy a PATH-on legyenek elérhetők.

```powershell
python start.py
python -m unittest discover -s tests -v
```

## Javítás – v0.1.1 buildszkript

A v0.1 forráscsomagban a `build_windows.ps1` 40. sorában szereplő
`$name:` változóhivatkozás PowerShell-szintaktikai hibát okozott. Javítva
`${name}:` alakra. A szkript UTF-8 BOM kódolást használ a Windows PowerShell
5.1 magyar szövegeihez. A Windowsos build tényleges lefutása továbbra is
külön ellenőrzést igényel.

## Ismert v0.1 korlátok

- Windows EXE nincs helyben validálva; az Actions workflow-t Windows runneren
  kell futtatni.
- A lejátszási lista kezelés alapvető, nincs külön videónkénti lista-nézet.
- A feliratok beágyazása MP4/MKV-hoz készült; WebM-hez külső felirat mentődik.
- Magyar lokalizáció van; angol felület még nincs.
- A „témaváltás” alkalmazás-újraindítást igényel.
- Van nagy statikus bélyegképes videó-előnézet, de beépített streaming lejátszó és
  vágási idővonal még nincs; a vágási időpontokat szöveges mezőkben kell megadni.
- A yt-dlp stable csatornája frissíthető, nightly/master nincs bekötve.
- FFmpeg és Deno frissítése a csomag újraépítésével történik.
- A pontos időbélyeg és az FFmpeg-kompatibilitás forrásfüggő.

## Licensing and third-party components

Source code: MIT (see `licenses/YTDLPStudio-MIT.txt`). External executables are
separately licensed; see `licenses/THIRD-PARTY-NOTICES.txt`. Their original
license texts and any source-offer obligations must be preserved on public
redistribution. No warranty is made for third-party services.

---

**English summary:** YTDLP Studio is an open-source Hungarian-language Tkinter
GUI for yt-dlp, providing video/audio formats, subtitles, multi-language audio,
partial video downloads, download queue, and SHA-256-verified yt-dlp stable
updates. GitHub Actions bundles it into a self-contained Windows x64 portable
ZIP with FFmpeg and Deno. Windows integration tests remain necessary.

## Javítás – v0.1.2 buildszkript

A v0.1.1 build csak a `python` parancsot és kizárólag a 3.12 verziót
fogadta el. A v0.1.2 a Windows `py` launchert is támogatja, és a 64 bites
Python 3.11–3.13 verziókkal képes fordítani. Python 3.12 az ajánlott.
A build már **a függőségek letöltése előtt** ellenőrzi a Pythont, a már
letöltött és hash alapján ellenőrizhető függőségeket újra felhasználja.
A Python-csomagok a projekt `.build-venv` mappájába települnek.
Ha nem található megfelelő Python, ellenőrizd PowerShellben: `py -0p`
és `python --version`. A kész EXE használatához nem kell Python.

## UI-frissítés – v0.1.3

- A korábbi `ttk.Combobox` mezőket `ttk.OptionMenu` natív menük váltják fel,
  mert egyes Windowsos környezetekben a ComboBox legördülő listái nem nyíltak meg.
- Hangsávok és feliratok két szomszédos panelben, külön keresővel és valódi
  jelölőnégyzetekkel. Többszörös kijelöléshez nem kell Ctrl vagy Shift.
- A szűrt listák kijelölése változatlan marad; az „Összes törlése” gomb mindent
  töröl, a „Láthatók mind” a jelenleg látható eredményeket jelöli.
- A felszabadult helyen megjelenik az elemzett videó nagy, ablakméretre
  igazodó borítóképe. Ez **nem videólejátszó**; a böngészőben nyitható meg.
- A már kész portable EXE önmagában nem frissül a forrásmódosításoktól:
  a `build_windows.cmd` fájllal újra kell építeni. Ha a meglévő forrásmappába
  másolod a javított fájlokat, a build újrahasználhatja az előzőleg ellenőrzött
  binárisokat és letöltött csomagokat.
