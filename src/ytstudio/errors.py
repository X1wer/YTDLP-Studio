"""A yt-dlp / FFmpeg technikai hibaüzeneteinek érthető magyar magyarázata."""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from .i18n import N_, tr


@dataclass(frozen=True)
class FriendlyError:
    title: str
    message: str
    retryable: bool = True
    # "rate_limit": túl sok kérés (429); "bot_check": robotellenőrzés – mindkettőnél a sor
    # automatikusan szünetel, és később újrapróbálkozik. "login": bejelentkezés kell.
    kind: str = ""

    @property
    def throttled(self) -> bool:
        return self.kind in ("rate_limit", "bot_check")


_RULES: list[tuple[str, FriendlyError]] = [
    (r"Unsupported URL", FriendlyError(
        N_("Nem támogatott link"),
        N_("Ezt a linket a yt-dlp nem ismeri fel videóként. Ellenőrizd, hogy a teljes, "
        "böngészőből kimásolt videólinket illesztetted-e be."), False)),
    (r"DRM|drm protected|This video is DRM", FriendlyError(
        N_("DRM-védett tartalom"),
        N_("A tartalom másolásvédelemmel (DRM) rendelkezik, ezért a program nem tölti le."), False)),
    (r"Private video|This video is private", FriendlyError(
        N_("Privát videó"),
        N_("A videó privát, csak a feltöltő által engedélyezett fiókokkal nézhető meg."), False)),
    (r"Video unavailable|This video is unavailable|has been removed|account associated with this video has been terminated", FriendlyError(
        N_("A videó nem érhető el"),
        N_("A videót törölték, letiltották, vagy a feltöltő eltávolította."), False)),
    (r"not available in your country|geo.?restrict|blocked it in your country", FriendlyError(
        N_("Földrajzi korlátozás"),
        N_("A videó ebben az országban nem érhető el."), False)),
    (r"Sign in to confirm your age|age.?restricted|inappropriate for some users", FriendlyError(
        N_("Korhatáros videó"),
        N_("A videó megtekintéséhez bejelentkezés szükséges. A Beállításokban megadhatod, hogy a "
        "program egy olyan böngésző sütijeit használja, amelyben be vagy jelentkezve a "
        "YouTube-ra (Firefox ajánlott)."), kind="login")),
    (r"Sign in to confirm you.?re not a bot|confirm you are not a robot|LOGIN_REQUIRED", FriendlyError(
        N_("A YouTube ellenőrzést kér"),
        N_("A YouTube rövid időn belül túl sok kérést kapott erről a hálózatról, ezért ideiglenesen "
        "robotnak nézte őket. Ezt az ellenőrzést a programból nem lehet elvégezni: a YouTube a "
        "letöltőprogramoknak nem küld kitölthető ellenőrzést, csak elutasítja a kérést (a böngészőben "
        "ezért nem is látszik semmi). Általában néhány perc–óra alatt magától megszűnik; a program "
        "addig szünetelteti a letöltési sort, majd újrapróbálkozik. Ha tartósan fennáll, frissítsd a "
        "yt-dlp-t (Eszközök menü)."), kind="bot_check")),
    (r"members.?only|Join this channel", FriendlyError(
        N_("Csak csatornatagoknak"),
        N_("Ez a videó csak a csatorna fizetős tagjai számára érhető el."), False)),
    (r"Premieres in|This live event will begin|is_upcoming|will begin in", FriendlyError(
        N_("Még nem kezdődött el"),
        N_("Ez egy későbbi premier vagy élő közvetítés. A kezdés után próbáld újra."))),
    (r"HTTP Error 429|Too Many Requests", FriendlyError(
        N_("Túl sok kérés (429)"),
        N_("A YouTube rövid idő alatt túl sok kérést kapott erről a hálózatról. Ezt a programból nem "
        "lehet feloldani; általában néhány perc–óra alatt magától megszűnik. A program addig "
        "szünetelteti a letöltési sort, majd újrapróbálkozik."), kind="rate_limit")),
    (r"HTTP Error 403|Forbidden", FriendlyError(
        N_("Hozzáférés megtagadva (403)"),
        N_("A szerver elutasította a letöltést. Ez gyakran a yt-dlp elavultságát jelzi: frissítsd az "
        "Eszközök menüben, majd próbáld újra."), kind="update")),
    (r"HTTP Error 404", FriendlyError(
        N_("Nem található (404)"),
        N_("A kért tartalom vagy formátum nem létezik a szerveren."))),
    (r"HTTP Error 5\d\d", FriendlyError(
        N_("Szerverhiba"),
        N_("A szolgáltató szervere hibát jelzett. Később érdemes újrapróbálni."))),
    (r"Requested format is not available|No video formats found", FriendlyError(
        N_("A kért formátum nem érhető el"),
        N_("A kiválasztott minőség, formátum vagy hangsáv ennél a videónál nem létezik. Válassz más "
        "beállítást, vagy hagyd a minőséget „Legjobb” értéken."))),
    (r"getaddrinfo failed|Name or service not known|No address associated|Failed to resolve|"
     r"Temporary failure in name resolution|nodename nor servname", FriendlyError(
        N_("Nincs internetkapcsolat"),
        N_("A szerver neve nem oldható fel. Ellenőrizd az internetkapcsolatot."))),
    (r"timed out|Read timed out|Connection reset|RemoteDisconnected|IncompleteRead|"
     r"ConnectionResetError|Connection aborted", FriendlyError(
        N_("Megszakadt a kapcsolat"),
        N_("A hálózati kapcsolat megszakadt vagy túl lassú. Az újrapróbálás folytatja a letöltést."))),
    (r"CERTIFICATE_VERIFY_FAILED|SSLError|\[SSL", FriendlyError(
        N_("Biztonságos kapcsolat hiba"),
        N_("A HTTPS-tanúsítvány nem ellenőrizhető. Ellenőrizd a rendszeridőt és a vírusirtó/proxy "
        "beállításait."))),
    (r"No space left on device|Errno 28|There is not enough space", FriendlyError(
        N_("Betelt a lemez"),
        N_("Nincs elég szabad hely a mentési meghajtón. Szabadíts fel helyet vagy válassz másik mappát."))),
    (r"Permission denied|Errno 13|Access is denied|WinError 5", FriendlyError(
        N_("Nincs írási jogosultság"),
        N_("A mentési mappába nem lehet írni, vagy egy fájlt másik program használ. Válassz másik "
        "mappát, vagy zárd be a fájlt megnyitó programot."))),
    (r"ffmpeg not found|ffprobe and ffmpeg not found|ffmpeg is not installed", FriendlyError(
        N_("Hiányzik az FFmpeg"),
        N_("A program mappájából hiányzik a bin\\ffmpeg.exe. Csomagold ki újra a teljes portable ZIP-et."),
        False)),
    (r"Postprocessing: Conversion failed|Error opening output|Invalid data found", FriendlyError(
        N_("Utófeldolgozási hiba"),
        N_("Az FFmpeg nem tudta átalakítani a fájlt. Próbálj másik formátumot (pl. MKV) vagy kapcsold ki "
        "a pontos vágást."))),
    (r"[Cc]ookies|could not find .* cookies database|Failed to decrypt", FriendlyError(
        N_("Böngészősütik nem olvashatók"),
        N_("A kiválasztott böngésző sütijei nem olvashatók (a böngészőt be kell zárni, a Chrome újabb "
        "verziói pedig titkosítják őket). Próbáld a Firefoxot, vagy kapcsold ki a sütiket."),
        kind="cookies")),
    (r"is_live|live event|live stream", FriendlyError(
        N_("Élő közvetítés"),
        N_("Élő közvetítés letöltése a közvetítés végéig tarthat, és vágás nem alkalmazható rá."))),
    (r"JavaScript runtime|js.?runtime|jsc:|n challenge|nsig|Signature extraction failed", FriendlyError(
        N_("YouTube-ellenőrzés sikertelen"),
        N_("A YouTube lejátszóellenőrzését nem sikerült megoldani. Frissítsd a yt-dlp-t az Eszközök "
        "menüben; ha nem segít, ellenőrizd, hogy a bin\\deno.exe megvan-e."), kind="update")),
]


def explain(technical: str) -> FriendlyError:
    text = technical or ""
    for pattern, friendly in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            # A szabályok import időben jönnek létre, ezért a fordítás itt történik.
            return replace(friendly, title=tr(friendly.title), message=tr(friendly.message))
    first = next((line for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]+:\s*)?", "", first).strip()
    return FriendlyError(tr("A művelet nem sikerült"),
                         (first[:300] + ("…" if len(first) > 300 else "")) if first
                         else tr("Ismeretlen hiba történt. A részleteket a naplóban találod."))
