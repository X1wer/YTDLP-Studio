# Változásnapló

## 0.2.2 – 2026-11-08

- **Ellenőrzés a böngészőben:** robotellenőrzésnél vagy bejelentkezést igénylő (pl. korhatáros)
  videónál vezető ablak nyílik: megnyitja a videót a saját böngésződben, ahol bejelentkezhetsz
  vagy elvégezheted az ellenőrzést, majd a program a kiválasztott böngésző munkamenetével
  újrapróbálja. Felismeri a telepített böngészőket, és figyelmeztet a Chrome-alapú böngészők
  sütititkosítására. Elérhető az elemzési hibánál, a letöltési kártya pajzs ikonjával és a
  várakozási sávból. A sütiket a program nem menti el.
- **Lenyitható letöltési kártyák:** figyelmeztetésnél és hibánál a kártya az állapotsorra vagy a
  nyíl ikonra kattintva lenyílik, és olvasható a teljes magyarázat; innen a „Technikai részletek
  megnyitása…” link a pontos yt-dlp-üzenetet is megmutatja. A figyelmeztetéses kész letöltés
  ikonja sárga.
- A hibák típus szerint különülnek el (robotellenőrzés, túl sok kérés, bejelentkezés szükséges,
  böngészősütik nem olvashatók).
- A várakozási sáv a keskeny letöltési panelen is olvasható (gombok a szöveg alatt).

## 0.2.1 – 2026-11-08

### Javítva
- „Váratlan hiba… AttributeError: 'NoneType' object has no attribute 'status'” üzenet jelent meg,
  ha az egérmutató a letöltési lista (vagy a hangsáv-/feliratlista) üres része fölött állt meg.
  A letöltést nem érintette; a buboréksúgó most üres területen nem jelenik meg.

### Kevesebb YouTube-kérés, kíméletesebb működés
- A letöltés az elemzéskor kapott adatokat használja (`--load-info-json`), így egy
  letöltés – feliratokkal együtt – **1 YouTube-lekérdezésbe** kerül a korábbi 3 helyett.
  Ez jelentősen csökkenti a „robotellenőrzés” és a „túl sok kérés” esélyét.
  Ha az elemzés óta a letöltési linkek lejártak (YouTube: kb. 6 óra), a program magától
  friss lekérésre vált.
- **Automatikus várakozás korlátozáskor:** ha a YouTube robotellenőrzést kér vagy „túl sok
  kérés” (429) hibát ad, a letöltési sor 15 percig nem indít új letöltést (visszaszámláló sáv
  „Folytatás most” gombbal), majd magától folytatódik, és az érintett letöltést egyszer
  automatikusan újrapróbálja. Elemzés közbeni korlátozásnál is így tesz, és felajánlja a
  böngészősütik beállítását.
- Lejátszási listák letöltésekor rövid szünetek a kérések között (kíméletes tempó).
- A program semmilyen ellenőrzést nem kerül meg: csak kivár és kevesebb kérést küld.

### Build
- A build tiszta munkamappába készül; a ZIP-be sosem kerül felhasználói adat, a
  `dist\YTDLPStudio\data` (beállítások, napló) újraépítéskor megmarad, és ha a program éppen
  fut a `dist` mappából, a build nem írja felül.

## 0.2.0 – 2026-11-08

Teljes átdolgozás: új grafikus felület, újraírt letöltőmotor, valós Windowsos tesztek.

### Új felület (PySide6 / Qt 6)
- A Tkinter-felületet modern Qt-felület váltotta: világos, sötét és rendszer szerinti téma
  **újraindítás nélkül**, sötét natív címsor, DPI-skálázás (125–200%), átméretezhető ablak,
  új ikon, magyar Qt-szövegek (pl. Igen/Nem gombok).
- Logikus munkafolyamat: link → elemzés → mit töltsünk le (Videó / Csak hang / Csak felirat) →
  hangsávok és feliratok → opcionális vágás → **Letöltés most** vagy **Hozzáadás a sorhoz**.
- Üdvözlő képernyő lépésekkel; a link az ablakra húzva is beilleszthető; a Beillesztés
  gomb szövegből is kiemeli a linket és automatikusan elemez.
- Videókártya nagy bélyegképpel, időtartammal, csatornával, dátummal, megtekintésekkel,
  elérhető legjobb minőséggel, hangsáv-, felirat- és fejezetszámmal.
- **Beépített előnézet-lejátszó** (Qt Multimedia, csak kérésre töltődik be), „Kezdőpont ide” /
  „Végpont ide” gombokkal a vágáshoz.
- Formátumválasztás szegmensgombokkal és megbízható legördülő listákkal; a nem elérhető
  lehetőségek letiltva, magyarázó buboréksúgóval (pl. WebM nem kompatibilis forrásnál, több
  hangsávnál csak MKV).
- Hangsávok és feliratok egymás melletti, **kereshető (ékezetfüggetlen), görgethető,
  jelölőnégyzetes** listákban; típusszűrő (eredeti / szinkron / automatikus / fordítás),
  „Csak kijelöltek” nézet, kijelölés törlése, ★ preferált nyelvek. A szűrés soha nem
  törli a kijelöléseket; az egész sorra kattintva lehet jelölni.
- Vágás: idővonal két húzható végponttal és fejezetjelölőkkel, kézzel szerkeszthető
  időmezők, fejezetválasztó, „Pontos vágás”, valamint „Teljes letöltés, utána vágás” mód.
