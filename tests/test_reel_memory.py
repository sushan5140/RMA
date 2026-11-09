import sqlite3
import tempfile
import unittest
from pathlib import Path

from reel_memory import (format_time, parse_manual_transcript, replace_cues,
                         search_reels, set_notes, setup_schema, timestamp_seconds,
                         validated_folder, reel_detail)


class ReelMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'db.sqlite3'
        with sqlite3.connect(self.db) as con:
            con.executescript('''
              CREATE TABLE batches(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL);
              CREATE TABLE reels(id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL,
                reel_url TEXT NOT NULL,status TEXT NOT NULL,folder TEXT,error TEXT,
                created_at TEXT NOT NULL);
              INSERT INTO batches VALUES(1,'2026-11-09');
            ''')
            for i in range(1, 4):
                con.execute('INSERT INTO reels VALUES (?,?,?,?,?,?,?)',
                    (i, 1, f'https://www.instagram.com/reel/Synthetic{i}/',
                     'ready', 'unused', None, '2026-11-09'))
        setup_schema(self.db)

    def test_timestamps_and_manual_parsing(self):
        self.assertEqual(timestamp_seconds('01:02'), 62.0)
        self.assertEqual(timestamp_seconds('00:59:03.125'), 3543.125)
        self.assertEqual(format_time(62), '01:02')
        self.assertEqual(parse_manual_transcript('00:12 Korean universities\n00:25 Scholarship interviews'),
                         [(12.0, None, 'Korean universities'), (25.0, None, 'Scholarship interviews')])
        self.assertEqual(parse_manual_transcript('Just a transcript'), [(0.0, None, 'Just a transcript')])
        for text in ['00:12 hello\nuntimed line', '00:20 later\n00:10 earlier', '00:61 invalid']:
            with self.assertRaises(ValueError):
                parse_manual_transcript(text)

    def test_three_reel_search_and_timestamp(self):
        set_notes(self.db, 1, 'Scholarships', 'Korea GKS university guide')
        set_notes(self.db, 2, 'Cooking', 'Pasta dinner')
        set_notes(self.db, 3, 'Language', 'Learning words')
        replace_cues(self.db, 1, 'manual', parse_manual_transcript('00:12 Korean universities\n00:25 Interview tips'))
        replace_cues(self.db, 2, 'manual', parse_manual_transcript('00:08 Cook pasta'))
        replace_cues(self.db, 3, 'manual', parse_manual_transcript('00:10 Korean grammar'))
        hits = search_reels(self.db, 'Korean universities')
        self.assertEqual([h['id'] for h in hits], [1])
        self.assertEqual(hits[0]['hit_seconds'], 12.0)
        self.assertEqual(search_reels(self.db, 'pasta')[0]['id'], 2)
        self.assertEqual(len(search_reels(self.db)), 3)

    def test_asr_and_manual_sources_do_not_overwrite_each_other(self):
        replace_cues(self.db, 1, 'manual', [(10, None, 'Manual correction')])
        replace_cues(self.db, 1, 'asr', [(11, 13, 'Automatic caption')])
        replace_cues(self.db, 1, 'asr', [(12, 14, 'New caption')])
        _, _, cues = reel_detail(self.db, 1)
        self.assertEqual([(c['source'], c['text']) for c in cues],
                         [('manual', 'Manual correction'), ('asr', 'New caption')])

    def test_rejects_invalid_and_unsafe_inputs(self):
        with self.assertRaises(ValueError):
            replace_cues(self.db, 1, 'asr', [(float('nan'), None, 'bad')])
        with self.assertRaises(ValueError):
            set_notes(self.db, 1, 'x' * 181, '')
        with self.assertRaises(ValueError):
            search_reels(self.db, 'x' * 161)
        with self.assertRaises(ValueError):
            set_notes(self.db, 99, 'Absent', '')
        root = self.root / 'batches'
        (root / 'Reel_001').mkdir(parents=True)
        self.assertEqual(validated_folder(root / 'Reel_001', root), (root / 'Reel_001').resolve())
        with self.assertRaises(ValueError):
            validated_folder(self.root, root)


if __name__ == '__main__':
    unittest.main()