# YTDLP Studio v0.1.3 — tesztjelentés

## Ellenőrzött (2026-11-01)

- Python-modulok fordíthatósága: OK (`python -m compileall`).
- Grafikus Tkinter-felület indulása Linux/Xvfb alatt: OK, képernyőkép készült.
- 15 automatizált unit/integrációs teszt: OK.
- yt-dlp JSON-adatainak normalizálása: unit tesztek OK.
- Vágási időpontok validálása és parancsargumentumok előállítása: unit tesztek OK.
- SRT/WebVTT-időzítés levágása és áthelyezése: unit tesztek OK.
- Hivatalos SHA256 ellenőrzésre épülő frissítő: unit tesztek OK, online próba NEM történt.
- Külső yt-dlp eszköz szimulációja: integrációs teszt OK (metaadat, médiaútvonal, felirat-utófeldolgozás).
- Valódi helyi FFmpeg 7.1.5-tel: 1,5 másodperces szintetikus MKV-állományba SRT-felirat beágyazása, ffprobe stream-ellenőrzéssel OK.

## Nem ellenőrzött ebben a környezetben

- Windows 11 x64 natív EXE build / portable működés.
- Valódi YouTube letöltés és valós yt-dlp válaszok.
- Automatikusan generált/fordított YouTube-feliratok konkrét videókkal.
- Több nyelvű YouTube-hangsávok és AI-szinkron konkrét videókkal.
- GitHub Actions workflow tényleges futtatása.
- Frissítő valós yt-dlp.exe fájlcseréje Windows alatt.
- Hosszabb vagy hálózati hibával megszakadó letöltés éles tesztje.

**Kiadhatóság:** 0.1 fejlesztői előzetes. Éles, stabil Windows kiadásnak csak
Windowsos fordítás és gyakorlati letöltési tesztek után tekinthető.

## v0.1.1 javítás

- A PowerShell parserhibát kiváltó `$name:` kifejezés javítva `${name}:` alakra.
- A buildszkript UTF-8 BOM-mal mentve a Windows PowerShell 5.1 miatt.
- A letöltőparancsokhoz `-UseBasicParsing` kapcsoló hozzáadva.
- A Python és PyInstaller kilépési kódjainak ellenőrzése hozzáadva.
- **Windows alatt a módosított buildet nem futtattam, így további hiba még előfordulhat.**

## v0.1.2 buildjavítás (2026-11-01)

A Windows build korábbi verziója kizárólag a `python` parancsot és a Python
3.12-t ismerte fel, ezért a letöltés után félbeszakadt, ha csak a `py`
launcher volt elérhető vagy a Python verziója 3.11/3.13 volt.
A buildszkript most több Python-indítási módot ellenőriz a letöltések előtt,
projektlokális virtuális környezetet használ, és hash-ellenőrzés után
újrahasznosítja a már letöltött fájlokat. A 15 Python-egységteszt újra
sikeresen lefutott.
**Korlát:** a PowerShell buildfolyamatot itt nem lehetett tényleges Windows 11
környezetben futtatni, ezért az EXE elkészítését továbbra is helyben kell
ellenőrizni.

## v0.1.3 GUI-frissítés (2026-11-01)

- A Tkinter `ttk.Combobox` legördülő mezőket natív `ttk.OptionMenu`
  vezérlőkre cseréltem. Automatikus tesztben a menük bejegyzéseinek
  meghívása az összes formátumtípus változóját megfelelően módosítja.
- A hangsáv és felirat panel egymás mellé került, mindkettő kereshető,
  görgethető, valódi jelölőnégyzetekkel rendelkezik.
- Tesztelve: checkbox többes kijelölés; keresés utáni kijelölésmegőrzés;
  a kijelölésből generált letöltési beállítások; kétpaneles elrendezés;
  natív menüválasztás; a videó statikus előnézetének megjelenítése.
- **19 / 19 automatikus teszt sikeres Linux/Xvfb alatt.**
- A grafikus felületet Xvfb képernyőképpel szemrevételeztem.
- **Windows 11-es natív EXE build, Windows legördülő menü egérrel
  történő kipróbálása és éles YouTube-letöltés ezen a gépen nem történt.**
- A látványtervi képernyőkép tesztmetaadatot és mesterséges képet mutat,
  nem valódi YouTube-letöltést vagy beépített streaming videólejátszót.
