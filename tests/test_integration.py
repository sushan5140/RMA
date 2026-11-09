"""Three user-free synthetic recordings; no Instagram account or real reels required."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import flask  # noqa: F401
except ImportError:
    flask = None


@unittest.skipUnless(flask, "Flask is required for integration tests")
class FlaskIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ['RMA_DATA_DIR'] = str(Path(cls.temp.name) / 'private')
        import app as rma
        cls.rma = rma
        rma.setup()
        cls.client = rma.app.test_client()
        cls.videos = []
        for index in range(1, 4):
            video = Path(cls.temp.name) / f'synthetic_{index}.mp4'
            subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', f'color=c=blue:s=160x120:r=5:d=2',
                '-f', 'lavfi', '-i', f'sine=frequency={400+index*50}:duration=2',
                '-t', '2', '-c:v', 'mpeg4', '-c:a', 'aac', str(video)
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            cls.videos.append(video)
        response = cls.client.post('/batches', follow_redirects=False)
        assert response.status_code == 302
        for i, video in enumerate(cls.videos, 1):
            response = cls.client.post('/reels', data={
                'batch_id': '1',
                'reel_url': f'https://www.instagram.com/reel/Synthetic{i}/',
                'video': (io.BytesIO(video.read_bytes()), video.name),
            }, content_type='multipart/form-data')
            assert response.status_code == 302, response.get_data(as_text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        os.environ.pop('RMA_DATA_DIR', None)
        sys.modules.pop('app', None)

    def csrf(self):
        with self.client.session_transaction() as sess:
            return sess['_rma_csrf']

    def test_three_recording_search_flow(self):
        response = self.client.get('/library')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'3 matching imported reel', response.data)
        self.assertEqual(self.client.get('/library/1').status_code, 200)
        token = self.csrf()
        self.assertEqual(self.client.post('/library/1/notes', data={
            'title': 'Scholarship reel', 'notes': 'Korean GKS university information',
            'csrf': token
        }).status_code, 302)
        self.assertEqual(self.client.post('/library/1/transcript', data={
            'transcript': '00:01 Korean universities and scholarships',
            'csrf': token
        }).status_code, 302)
        result = self.client.get('/library?q=Korean+universities')
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'1 matching imported reel', result.data)
        self.assertIn(b'at 00:01', result.data)
        self.assertEqual(self.client.get('/library/1/audio').status_code, 200)
        self.assertEqual(self.client.get('/library/1/frame/00001.jpg').status_code, 200)
        self.assertEqual(self.client.get('/batches/1/download').status_code, 200)

    def test_csrf_and_media_path_protection(self):
        self.client.get('/library/2')
        response = self.client.post('/library/2/notes', data={
            'title': 'Attack', 'notes': 'Bad', 'csrf': 'wrong'
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/library/2/frame/../../.env').status_code, 404)
        self.assertEqual(self.client.get('/library/2/frame/sneaky.jpg').status_code, 404)
        with self.rma.connect() as con:
            con.execute('UPDATE reels SET folder=? WHERE id=3', (self.temp.name,))
        self.assertEqual(self.client.get('/library/3/audio').status_code, 404)

    def test_asr_requires_explicit_local_model(self):
        self.client.get('/library/1')
        old = os.environ.pop('RMA_WHISPER_MODEL_PATH', None)
        try:
            response = self.client.post('/library/1/transcribe', data={'csrf': self.csrf()})
            self.assertEqual(response.status_code, 400)
            self.assertIn(b'RMA_WHISPER_MODEL_PATH', response.data)
        finally:
            if old is not None:
                os.environ['RMA_WHISPER_MODEL_PATH'] = old


if __name__ == '__main__':
    unittest.main()