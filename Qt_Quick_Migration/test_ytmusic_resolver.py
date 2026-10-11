from __future__ import annotations

import unittest
from unittest.mock import patch

import ytmusic_resolver


class YTMResolverTests(unittest.TestCase):
    @patch("ytmusic_resolver.YTMusic")
    def test_exact_contributing_artist_song_is_preferred_over_wrong_artist(self, ytmusic_cls):
        client = ytmusic_cls.return_value
        client.search.return_value = [
            {
                "videoId": "wrong",
                "title": "The Song",
                "artists": [{"name": "Another Artist"}],
                "album": {"name": "The Album"},
            },
            {
                "videoId": "right",
                "title": "The Song (Remastered)",
                "artists": [{"name": "Requested Artist"}],
                "album": {"name": "The Album"},
                "thumbnails": [{"url": "https://img.example/art=w544-h544-l90-rj", "width": 544, "height": 544}],
            },
        ]

        result = ytmusic_resolver.YTMResolver().search("Requested Artist", "The Song", "The Album")

        self.assertIsNotNone(result)
        self.assertEqual(result["video_id"], "right")
        self.assertEqual(result["artist"], "Requested Artist")
        self.assertEqual(result["source"], "YouTube Music Songs")
        client.search.assert_called_once_with("Requested Artist The Song", filter="songs", limit=15, ignore_spelling=False)

    @patch("ytmusic_resolver.YTMusic")
    def test_video_fallback_is_used_when_no_exact_artist_song_exists(self, ytmusic_cls):
        client = ytmusic_cls.return_value

        def fake_search(query, filter=None, **_kwargs):
            if filter == "songs":
                return [{
                    "videoId": "wrong-song",
                    "title": "Same Title",
                    "artists": [{"name": "Wrong Artist"}],
                }]
            if filter == "videos":
                return [
                    {
                        "videoId": "wrong-video",
                        "title": "Same Title",
                        "artists": [{"name": "Other Artist"}],
                    },
                    {
                        "videoId": "correct-video",
                        "title": "Same Title",
                        "artists": [{"name": "Requested Artist"}],
                    },
                ]
            return []

        client.search.side_effect = fake_search
        result = ytmusic_resolver.YTMResolver().search("Requested Artist", "Same Title")

        self.assertEqual(result["video_id"], "correct-video")
        self.assertEqual(result["source"], "YouTube Music Videos (Fallback)")
        self.assertTrue(result["is_fallback"])

    @patch("ytmusic_resolver.YTMusic")
    def test_video_fallback_uses_best_available_video_if_artist_is_unlisted(self, ytmusic_cls):
        client = ytmusic_cls.return_value

        def fake_search(query, filter=None, **_kwargs):
            if filter == "songs":
                return []
            if filter == "videos":
                return [
                    {"videoId": "weak", "title": "A Song", "artists": [{"name": "Unknown"}]},
                    {"videoId": "strong", "title": "Exact Song Title", "artists": [{"name": "Unknown"}]},
                ]
            return []

        client.search.side_effect = fake_search
        result = ytmusic_resolver.YTMResolver().search("Requested Artist", "Exact Song Title")

        self.assertEqual(result["video_id"], "strong")
        self.assertTrue(result["is_fallback"])

    def test_artist_match_is_based_on_contributing_artists(self):
        self.assertTrue(ytmusic_resolver.exact_artist_name_match(
            "Artist A & Artist B",
            ["Artist A", "Artist B"],
        ))
        self.assertFalse(ytmusic_resolver.exact_artist_name_match(
            "Artist A",
            ["Album Artist"],
        ))
        self.assertEqual(
            ytmusic_resolver.canonicalize_thumbnail_url("https://img.example/cover=w544-h544-l90-rj"),
            "https://img.example/cover=s0",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
