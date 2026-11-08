"""Nyelvkódok magyar megnevezése és ISO 639-2 megfeleltetése.

A YouTube (és a yt-dlp) BCP 47-szerű kódokat ad, pl. ``hu``, ``en-US``,
``zh-Hans``, ``es-419`` vagy ``en-orig``. A felület magyar nevet mutat, a
konténerbe írt nyelvi metaadathoz pedig háromjegyű ISO 639-2 kód kell.
"""
from __future__ import annotations

import re

# ISO 639-1 / YouTube-kód -> magyar név
NAMES = {
    "aa": "afar", "ab": "abház", "af": "afrikaans", "ak": "akan", "am": "amhara",
    "ar": "arab", "as": "asszámi", "ay": "ajmara", "az": "azerbajdzsáni",
    "ba": "baskír", "be": "belarusz", "bg": "bolgár", "bho": "bhodzspuri",
    "bn": "bengáli", "bo": "tibeti", "br": "breton", "bs": "bosnyák",
    "ca": "katalán", "ceb": "szebuano", "co": "korzikai", "crs": "seychelle-szigeteki kreol",
    "cs": "cseh", "cy": "walesi", "da": "dán", "de": "német", "dv": "divehi",
    "dz": "dzongkha", "ee": "eve", "el": "görög", "en": "angol", "eo": "eszperantó",
    "es": "spanyol", "et": "észt", "eu": "baszk", "fa": "perzsa", "ff": "fulani",
    "fi": "finn", "fil": "filippínó", "fj": "fidzsi", "fo": "feröeri", "fr": "francia",
    "fy": "nyugati fríz", "ga": "ír", "gaa": "ga", "gd": "skót gael", "gl": "galíciai",
    "gn": "guarani", "gu": "gudzsaráti", "gv": "manx", "ha": "hausza", "haw": "hawaii",
    "he": "héber", "iw": "héber", "hi": "hindi", "hmn": "hmong", "hr": "horvát",
    "ht": "haiti kreol", "hu": "magyar", "hy": "örmény", "id": "indonéz", "ig": "igbo",
    "is": "izlandi", "it": "olasz", "iu": "inuktitut", "ja": "japán", "jv": "jávai",
    "ka": "grúz", "kha": "kaszi", "kk": "kazah", "kl": "grönlandi", "km": "khmer",
    "kn": "kannada", "ko": "koreai", "kri": "krio", "ku": "kurd", "ky": "kirgiz",
    "la": "latin", "lb": "luxemburgi", "lg": "ganda", "ln": "lingala", "lo": "lao",
    "lt": "litván", "lua": "luba-lulua", "luo": "luo", "lv": "lett", "mfe": "mauritiusi kreol",
    "mg": "malgas", "mi": "maori", "mk": "macedón", "ml": "malajálam", "mn": "mongol",
    "mr": "maráthi", "ms": "maláj", "mt": "máltai", "my": "burmai", "ne": "nepáli",
    "new": "nevari", "nl": "holland", "nb": "norvég (bokmål)", "nn": "norvég (nynorsk)",
    "no": "norvég", "nso": "északi szotó", "ny": "csiva", "oc": "okcitán", "om": "oromo",
    "or": "orija", "os": "oszét", "pa": "pandzsábi", "pam": "pampangan", "pl": "lengyel",
    "ps": "pastu", "pt": "portugál", "qu": "kecsua", "rm": "rétoromán", "rn": "kirundi",
    "ro": "román", "ru": "orosz", "rw": "kinyarvanda", "sa": "szanszkrit", "sd": "szindhi",
    "se": "északi számi", "sg": "szangó", "si": "szingaléz", "sk": "szlovák", "sl": "szlovén",
    "sm": "szamoai", "sn": "sona", "so": "szomáli", "sq": "albán", "sr": "szerb",
    "ss": "szvázi", "st": "déli szotó", "su": "szundanéz", "sv": "svéd", "sw": "szuahéli",
    "ta": "tamil", "te": "telugu", "tg": "tádzsik", "th": "thai", "ti": "tigrinya",
    "tk": "türkmén", "tl": "tagalog", "tn": "csvana", "to": "tongai", "tr": "török",
    "ts": "conga", "tt": "tatár", "tum": "tumbuka", "ug": "ujgur", "uk": "ukrán",
    "ur": "urdu", "uz": "üzbég", "ve": "venda", "vi": "vietnámi", "war": "waraj",
    "wo": "volof", "xh": "xhosza", "yi": "jiddis", "yo": "joruba", "yue": "kantoni",
    "zh": "kínai", "zu": "zulu",
}

