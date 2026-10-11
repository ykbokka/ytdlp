from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend


class FakeDownloadProcess:
    def __init__(self, command, **_kwargs):
        self.command = list(command)
        self.stdout = io.StringIO(
            "__YT_PROGRESS__100%|1.0MiB/s|00:00\n"
        )
        self.pid = 999999
        self._returncode = 0

        output_template = self.command[self.command.index("--output") + 1]
        staging_dir = Path(output_template).parent
        video_id = "vid123"
        title = "Raw title"
        if "--merge-output-format" in self.command:
            extension = "." + self.command[self.command.index("--merge-output-format") + 1]
        elif "--audio-format" in self.command:
            audio_format = self.command[self.command.index("--audio-format") + 1]
            extension = {"flac": ".flac", "mp3": ".mp3", "m4a": ".m4a", "opus": ".opus"}.get(audio_format, ".flac")
        else:
            extension = ".mp4"
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / f"{title} [{video_id}]{extension}").write_bytes(b"mock-media")

    def poll(self):
        return self._returncode

    def wait(self, timeout=None):
        return self._returncode

    def kill(self):
        self._returncode = -9

    def terminate(self):
        self._returncode = -15


class QtBackendCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_path = self.root / "toolkit.json"
        self.config_patch = patch.object(backend, "CONFIG_FILE", self.config_path)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def make_backend(self, config=None):
        self.config_path.write_text(json.dumps(config or {}), encoding="utf-8")
        return backend.ToolkitBackend()

    def test_legacy_paths_and_cookie_setting_are_loaded(self):
        download = self.root / "Downloads"
        metadata = self.root / "Metadata"
        covers = self.root / "Covers"
        crop = self.root / "Crop"
        pipeline = self.root / "Pipeline"
        cookie = self.root / "cookies.txt"
        cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        paths = {
            "downloader": str(download),
            "metadata": str(metadata),
            "cover": str(covers),
            "crop": str(crop),
            "pipeline": str(pipeline),
        }

        app = self.make_backend({
            "paths": paths,
            "cookie_file_path": str(cookie),
            "performance_mode": "balanced",
            "appearance_mode": "light",
            "conflict_mode": "skip",
            "file_type": "Video (MP4)",
            "quality": "720p",
        })

        settings = app.getSettings()
        self.assertEqual(settings["downloadDir"], str(download))
        self.assertEqual(settings["metadataDir"], str(metadata))
        self.assertEqual(settings["coverDir"], str(covers))
        self.assertEqual(settings["cropDir"], str(crop))
        self.assertEqual(settings["pipelineDir"], str(pipeline))
        self.assertEqual(settings["cookiePath"], str(cookie.resolve()))
        self.assertEqual(settings["performanceMode"], "balanced")
        self.assertEqual(settings["appearanceMode"], "light")
        self.assertEqual(settings["conflictMode"], "skip")
        self.assertEqual(settings["fileType"], "Video (MP4)")
        self.assertEqual(settings["quality"], "720p")

        app.setDownloadOptions("Audio only", "Best available", "FLAC", "Auto subtitles")
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["paths"], paths)
        self.assertEqual(saved["file_type"], "Audio only")
        self.assertEqual(saved["audio_format"], "FLAC")
        self.assertEqual(saved["subtitle_mode"], "Auto subtitles")

    def test_queue_item_captures_current_download_options(self):
        app = self.make_backend()
        tasks = {}
        def capture_worker(label, fn):
            tasks["work"] = fn
            return "test-queue-add"
        with patch.object(app, "_extract", return_value={
            "id": "vid123",
            "title": "Test song",
            "webpage_url": "https://www.youtube.com/watch?v=vid123",
            "formats": [],
        }), patch.object(app, "_run_async", side_effect=capture_worker):
            app.addQueueUrl(
                "https://www.youtube.com/watch?v=vid123",
                "Video (MP4)",
                "720p",
                "M4A",
                "Auto subtitles",
            )
        payload = tasks["work"]()
        item = payload["items"][-1]
        self.assertEqual(item["file_type"], "Video (MP4)")
        self.assertEqual(item["quality"], "720p")
        self.assertEqual(item["audio_format"], "M4A")
        self.assertEqual(item["subtitle_mode"], "Auto subtitles")

    def test_playlist_and_liked_music_url_detection(self):
        app = self.make_backend()
        self.assertTrue(app._is_playlist_url("https://www.youtube.com/playlist?list=PL123"))
        self.assertTrue(app._is_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123"))
        self.assertTrue(app._is_liked_music_url("https://music.youtube.com/playlist?list=LM"))
        self.assertFalse(app._is_liked_music_url("https://music.youtube.com/playlist?list=PL123"))

    def test_format_ceiling_and_audio_format_are_selected(self):
        app = self.make_backend()
        args = app._format_args("Video (MP4)", "1080p", "FLAC")
        self.assertIn("bestvideo[height<=1080][ext=mp4]", args[1])
        self.assertTrue(args[1].endswith("/best[height<=1080]"), "MP4 format fallback must not exceed the selected quality ceiling.")
        self.assertIn("--merge-output-format", args)
        audio = app._format_args("Audio only", "Best available", "FLAC")
        self.assertIn("--audio-format", audio)
        self.assertEqual(audio[audio.index("--audio-format") + 1], "flac")

    def test_native_fallback_removes_only_aria2_routing_arguments(self):
        command = [
            "yt-dlp", "--downloader", "aria2c",
            "--downloader", "dash,m3u8:native",
            "--downloader-args", "aria2c:-x 8 -s 8 -k 2M",
            "--format", "bestvideo+bestaudio", "https://example.invalid/video",
        ]
        fallback = backend.build_native_ytdlp_fallback_command(command)
        self.assertIsNotNone(fallback)
        self.assertNotIn("--downloader", fallback)
        self.assertNotIn("--downloader-args", fallback)
        self.assertIn("--format", fallback)
        self.assertEqual(fallback[-2:], ["bestvideo+bestaudio", "https://example.invalid/video"])
        self.assertIsNone(backend.build_native_ytdlp_fallback_command(["yt-dlp", "--format", "best"]))

    def test_stage_retries_aria2_failure_once_with_native_downloader(self):
        app = self.make_backend()
        commands = []

        class FakeStageProcess:
            def __init__(self, command, **_kwargs):
                self.command = list(command)
                commands.append(self.command)
                if len(commands) == 1:
                    self.stdout = io.StringIO("ERROR: aria2c download failed\\n")
                    self.code = 1
                else:
                    self.stdout = io.StringIO("__YT_PROGRESS__100%|3MiB/s|00:00\\n")
                    self.code = 0

            def poll(self):
                return self.code

            def wait(self, timeout=None):
                return self.code

            def kill(self):
                self.code = -9

            def terminate(self):
                self.code = -15

        command = [
            "yt-dlp", "--downloader", "aria2c",
            "--downloader", "dash,m3u8:native",
            "--downloader-args", "aria2c:-x 8 -s 8 -k 2M",
            "--progress-template", "download:__YT_PROGRESS__%(progress._percent_str)s",
        ]
        with patch("backend.subprocess.Popen", FakeStageProcess):
            result = app._run_stage(command, "Video")
        self.assertEqual(len(commands), 2)
        self.assertIn("--downloader", commands[0])
        self.assertNotIn("--downloader", commands[1])
        self.assertNotIn("--downloader-args", commands[1])
        self.assertTrue(any("__YT_PROGRESS__" in line for line in result))

    def test_audio_language_is_recovered_from_format_notes(self):
        app = self.make_backend()
        english = {"language": "und", "format_note": "English original (default), medium"}
        arabic = {"language": "", "format_note": "Arabic original (default), high"}
        self.assertEqual(app._audio_language_name(english), "English")
        self.assertEqual(app._audio_language_key(english), "en")
        self.assertEqual(app._audio_language_key(arabic), "ar")
        self.assertEqual(app._language_iso639("English"), "eng")
        self.assertEqual(app._language_iso639("Arabic"), "ara")

    def test_ytmusic_enrichment_rejects_different_video_ids(self):
        app = self.make_backend()
        info = {
            "id": "source123",
            "title": "Source title",
            "artist": "Source artist",
            "album": "Source album",
            "thumbnail": "https://image.example/source.jpg",
            "formats": [],
        }
        ytm_match = {
            "video_id": "different999",
            "title": "Unrelated search result",
            "artist": "Other artist",
            "album": "Other album",
            "year": "2022",
            "cover_url": "https://image.example/wrong.jpg",
            "thumbnail_candidates": ["https://image.example/wrong.jpg"],
            "source": "YouTube Music Songs",
        }
        with patch.object(backend, "YTMResolver") as resolver:
            resolver.return_value.search.return_value = ytm_match
            result = app._metadata_for_source(info, "https://music.youtube.com/watch?v=source123")
        self.assertEqual(result["video_id"], "source123")
        self.assertEqual(result["title"], "Source title")
        self.assertEqual(result["artist"], "Source artist")
        self.assertEqual(result["cover_url"], "https://image.example/source.jpg")

    def test_ytmusic_enrichment_is_used_for_the_same_video_id(self):
        app = self.make_backend()
        info = {"id": "source123", "title": "Source title", "artist": "Source artist", "thumbnail": ""}
        ytm_match = {
            "video_id": "source123",
            "title": "YT Music title",
            "artist": "YT Music artist",
            "album": "YT Music album",
            "year": "2021",
            "cover_url": "https://image.example/cover.jpg",
            "thumbnail_candidates": ["https://image.example/cover.jpg"],
            "source": "YouTube Music Songs",
        }
        with patch.object(backend, "YTMResolver") as resolver:
            resolver.return_value.search.return_value = ytm_match
            result = app._metadata_for_source(info, "https://music.youtube.com/watch?v=source123")
        self.assertEqual(result["video_id"], "source123")
        self.assertEqual(result["title"], "YT Music title")
        self.assertEqual(result["artist"], "YT Music artist")
        self.assertEqual(result["cover_url"], "https://image.example/cover.jpg")

    def test_single_video_download_exports_from_tempytm_and_cleans_it(self):
        output = self.root / "output"
        app = self.make_backend({"download_dir": str(output)})
        app.download_dir = str(output)
        source_info = {
            "id": "vid123",
            "title": "Raw title",
            "artist": "Raw artist",
            "thumbnail": "",
            "formats": [],
        }
        with patch.object(app, "_extract", return_value=source_info), \
             patch.object(app, "_base_command", return_value=["fake-yt-dlp"]), \
             patch.object(app, "_apply_download_metadata"), \
             patch("backend.subprocess.Popen", FakeDownloadProcess):
            app._download_one(
                "https://www.youtube.com/watch?v=vid123",
                "Video (MP4)",
                "720p",
                "FLAC",
                "No subtitles",
            )

        result = output / "Raw title.mp4"
        self.assertTrue(result.is_file(), "A completed media file should have been exported to the final folder.")
        self.assertEqual(result.read_bytes(), b"mock-media")
        self.assertFalse((output / "tempytm").exists(), "A single-download tempytm workspace should be removed.")

    def test_safe_filename_and_language_labels(self):
        self.assertEqual(backend.ToolkitBackend._safe_name('a<b>:"c'), "a_b_c")
        self.assertEqual(backend.ToolkitBackend._language_label("ar"), "Arabic")
        self.assertEqual(backend.ToolkitBackend._language_iso639("en-US"), "eng")

    def test_queue_progress_percent_is_playlist_wide(self):
        calculate = backend.ToolkitBackend._queue_progress_percent
        self.assertAlmostEqual(calculate(0, 4, 50), 12.5)
        self.assertAlmostEqual(calculate(1, 4, 0), 25.0)
        self.assertAlmostEqual(calculate(1, 4, 100), 50.0)
        self.assertAlmostEqual(calculate(3, 4, 50), 87.5)
        self.assertAlmostEqual(calculate(3, 4, 100), 100.0)
        self.assertAlmostEqual(calculate(1, 4, 150), 50.0)
        self.assertAlmostEqual(calculate(1, 4, -5), 25.0)

    def test_arabic_media_filename_isolated_without_reversing_title(self):
        title = "لا تصارخ ولا راح تموت🤫 _ Fears to Fathom #2"
        stem = backend.ToolkitBackend._media_stem(title)
        self.assertTrue(stem.startswith("\u2067"))
        self.assertTrue(stem.endswith("\u2069"))
        self.assertNotIn("5Bj2JKH1xEQ", stem)
        self.assertIn(title, stem)
        derived = backend.derive_title_from_filename(stem + ".mkv")
        self.assertNotIn("\u2067", derived)
        self.assertNotIn("\u2069", derived)
        self.assertEqual(
            derived,
            "لا تصارخ ولا راح تموت🤫 Fears to Fathom #2",
            "The final filename should contain the title only, without the opaque YouTube ID."
        )

    def test_english_media_filename_remains_clean(self):
        self.assertEqual(
            backend.ToolkitBackend._media_stem("Example Video"),
            "Example Video"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