- Rögzített műveletsáv: mentési mappa, **becsült fájlméret**, részlethossz.
- Letöltési sor jobb oldali panelben: állapot, haladás, sebesség, hátralévő idő,
  utófeldolgozási lépés (pl. „Sávok összefűzése…”), megszakítás, újrapróbálás, fájl és mappa
  megnyitása, hiba részletei, helyi menü, szüneteltetés, „Sikertelenek újra”.
- Érthető magyar hibaüzenetek (403, 429, bot-ellenőrzés, privát/korhatáros/törölt videó,
  DRM, nincs internet, betelt lemez, jogosultság…) újrapróbálás és technikai részletek
  gombbal; külön, kereshető technikai napló ablak és naplófájl.
- Lejátszási listák: listanézet kijelöléssel és kereséssel, almappa a lista nevével,
  sorszám a fájlnév elején, preferált felirat- és hangsávnyelv; csatornalinkeknél a
  „Videók” lista töltődik be.
- Beállítások ablak: mappa, téma, preferált nyelvek, párhuzamos letöltések (1–3),
  sebességkorlát, böngészősütik (korhatáros videókhoz), automatikus elemzés.
- Eszközök és frissítés ablak: összetevők verziói, yt-dlp **Stable/Nightly** frissítés,
  előző verzió visszaállítása.

### Letöltőmotor és stabilitás
- **Javítva:** az ékezetes címek és fájlnevek sérültek, mert a yt-dlp Windows alatt nem
  UTF-8-ban írt a programnak (`--encoding utf-8`).
- **Javítva:** a haladásjelző nem frissült (a `--print` csendes módot kapcsolt be).
  Új, gépi feldolgozású haladássablon; több sáv esetén összesített százalék.
- **Javítva:** az „eredeti hangsáv” sosem volt felismerve. A hangsávok most nyelv és
  típus szerint (eredeti / szinkron / AI-szinkron csak YouTube-jelölés esetén / narrált)
  jelennek meg, és nyelvi szűrővel kerülnek kiválasztásra.
- **Javítva:** fájlnév-ütközésnél a letöltés kimaradt; most „(2)”, „(3)” utótag kerül a
  névbe, a feliratfájlok is követik.
- **Javítva:** gyors vágásnál MKV-ban a feliratok elcsúsztak (a hang a kulcskocka miatt
  később indul) – a program méri és kompenzálja az eltolást.
- **Javítva:** egy sikertelen felirat (pl. 429) az egész letöltést meghiúsíthatta; a
  feliratok most külön, nem végzetes lépésben töltődnek le, figyelmeztetéssel.
- **Javítva:** azonos nyelvű kézi és automatikus felirat felülírta egymást (`.auto` utótag).
- Minden feladat saját rejtett munkamappában fut; megszakításkor és kilépéskor az
  ideiglenes fájlok törlődnek. Windows Job Object biztosítja, hogy a yt-dlp és az
  FFmpeg-folyamatok összeomlás esetén se maradjanak futva.
- Feliratbeágyazás MP4/MKV/WebM fájlba **nyelvi címkével**; metaadatok, borítókép és
  fejezetek beágyazása; többnyelvű hangsávok MKV-ban nyelvi címkével.
- MP4-nél azonos felbontáson a legkompatibilisebb kodek (H.264/AAC) az előnyben; választható
  kodek (H.264 / VP9 / AV1). Hangformátumok: MP3, M4A, AAC, Opus, FLAC, WAV és
  átkódolás nélküli „Eredeti”; több kijelölt hangsáv külön fájlokba.
- A letöltött fájl dátuma a letöltés ideje (nem a feltöltésé), így a mappában a legújabbak
  között jelenik meg.
- yt-dlp és Deno gyorsítótár a program `data` mappájában (USB-ről is hordozható).
- DRM-védett tartalmat a program felismer és nem tölt le.

### Frissítő
- Stable és Nightly csatorna a hivatalos GitHub-kiadásokból; a GitHub `digest` és a
  kiadás `SHA2-256SUMS` fájlja **keresztellenőrizve**.
- **Javítva:** sikertelen frissítés törölte a korábbi biztonsági mentést; most a mentés
  csak sikeres telepítés után cserélődik. Kézi visszaállítás az előző verzióra.

### Build, szerkezet, dokumentáció
- Új mappaszerkezet: `src/`, `assets/`, `tests/`, `build/`, `docs/`, `dist/`.
- PyInstaller **onedir** portable mappa (gyorsabb indulás, LGPL-kompatibilis), EXE
  verzióinformációval és ikonnal; portable ZIP SHA-256 ellenőrzőösszeggel.
- A beállítások a `data/settings.json` fájlba kerülnek (a v0.1 beállításai átvéve).
- 44 automatikus teszt (valós YouTube-metaadat mintákon, valódi FFmpeg-gel és
  kattintásos Qt-felülettesztekkel) + kézi futtatású élő hálózati ellenőrzés.
- Teljes licencinformáció (LGPL/GPL/PSF/Unlicense/MIT) a `licenses` mappában.

## 0.1.3 – 2026-11-01
- Legördülő menük cseréje natív menükre, jelölőnégyzetes felirat- és hangsávlisták
  egymás mellett, nagyobb bélyegképes előnézet.

## 0.1.2 – 2026-11-01
- A buildszkript a Python 3.11–3.13-at és a `py` launchert is felismeri.

## 0.1.1 – 2026-11-01
- PowerShell-szintaktikai hiba javítása a buildszkriptben.

## 0.1 – első változat
