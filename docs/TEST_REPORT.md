# YTDLP Studio 0.2.0 – tesztjelentés

Dátum: 2026-11-08 · Gép: Windows 11 Pro 10.0.26200 x64 · Build-Python: 3.11.9 ·
PySide6/Qt 6.12.0 · yt-dlp 2026.10.26 (stable) · FFmpeg: BtbN win64-gpl · Deno 2.9.x

Jelölések: ✅ sikeres · ⚠️ külső korlátozás (nem a program hibája) · ❌ sikertelen

## 1. Automatikus tesztek (`tests/`, 44 db) – ✅ 44/44

| Modul | Db | Mit ellenőriz |
|---|---|---|
| `test_core.py` | 15 | időpont- és URL-ellenőrzés, valós YouTube-metaadat (24 hangsávos videó mintája): eredeti hangsáv felismerése, szinkron/AI-szinkron/narrált jelölés, felirattípusok (eredeti/automatikus/fordítás + forrásnyelv), lejátszási lista, formátumválasztók, MP4/MKV/WebM szabályok, `--encoding utf-8`, `--no-quiet`, vágás-argumentumok, felirat-ütközés kezelése, érvénytelen bemenetek elutasítása (injection-kísérletek), méretbecslés |
| `test_subtitles.py` | 6 | SRT/VTT vágás, időeltolás (kulcskocka-kompenzáció), VTT-fejléc és beágyazott időbélyegek, ékezetes fájlnév, CR-CR-LF sorvégek |
| `test_updater.py` | 4 | csak hivatalos letöltési cím, két SHA-256 forrás egyezése, verzió-összehasonlítás, telepítés + mentés + automatikus visszaállítás hibás frissítésnél + kézi visszaállítás |
| `test_engine.py` | 7 | teljes letöltési folyamat szimulált yt-dlp-vel **valódi FFmpeg-gel**: elemzés (videó/lista), magyar hibaüzenet (403), vágott videó beágyazott `hun`+`eng` felirattal, ütközésmentes „(2)” név a feliratokkal együtt, hangsávok külön fájlokba, nem végzetes feliratletöltési hiba, csak felirat (kézi + `.auto`), megszakítás < 5 s, helyi pontos vágás |
| `test_gui.py` | 11 | valódi Qt-ablak Windows-asztalon, egérkattintásokkal: üres állapot, hibás link magyar üzenete, **a minőségválasztó legördülő lista ténylegesen megnyílik** és a választás érvényesül, módváltás (Videó/Csak hang/Csak felirat) a releváns vezérlőkkel, **hangsávok jelölőnégyzetei** (több sáv → MKV kényszer), **keresés/szűrés nem törli a kijelölést**, felirattípus-szűrő és **felirat-jelölőnégyzetek**, vágási idővonal ↔ időmezők ↔ fejezetválasztó, Letöltés most / Hozzáadás a sorhoz, lejátszási lista (almappa, sorszám, nyelvek), sorkártyák és műveletek, futás közbeni témaváltás |

Futtatás: `cd tests` → `..\.build-venv\Scripts\python -m unittest discover -s .`
(a buildszkript a build előtt automatikusan lefuttatja, hiba esetén leáll).

## 2. Valós hálózati tesztek (`tests/live_check.py`) – a csomagolt yt-dlp/FFmpeg/Deno eszközökkel

Tesztanyag: *Big Buck Bunny* (Blender Foundation, CC BY 3.0), *Me at the zoo* (19 mp-es
nyilvános tesztanyag). A többnyelvű hangsáv ellenőrzéséhez egy 3 másodperces, utána azonnal
törölt részlet készült egy többnyelvű szinkronnal rendelkező nyilvános videóból.

LIVE_RESULTS_PLACEHOLDER

## 3. Valódi felületen végzett munkafolyamat (élő hálózattal) – ✅

