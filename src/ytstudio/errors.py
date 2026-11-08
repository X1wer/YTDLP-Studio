"""A yt-dlp / FFmpeg technikai hibaüzeneteinek érthető magyar magyarázata."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FriendlyError:
    title: str
    message: str
    retryable: bool = True


_RULES: list[tuple[str, FriendlyError]] = [
    (r"Unsupported URL", FriendlyError(
        "Nem támogatott link",
        "Ezt a linket a yt-dlp nem ismeri fel videóként. Ellenőrizd, hogy a teljes, "
        "böngészőből kimásolt videólinket illesztetted-e be.", False)),
    (r"DRM|drm protected|This video is DRM", FriendlyError(
        "DRM-védett tartalom",
        "A tartalom másolásvédelemmel (DRM) rendelkezik, ezért a program nem tölti le.", False)),
    (r"Private video|This video is private", FriendlyError(
        "Privát videó",
        "A videó privát, csak a feltöltő által engedélyezett fiókokkal nézhető meg.", False)),
    (r"Video unavailable|This video is unavailable|has been removed|account associated with this video has been terminated", FriendlyError(
        "A videó nem érhető el",
        "A videót törölték, letiltották, vagy a feltöltő eltávolította.", False)),
    (r"not available in your country|geo.?restrict|blocked it in your country", FriendlyError(
        "Földrajzi korlátozás",
        "A videó ebben az országban nem érhető el.", False)),
    (r"Sign in to confirm your age|age.?restricted|inappropriate for some users", FriendlyError(
        "Korhatáros videó",
        "A videó megtekintéséhez bejelentkezés szükséges. A Beállításokban megadhatod, hogy "
        "a program egy bejelentkezett böngésző sütijeit használja.")),
    (r"Sign in to confirm you.?re not a bot|confirm you are not a robot|LOGIN_REQUIRED", FriendlyError(
        "A YouTube ellenőrzést kér",
        "A YouTube ideiglenesen robotnak nézte a kéréseket. Várj néhány percet, frissítsd a "
        "yt-dlp-t (Eszközök menü), vagy használd egy bejelentkezett böngésző sütijeit.")),
    (r"members.?only|Join this channel", FriendlyError(
        "Csak csatornatagoknak",
        "Ez a videó csak a csatorna fizetős tagjai számára érhető el.", False)),
    (r"Premieres in|This live event will begin|is_upcoming|will begin in", FriendlyError(
        "Még nem kezdődött el",
        "Ez egy későbbi premier vagy élő közvetítés. A kezdés után próbáld újra.")),
    (r"HTTP Error 429|Too Many Requests", FriendlyError(
        "Túl sok kérés (429)",
        "A szolgáltató átmenetileg korlátozza a letöltéseket. Várj néhány percet, majd próbáld újra.")),
    (r"HTTP Error 403|Forbidden", FriendlyError(
        "Hozzáférés megtagadva (403)",
        "A szerver elutasította a letöltést. Ez gyakran a yt-dlp elavultságát jelzi: frissítsd az "
        "Eszközök menüben, majd próbáld újra.")),
    (r"HTTP Error 404", FriendlyError(
        "Nem található (404)",
        "A kért tartalom vagy formátum nem létezik a szerveren.")),
    (r"HTTP Error 5\d\d", FriendlyError(
        "Szerverhiba",
        "A szolgáltató szervere hibát jelzett. Később érdemes újrapróbálni.")),
    (r"Requested format is not available|No video formats found", FriendlyError(
        "A kért formátum nem érhető el",
        "A kiválasztott minőség, formátum vagy hangsáv ennél a videónál nem létezik. Válassz más "
        "beállítást, vagy hagyd a minőséget „Legjobb” értéken.")),
    (r"getaddrinfo failed|Name or service not known|No address associated|Failed to resolve|"
     r"Temporary failure in name resolution|nodename nor servname", FriendlyError(
        "Nincs internetkapcsolat",
        "A szerver neve nem oldható fel. Ellenőrizd az internetkapcsolatot.")),
    (r"timed out|Read timed out|Connection reset|RemoteDisconnected|IncompleteRead|"
     r"ConnectionResetError|Connection aborted", FriendlyError(
        "Megszakadt a kapcsolat",
        "A hálózati kapcsolat megszakadt vagy túl lassú. Az újrapróbálás folytatja a letöltést.")),
    (r"CERTIFICATE_VERIFY_FAILED|SSLError|\[SSL", FriendlyError(
        "Biztonságos kapcsolat hiba",
        "A HTTPS-tanúsítvány nem ellenőrizhető. Ellenőrizd a rendszeridőt és a vírusirtó/proxy "
        "beállításait.")),
    (r"No space left on device|Errno 28|There is not enough space", FriendlyError(
        "Betelt a lemez",
        "Nincs elég szabad hely a mentési meghajtón. Szabadíts fel helyet vagy válassz másik mappát.")),
    (r"Permission denied|Errno 13|Access is denied|WinError 5", FriendlyError(
        "Nincs írási jogosultság",
        "A mentési mappába nem lehet írni, vagy egy fájlt másik program használ. Válassz másik "
        "mappát, vagy zárd be a fájlt megnyitó programot.")),
    (r"ffmpeg not found|ffprobe and ffmpeg not found|ffmpeg is not installed", FriendlyError(
        "Hiányzik az FFmpeg",
        "A program mappájából hiányzik a bin\\ffmpeg.exe. Csomagold ki újra a teljes portable ZIP-et.",
        False)),
    (r"Postprocessing: Conversion failed|Error opening output|Invalid data found", FriendlyError(
        "Utófeldolgozási hiba",
        "Az FFmpeg nem tudta átalakítani a fájlt. Próbálj másik formátumot (pl. MKV) vagy kapcsold ki "
        "a pontos vágást.")),
    (r"[Cc]ookies|could not find .* cookies database|Failed to decrypt", FriendlyError(
        "Böngészősütik nem olvashatók",
        "A kiválasztott böngésző sütijei nem olvashatók (a böngészőt be kell zárni, a Chrome újabb "
        "verziói pedig titkosítják őket). Próbáld a Firefoxot, vagy kapcsold ki a sütiket.")),
    (r"is_live|live event|live stream", FriendlyError(
        "Élő közvetítés",
        "Élő közvetítés letöltése a közvetítés végéig tarthat, és vágás nem alkalmazható rá.")),
    (r"JavaScript runtime|js.?runtime|jsc:|n challenge|nsig|Signature extraction failed", FriendlyError(
        "YouTube-ellenőrzés sikertelen",
        "A YouTube lejátszóellenőrzését nem sikerült megoldani. Frissítsd a yt-dlp-t az Eszközök "
        "menüben; ha nem segít, ellenőrizd, hogy a bin\\deno.exe megvan-e.")),
]


def explain(technical: str) -> FriendlyError:
    text = technical or ""
    for pattern, friendly in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return friendly
    first = next((line for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]+:\s*)?", "", first).strip()
    return FriendlyError("A művelet nem sikerült",
                         (first[:300] + ("…" if len(first) > 300 else "")) if first
                         else "Ismeretlen hiba történt. A részleteket a naplóban találod.")
