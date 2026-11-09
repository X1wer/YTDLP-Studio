# YTDLP Studio – tesztjelentés

## 0.3.0 kiegészítés (2026-11-09) – angol felület

| Ellenőrzés | Eredmény |
|---|---|
| Automatikus tesztek | ✅ **59/59** (Windows-asztalon és képernyő nélküli `QT_QPA_PLATFORM=offscreen` módban is) |
| Fordítás teljessége | ✅ minden fordítandó szövegnek (~485) van angol párja, a helyőrzők egyeznek, nincs gyorsbillentyűt okozó „&” |
| Angol felület végigjárása (teszt) | ✅ kezdőképernyő, videó (24 hangsáv, 174 felirat), mindhárom mód, vágás, lejátszási lista, letöltési sor és várakozási sáv, Beállítások, Eszközök, Napló, Részletek: **0 magyar szöveg** (ugyanez magyar módban 69 találatot ad, tehát a teszt érzékeny) |
| Képernyőkép (angol, világos és sötét) | ✅ |
| Nyelvváltás újraindítással | ✅ beállítás és újraindítás-kérdés bekötve; az újraindítást a kész EXE-vel ellenőrizni kell |

## 0.2.4 kiegészítés (2026-11-08)

A felhasználói visszajelzés szerint a böngészőben nem jelenik meg ellenőrzés, így az
„Ellenőrzés a böngészőben” funkció nem segített; eltávolítva.

| Ellenőrzés | Eredmény |
|---|---|
| Automatikus tesztek | ✅ **54/54** (a böngészős funkció tesztjei helyett: robotellenőrzésnél nincs hamis megoldási javaslat, csak magyarázat; fordított felirat 429 → „nem oldható meg” magyarázat, nincs várakoztatás; más felirat 429 → valódi korlátozásként kezelve; a feliratlistában a fordítások jelölése és súgója) |

## 0.2.3 kiegészítés (2026-11-08)

| Ellenőrzés | Eredmény |
|---|---|
| Automatikus tesztek | ✅ **56/56** (3 új: 429-es hibánál is felkínált böngészős ellenőrzés és a vezető ablak 429-es szövege; csak a hiányzó felirat újrapróbálása új feladatként, böngészővel, a videó újbóli letöltése nélkül; „Csak felirat” módban a 429 korlátozásként kerül besorolásra) |
| Képernyőkép | ✅ kész, de felirathibás kártya pajzs ikonnal és megoldási javaslattal; „Felirat újrapróbálása” vezető ablak |
| Bejelentkezett munkamenettel a YouTube kiadja-e a fordított feliratot | ❌ nem tesztelt (a felhasználó fiókjával nem próbáltam); a program ezt őszintén jelzi |

## 0.2.2 kiegészítés (2026-11-08)

| Ellenőrzés | Eredmény |
|---|---|
| Automatikus tesztek | ✅ **53/53** (3 új: lenyitható kártya valódi egérkattintással az állapotsorra, a „Technikai részletek” link a pontos yt-dlp-üzenetet adja át; pajzs gomb → böngészős újrapróbálás friss lekéréssel és a választott böngészővel; az „Ellenőrzés a böngészőben” ablak böngészőfüggő tanácsai és a beállítás mentése) |
| Hibatípusok | ✅ robotellenőrzés / túl sok kérés / bejelentkezés / sütihiba külön ismerve fel |
| Képernyőkép (világos és sötét) | ✅ lenyitott figyelmeztetés és hiba, várakozási sáv két gombbal, vezető ablak |
| Valós robotellenőrzés + böngészős igazolás | ❌ nem tesztelt: a teszt idején nem volt aktív korlátozás, és valódi felhasználói fiókkal nem próbáltam |

## 0.2.1 kiegészítés (2026-11-08)

