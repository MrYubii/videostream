import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from app.config import get_settings

settings = get_settings()

TRANSCODE_WIDTH = 1280
TRANSCODE_CRF = 23


def _ffmpeg() -> str:
    return settings.ffmpeg_path or imageio_ffmpeg.get_ffmpeg_exe()


class MediaProcessor:
    def probe(self, source_path: Path) -> tuple[int, int]:
        cmd = [_ffmpeg(), "-i", str(source_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            return 0, 0
        stderr = result.stderr or ""
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
        duration = 0
        if match:
            h, m, s = match.groups()
            duration = int(h) * 3600 + int(m) * 60 + int(float(s))
        size = source_path.stat().st_size if source_path.exists() else 0
        return duration, size

    def has_audio(self, source_path: Path) -> bool:
        try:
            result = subprocess.run(
                [_ffmpeg(), "-i", str(source_path)], capture_output=True, text=True, timeout=60
            )
        except (subprocess.TimeoutExpired, OSError):
            return True
        return "Audio:" in (result.stderr or "")

    def transcode(self, source_path: Path, output_path: Path) -> bool:
        """Normalise uploads to a browser-friendly MP4 (720p H.264 + AAC, faststart).

        Scales down oversized footage, caps the bitrate, adds a silent audio track
        when the source has none, and moves the moov atom to the front so playback
        and seeking start instantly over HTTP Range streaming.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        inputs = [_ffmpeg(), "-y", "-i", str(source_path)]
        maps = ["-map", "0:v:0"]
        if not self.has_audio(source_path):
            inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            maps += ["-map", "1:a:0"]
        else:
            maps += ["-map", "0:a:0"]
        cmd = inputs + maps + [
            "-vf", f"scale='min({TRANSCODE_WIDTH},iw)':-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(TRANSCODE_CRF),
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def make_thumbnail(self, source_path: Path, thumb_path: Path) -> bool:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            _ffmpeg(),
            "-y",
            "-ss", "0.5",
            "-i", str(source_path),
            "-frames:v", "1",
            "-vf", "scale=640:-2",
            "-q:v", "5",
            str(thumb_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0 and thumb_path.exists()
        except (subprocess.TimeoutExpired, OSError):
            return False