A forrásból indított alkalmazásban, programozott egérkattintásokkal:
Beillesztés gomb (a vágólapon szöveg + link: „Nézd meg: https://…”) → a link kiemelése és
automatikus elemzés („Mégse” gomb az elemzés alatt) → videókártya bélyegképpel →
Minőség: 480p → vágás bekapcsolása, 00:02:00–00:02:15 → **Letöltés most** → a sorban
„Letöltés … %” → „Kész · 1,5 MB”, a fájl a célmappában:
`Big Buck Bunny … [aqz-KE-bpKQ] (00.02.00–00.02.15).mp4`.

## 4. Portable EXE

Build: `build\build_windows.ps1` (teljes, online futás) – ✅ kilépési kód 0.

| Lépés | Eredmény |
|---|---|
| yt-dlp 2026.10.26 | ✅ GitHub `digest` + `SHA2-256SUMS` egyezik, gyorsítótárból |
| Deno v2.9.8 ZIP | ✅ letöltve, SHA-256 OK |
| FFmpeg BtbN win64-gpl (N-128691, 2026-11-08) | ✅ letöltve (~200 MB), SHA-256 OK |
| Automatikus tesztek a build előtt | ✅ 44/44 |
| PyInstaller 6.22.3 onedir, verzióinfó, ikon | ✅ |
| Portable mappa | `dist\YTDLPStudio\` (≈ 550 MB kicsomagolva) |
| ZIP | `dist\YTDLPStudio-0.2.0-Windows-x64-portable.zip` (235 MB) + `.sha256` |

Ellenőrzés a kész csomaggal:

- ✅ **Indulás Python nélküli környezetben**: a mappa átmásolva ide:
  `%TEMP%\YTDLP próba ő ű\Hordozható mappa` (ékezetes, szóközös útvonal), indítás
  `PATH=C:\Windows\System32;C:\Windows` környezettel, `PYTHON*` változók nélkül.
  `YTDLPStudio.exe --selftest`: kilépési kód 0, ablak megnyílt, a négy eszköz verziója
  lekérdezhető (yt-dlp 2026.10.26, FFmpeg N-128691, FFprobe N-128691, Deno 2.9.8),
  Qt Multimedia betölthető. A betöltött modulok listája szerint a program kizárólag a saját
  `_internal\python311.dll` fájlját használja.
- ✅ **Portable adatkezelés**: a beállítások, a napló és a gyorsítótár a program saját
  `data\` mappájába került; a rendszerleíró adatbázist a program nem használja.
- ✅ **Grafikus indulás**: normál indításkor az ablak 1,1 mp alatt megjelent (rendszer szerinti
  sötét téma, sötét natív címsor, saját ikon), bezáráskor 0 kóddal kilépett
  (képernyőkép: `docs/screenshots/exe-dark.png`).

## 5. Nem tesztelt vagy korlátozottan tesztelt esetek

- **Tiszta, Python nélküli Windows-gép**: Windows Sandbox nem volt elérhető. Helyette a kész
  mappa ékezetes, szóközös útvonalra másolva, Python nélküli `PATH`-tal futott, és
  ellenőriztük, hogy csak a csomagolt `python311.dll`-t tölti be (lásd 4. pont).
- **Automatikusan fordított YouTube-feliratok**: a YouTube a teszt idején minden kérésre
  429-et adott (kézzel, a yt-dlp-vel közvetlenül is reprodukálva, késleltetéssel is). A program
  ezt érthető magyar figyelmeztetéssel jelzi, a videó letöltését nem akasztja meg.
- **Előnézet-lejátszó**: a lejátszó betöltése és a forrás-URL lejátszhatósága (FFmpeg-gel)
  ellenőrizve; a hang/kép lejátszását ember nem nézte végig.
- **GitHub Actions** workflow: nem futott (a tároló még nincs közzétéve).
- **Böngészősütik** (korhatáros videók): nem tesztelt (bejelentkezett fiókot igényel).
- **Nagyon nagy (több ezer elemes) lejátszási lista**: csak kis listával tesztelve; a lista
  nézet virtualizált (QListView), a flat-playlist elemzés nem tölti le az egyes videók adatait.
- **Nagy DPI**: valódi 150%-os monitor nem volt; 100%-on és `QT_SCALE_FACTOR=1.5`
  szimulációval ellenőrizve (képernyőképen: éles vektoros ikonok, arányos elrendezés).
- **Világos/sötét téma**: mindkettő képernyőképen ellenőrizve, a váltás újraindítás nélkül
  működik (GUI-teszt is).