# Régió- és írásváltozatok
VARIANTS = {
    "us": "USA", "gb": "Egyesült Királyság", "uk": "Egyesült Királyság", "au": "Ausztrália",
    "ca": "Kanada", "ie": "Írország", "in": "India", "nz": "Új-Zéland", "za": "Dél-Afrika",
    "br": "Brazília", "pt": "Portugália", "es": "Spanyolország", "mx": "Mexikó",
    "419": "Latin-Amerika", "ar": "Argentína", "fr": "Franciaország", "be": "Belgium",
    "ch": "Svájc", "de": "Németország", "at": "Ausztria", "cn": "Kína", "tw": "Tajvan",
    "hk": "Hongkong", "hans": "egyszerűsített", "hant": "hagyományos", "latn": "latin írás",
    "cyrl": "cirill írás", "orig": "eredeti", "it": "Olaszország", "jp": "Japán",
    "kr": "Korea", "ru": "Oroszország", "hu": "Magyarország",
}

# ISO 639-1 -> ISO 639-2/T (FFmpeg nyelvi metaadathoz)
ISO639_2 = {
    "af": "afr", "am": "amh", "ar": "ara", "as": "asm", "az": "aze", "be": "bel", "bg": "bul",
    "bn": "ben", "bo": "bod", "bs": "bos", "ca": "cat", "cs": "ces", "cy": "cym", "da": "dan",
    "de": "deu", "el": "ell", "en": "eng", "eo": "epo", "es": "spa", "et": "est", "eu": "eus",
    "fa": "fas", "fi": "fin", "fil": "fil", "fo": "fao", "fr": "fra", "fy": "fry", "ga": "gle",
    "gd": "gla", "gl": "glg", "gu": "guj", "ha": "hau", "he": "heb", "iw": "heb", "hi": "hin",
    "hr": "hrv", "ht": "hat", "hu": "hun", "hy": "hye", "id": "ind", "ig": "ibo", "is": "isl",
    "it": "ita", "ja": "jpn", "jv": "jav", "ka": "kat", "kk": "kaz", "km": "khm", "kn": "kan",
    "ko": "kor", "ku": "kur", "ky": "kir", "la": "lat", "lb": "ltz", "lo": "lao", "lt": "lit",
    "lv": "lav", "mg": "mlg", "mi": "mri", "mk": "mkd", "ml": "mal", "mn": "mon", "mr": "mar",
    "ms": "msa", "mt": "mlt", "my": "mya", "nb": "nob", "ne": "nep", "nl": "nld", "nn": "nno",
    "no": "nor", "or": "ori", "pa": "pan", "pl": "pol", "ps": "pus", "pt": "por", "qu": "que",
    "ro": "ron", "ru": "rus", "rw": "kin", "sa": "san", "sd": "snd", "si": "sin", "sk": "slk",
    "sl": "slv", "sm": "smo", "sn": "sna", "so": "som", "sq": "sqi", "sr": "srp", "st": "sot",
    "su": "sun", "sv": "swe", "sw": "swa", "ta": "tam", "te": "tel", "tg": "tgk", "th": "tha",
    "ti": "tir", "tk": "tuk", "tl": "tgl", "tr": "tur", "tt": "tat", "ug": "uig", "uk": "ukr",
    "ur": "urd", "uz": "uzb", "vi": "vie", "xh": "xho", "yi": "yid", "yo": "yor", "zh": "zho",
    "zu": "zul", "yue": "yue",
}

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


def is_valid_code(code: str) -> bool:
    return bool(code) and bool(_CODE_RE.fullmatch(code))


def base_code(code: str) -> str:
    return (code or "").replace("_", "-").split("-")[0].lower()


def language_name(code: str, fallback: str = "") -> str:
    """Magyar, nagybetűs nyelvnév, pl. ``en-US`` -> ``Angol (USA)``."""
    if not code or code.lower() in {"und", "none", "default"}:
        return fallback or "Ismeretlen nyelv"
    parts = code.replace("_", "-").split("-")
    name = NAMES.get(parts[0].lower())
    if not name:
        return fallback or code
    extra = [VARIANTS.get(p.lower(), p) for p in parts[1:] if p]
    text = name[:1].upper() + name[1:]
    return f"{text} ({', '.join(extra)})" if extra else text


def to_iso639_2(code: str) -> str | None:
    base = base_code(code)
    if len(base) == 3 and base.isalpha():
        return base
    return ISO639_2.get(base)


def matches_preference(code: str, preferred: list[str]) -> bool:
    base = base_code(code)
    return any(base == base_code(p) for p in preferred)