Felhasználói hibajelentés: „AttributeError: 'NoneType' object has no attribute 'status'”
egy YouTube Shorts videó letöltésekor. A napló (`data\logs\ytdlp-studio.log`) szerint a
hiba a letöltési lista buboréksúgójában keletkezett, amikor az egérmutató a lista üres
része fölött állt meg (a Qt ilyenkor érvénytelen indexszel kéri a súgót). A letöltés
sikeres volt. Javítva mindkét listatípusban.

| Ellenőrzés | Eredmény |
|---|---|
| Automatikus tesztek | ✅ **50/50** (6 új: buboréksúgó-regresszió, korlátozás → várakozás + egyszeri automatikus újrapróbálás, hibatípus-besorolás, mentett elemzés használata és lejárt link esetén friss lekérés, kíméletes mód) |
| Valós: elemzés után letöltés (Me at the zoo, M4A + angol felirat) | ✅ a letöltés alatt **0** YouTube-oldallekérés (korábban 2 teljes lekérdezés feladatonként) |
| Valós: `--load-info-json` vágott részlettel (Big Buck Bunny) | ✅ |
| Automatikusan fordított magyar felirat (a hibajelentés videója) | ⚠️ továbbra is 429 – a YouTube elutasítja; a program figyelmeztet, a videó letöltődik |

---

# 0.2.0 – tesztjelentés

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

Három futás történt ugyanazon a napon: **A** – a javítások előtt (16:xx), **B** – a végleges kóddal
(19:xx), **C** – külön a megszakítás ellenőrzése a javítás után. A B futás idejére a YouTube a
napi sok tesztkérés miatt ideiglenes robotellenőrzést kért ettől az IP-címtől; ezeket a
lépéseket a program helyesen, magyarul jelezte („A YouTube ideiglenesen robotnak nézte a
kéréseket…”), de a letöltés nem futott le.

| Ellenőrzés | A | B | Eredmény / mért érték |
|---|---|---|---|
| Elemzés (Big Buck Bunny) | ✅ | ✅ | 635 s, max. 2160p60 |
| Videórészlet MP4 360p, 01:00–01:10 | ✅ | ✅ | 10,03 s, 360p videósáv (+ beágyazott borítókép), 464 KB |
| WebM formátum érvényesül, 240p | ✅ | ✅ | `.webm`, AV1 + Opus |
| Csak hang MP3, 30 s részlet | ✅ | ✅ | 30,0 s MP3 |
| Feliratok beágyazva MKV-ba (en + de) | ✅ | ⚠️ robotellenőrzés | feliratsávok: `deu`, `eng` |
| Vágott részlet + felirat igazítása (00:05–00:12) | ✅ | ⚠️ robotellenőrzés | külön SRT, első felirat 00:00:00,318-nál |
| Csak felirat: YouTube automatikus magyar fordítás | ⚠️ 429 | ⚠️ 429 | a YouTube elutasítja; érthető figyelmeztetés |
| Több hangsáv egy MKV-ban (de + es, 3 s) | ✅ | ⚠️ robotellenőrzés | hangsávok: `deu`, `spa` (a fájl utána törölve) |
| Csatornalink → Videók lista | ✅ | ✅ | `@jawed` → „Videos” lista |
| Megszakítás 4K letöltés közben | ❌ → javítva, **C: ✅** | ⚠️ robotellenőrzés | C: azonnali leállás, 0 árva yt-dlp/FFmpeg, ideiglenes mappa törölve |
| Ékezetes mentési mappa | ✅ | ✅ | `Ékezetes ő ű mappa\Me at the zoo [jNQXAC9IVRw].m4a` |
| yt-dlp frissítés élesben (ideiglenes mappába) | ✅ | ✅ | GitHub-letöltés, SHA-256 OK, `--version` fut, előző verzió mentve |

Az **A** futás hibája (megszakítás után túl korán futó takarítás, a leállított FFmpeg még fogta
a fájlt) javítva lett: a takarítás rövid ideig újrapróbálkozik, és háttérszálon fut.

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
