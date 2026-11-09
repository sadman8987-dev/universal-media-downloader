import unittest
from unittest.mock import patch

from smart_download_engine import select_engine, is_gallery_url, is_hls_url


class EngineSelectionTests(unittest.TestCase):
    def test_regular_video_uses_ytdlp(self):
        self.assertEqual(select_engine("https://youtu.be/example", environ={}), "yt-dlp")

    def test_gallery_url_uses_gallery_dl(self):
        self.assertEqual(select_engine("https://www.instagram.com/p/example/", environ={}), "gallery-dl")

    def test_explicit_gallery_kind_uses_gallery_dl(self):
        self.assertEqual(select_engine("https://example.com/post", kind="gallery", environ={}), "gallery-dl")

    def test_hls_uses_streamlink_when_available(self):
        with patch("smart_download_engine.shutil.which", side_effect=lambda name: "/usr/bin/streamlink" if name == "streamlink" else None):
            self.assertEqual(select_engine("https://cdn.example/live.m3u8", environ={}), "streamlink")

    def test_n_m3u8dl_preferred_when_available(self):
        with patch("smart_download_engine.shutil.which", return_value="/usr/bin/N_m3u8DL-RE"):
            self.assertEqual(select_engine("https://cdn.example/movie.mpd", environ={}), "N_m3u8DL-RE")

    def test_hls_detection(self):
        self.assertTrue(is_hls_url("https://cdn.example/live.m3u8?token=x"))
        self.assertTrue(is_gallery_url("https://i.imgur.com/example"))


if __name__ == "__main__":
    unittest.main()
