"""End-to-end orchestration test using an executable yt-dlp stand-in.

Does not contact YouTube or fetch any media.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ytstudio.core import DownloadOptions, Subtitle
from ytstudio.engine import Engine

FAKE_CLI = r'''#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
if '--dump-single-json' in args:
 print(json.dumps({'id':'vid123','title':'Mock','duration':33,'formats':[]}))
 sys.exit(0)
if '-P' not in args:
 print('ERROR: missing destination')
 sys.exit(1)
folder = Path(args[args.index('-P')+1]); folder.mkdir(parents=True,exist_ok=True)
if '--skip-download' in args:
 (folder/'Mock [vid123].en.srt').write_text('1\n00:00:09,000 --> 00:00:12,000\nHello\n\n2\n00:00:14,000 --> 00:00:18,000\nBye\n', encoding='utf8')
 print('Subtitles written')
else:
 path=folder/'Mock [vid123].mkv'
 path.write_bytes(b'MOCK DATA')
 print('[download] 100.0% of 1MiB')
 print('__YTDLPSTUDIO_OUTPUT__'+str(path))
'''


class EngineIntegrationTest(TestCase):
    def test_metadata_and_clip_subtitle_download(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = root / 'yt-dlp'
            cli.write_text(FAKE_CLI, encoding='utf8')
            cli.chmod(0o755)
            original_find_exe = __import__('ytstudio.settings', fromlist=['find_exe']).find_exe
            def fake_find(name):
                return cli if name == 'yt-dlp' else original_find_exe(name)
            engine = Engine()
            with patch('ytstudio.engine.find_exe', side_effect=fake_find):
                raw = engine.analyze('https://example.org/vid123')
                self.assertEqual(raw['id'], 'vid123')
                log = []
                opts = DownloadOptions(url='https://example.org/vid123', dest=str(root), container='mkv',
                                       start=10.0, end=16.0,
                                       subtitles=[Subtitle('en', 'manual', 'English')])
                result = engine.download(opts, log.append)
                self.assertTrue(Path(result).exists())
                caption = root/'Mock [vid123].en.srt'
                self.assertTrue(caption.exists())
                adjusted = caption.read_text(encoding='utf8')
                self.assertIn('00:00:00,000 --> 00:00:02,000', adjusted)
                self.assertIn('00:00:04,000 --> 00:00:06,000', adjusted)
                self.assertTrue(any('Mentés:' in line for line in log))
