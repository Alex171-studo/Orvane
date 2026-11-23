import io
import wave
from pathlib import PurePath

from src.domain.errors import AudioValidationError

MIMES = {
    "wav": {"audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "m4a": {"audio/mp4", "audio/m4a", "audio/x-m4a"},
    "ogg": {"audio/ogg", "application/ogg"},
    "webm": {"audio/webm", "video/webm"},
}


def validate_audio(name: str, mime: str | None, data: bytes, max_mb: int) -> str:
    if not data or len(data) > max_mb * 1_000_000:
        raise AudioValidationError("Fichier vide ou supérieur à la limite configurée.")
    if any(c in name for c in ("/", "\\", "\x00", ":")) or len(name) > 255:
        raise AudioValidationError("Nom de fichier invalide.")
    ext = PurePath(name).suffix.lower().lstrip(".")
    media = (mime or "").lower().partition(";")[0].strip()
    if ext not in MIMES or (
        media not in ("", "application/octet-stream") and media not in MIMES[ext]
    ):
        raise AudioValidationError("Extension ou type MIME incompatible.")
    identified = False
    if ext == "wav":
        try:
            with wave.open(io.BytesIO(data)) as sound:
                identified = sound.getnframes() > 0 and bool(sound.readframes(1))
        except (wave.Error, EOFError):
            pass
    elif ext == "ogg":
        identified = data.startswith(b"OggS\x00") and any(
            tag in data[:256] for tag in (b"OpusHead", b"vorbis", b"FLAC", b"Speex")
        )
    elif ext == "m4a":
        identified = len(data) > 16 and data[4:8] == b"ftyp" and b"mdat" in data
    elif ext == "webm":
        identified = data.startswith(b"\x1aE\xdf\xa3") and b"webm" in data[:256]
    elif ext == "mp3":
        offset = 0
        if data.startswith(b"ID3") and len(data) >= 10:
            for byte in data[6:10]:
                offset = (offset << 7) | (byte & 127)
            offset += 10
        frame = data[offset : offset + 4]
        identified = (
            len(frame) == 4
            and frame[0] == 255
            and frame[1] & 224 == 224
            and frame[1] & 6 != 0
            and frame[2] >> 4 not in (0, 15)
        )
    if not identified:
        raise AudioValidationError("Le contenu audio ne correspond pas au format annoncé.")
    return ext
