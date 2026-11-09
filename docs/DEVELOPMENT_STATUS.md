# Fejlesztési állapot és további lehetőségek

**Aktuális verzió: 0.3.1** (2026-11-09). A változások a `CHANGELOG.md`-ben, a tesztek
eredménye a `docs/TEST_REPORT.md`-ben olvasható.

## Architektúra röviden

- `core.py` – tiszta logika (nincs I/O): yt-dlp JSON → modellek, formátumválasztók,
  argumentumlisták, méretbecslés. Minden felhasználói érték ellenőrzött; parancssor-sztring
  nem készül (nincs shell injection), a fájlnevek a yt-dlp `--windows-filenames`
  szabályaival és saját mappanév-tisztítással készülnek (nincs path traversal).
- `engine.py` – folyamatkezelés: elemzés, `DownloadTask` (saját munkamappa, haladás,
  feliratok, helyi vágás, beágyazás, ütközésmentes véglegesítés), Windows Job Object.
- `ui/` – PySide6-felület; a hosszú műveletek háttérszálon futnak, a felület csak Qt-jelzéseket
  kap, így letöltés közben sem fagy le.

## További fejlesztési lehetőségek
1. Kódaláírás (SmartScreen-figyelmeztetés megszüntetése) – tanúsítvány szükséges.
2. A letöltési sor mentése kilépéskor és visszaállítása induláskor.
3. FFmpeg és Deno frissítése a programból (jelenleg a csomag újraépítésével frissülnek).
4. Automatikusan fordított YouTube-feliratok: a YouTube jelenleg 429-cel elutasítja őket; ha a
   yt-dlp új megoldást ad (pl. PO-token támogatás), a program frissítés után automatikusan
   profitál belőle.
