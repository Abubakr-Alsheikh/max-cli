"""`max audio transcribe`: Google Gemini's Files API, prompts, SRT building.

No network and no FFmpeg: `requests.request` is mocked for the client, and
the operation tests use a fake client and a fake engine.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import AIError, ConfigurationError, NetworkError
from max_cli.core.engines import gemini_files
from max_cli.core.engines.gemini_files import Answer, GeminiFiles, UploadedFile
from max_cli.core.operations import audio
from max_cli.interface.cli_audio import app as audio_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

KEY = "test-key"
UPLOAD_ADDRESS = "https://upload.example/session-1"
FILE_INFO = {
    "name": "files/abc",
    "uri": "https://generativelanguage.googleapis.com/v1beta/files/abc",
    "mimeType": "audio/mp3",
    "state": "ACTIVE",
}


def _response(status: int = 200, body=None, headers=None) -> SimpleNamespace:
    return SimpleNamespace(
        ok=status < 400,
        status_code=status,
        reason="Bad Request" if status >= 400 else "OK",
        headers=headers or {},
        json=lambda: body if body is not None else {},
    )


def _answer(text: str, finish: str = "STOP") -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]
    }


class TestGeminiFiles:
    def test_needs_a_key(self):
        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
            GeminiFiles(None)

    def test_upload_starts_a_session_then_sends_the_bytes(self, tmp_path):
        speech = tmp_path / "talk.mp3"
        speech.write_bytes(b"mp3-bytes")
        replies = [
            _response(headers={"x-goog-upload-url": UPLOAD_ADDRESS}),
            _response(body={"file": FILE_INFO}),
        ]

        with patch("requests.request", side_effect=replies) as request:
            uploaded = GeminiFiles(KEY).upload(speech, "audio/mp3")

        start, send = request.call_args_list
        assert start.args == ("POST", gemini_files.UPLOAD_URL)
        assert start.kwargs["headers"]["x-goog-api-key"] == KEY
        assert start.kwargs["headers"]["X-Goog-Upload-Command"] == "start"
        assert start.kwargs["headers"]["X-Goog-Upload-Header-Content-Length"] == "9"
        assert start.kwargs["json"] == {"file": {"display_name": "talk.mp3"}}
        assert send.args == ("POST", UPLOAD_ADDRESS)
        assert send.kwargs["headers"]["X-Goog-Upload-Command"] == "upload, finalize"
        assert uploaded == UploadedFile(
            "files/abc", FILE_INFO["uri"], "audio/mp3", "ACTIVE"
        )

    def test_upload_without_an_address_fails(self, tmp_path):
        speech = tmp_path / "talk.mp3"
        speech.write_bytes(b"x")

        with patch("requests.request", return_value=_response()):
            with pytest.raises(AIError, match="no upload address"):
                GeminiFiles(KEY).upload(speech, "audio/mp3")

    def test_googles_error_message_reaches_the_user(self):
        refusal = _response(400, {"error": {"message": "API key not valid."}})

        with patch("requests.request", return_value=refusal):
            with pytest.raises(AIError, match="API key not valid"):
                GeminiFiles(KEY).ask("m", "p", UploadedFile("files/a", "u", "t", ""))

    def test_offline_is_a_network_error(self):
        import requests

        with patch("requests.request", side_effect=requests.ConnectionError("down")):
            with pytest.raises(NetworkError, match="Couldn't reach"):
                GeminiFiles(KEY).ask("m", "p", UploadedFile("files/a", "u", "t", ""))

    def test_waits_until_the_file_is_active(self):
        processing = UploadedFile("files/abc", "u", "audio/mp3", "PROCESSING")
        sleeps: list[float] = []

        with patch("requests.request", return_value=_response(body=FILE_INFO)):
            ready = GeminiFiles(KEY).wait_until_ready(processing, sleep=sleeps.append)

        assert ready.state == "ACTIVE"
        assert sleeps == [gemini_files.POLL_SECONDS]

    def test_failed_processing_stops(self):
        failed = UploadedFile("files/abc", "u", "audio/mp3", "FAILED")

        with pytest.raises(AIError, match="couldn't process"):
            GeminiFiles(KEY).wait_until_ready(failed, sleep=lambda _: None)

    def test_slow_processing_gives_up(self):
        processing = UploadedFile("files/abc", "u", "audio/mp3", "PROCESSING")
        times = iter([0.0, gemini_files.PROCESSING_WAIT_SECONDS + 1])

        with pytest.raises(AIError, match="too long"):
            GeminiFiles(KEY).wait_until_ready(
                processing, sleep=lambda _: None, clock=lambda: next(times)
            )

    def test_ask_points_at_the_file_and_can_ask_for_json(self):
        uploaded = UploadedFile("files/abc", "https://f/abc", "audio/mp3", "ACTIVE")
        schema = {"type": "ARRAY"}

        with patch(
            "requests.request", return_value=_response(body=_answer("[]", "MAX_TOKENS"))
        ) as request:
            answer = GeminiFiles(KEY).ask("gemini-x", "Do it.", uploaded, schema)

        method, url = request.call_args.args
        assert url.endswith("/models/gemini-x:generateContent")
        body = request.call_args.kwargs["json"]
        text_part, file_part = body["contents"][0]["parts"]
        assert text_part == {"text": "Do it."}
        assert file_part == {
            "file_data": {"mime_type": "audio/mp3", "file_uri": "https://f/abc"}
        }
        assert body["generationConfig"]["responseSchema"] == schema
        assert answer == Answer("[]", cut_off=True)

    def test_a_blocked_answer_says_why(self):
        blocked = _response(body={"promptFeedback": {"blockReason": "SAFETY"}})

        with patch("requests.request", return_value=blocked):
            with pytest.raises(AIError, match="SAFETY"):
                GeminiFiles(KEY).ask("m", "p", UploadedFile("files/a", "u", "t", ""))

    def test_delete_failure_only_logs(self, caplog):
        with patch("requests.request", return_value=_response(500)):
            GeminiFiles(KEY).delete(UploadedFile("files/a", "u", "t", ""))

        assert "Couldn't delete files/a" in caplog.text


class TestPrompt:
    def test_user_instructions_follow_the_default(self):
        prompt = audio.transcript_prompt("txt", "  Translate to Arabic. ")

        assert prompt.startswith(audio.TRANSCRIPT_PROMPT)
        assert prompt.endswith("they win:\nTranslate to Arabic.")

    def test_subtitles_name_the_length(self):
        assert "12.5 seconds long" in audio.transcript_prompt("srt", None, 12.5)


class TestCuesToSrt:
    def test_writes_numbered_cues_in_time_order(self):
        srt = audio.cues_to_srt(
            [
                {"start": 3.5, "end": 5.0, "text": "Second."},
                {"start": 0.0, "end": 2.25, "text": "First."},
            ],
            10.0,
        )

        assert srt == (
            "1\n00:00:00,000 --> 00:00:02,250\nFirst.\n\n"
            "2\n00:00:03,500 --> 00:00:05,000\nSecond.\n"
        )

    def test_fixes_overlaps_short_cues_and_the_end(self):
        srt = audio.cues_to_srt(
            [
                {"start": 1.0, "end": 4.0, "text": "a"},
                {"start": 3.0, "end": 3.1, "text": "b"},
                {"start": 9.0, "end": 12.0, "text": "c"},
            ],
            10.0,
        )

        assert "00:00:01,000 --> 00:00:03,000\na" in srt  # ends where b starts
        assert "00:00:03,000 --> 00:00:03,500\nb" in srt  # at least half a second
        assert "00:00:09,000 --> 00:00:10,000\nc" in srt  # not past the end

    def test_long_text_becomes_two_lines(self):
        words = "We will discuss the budget and the new website today"

        srt = audio.cues_to_srt([{"start": 0, "end": 3, "text": words}], 5.0)

        assert "We will discuss the budget\nand the new website today" in srt

    def test_drops_cues_without_text_or_time(self):
        srt = audio.cues_to_srt(
            [
                {"start": "soon", "end": 1, "text": "x"},
                {"start": 0, "end": 1, "text": "  "},
                {"start": 20, "end": 21, "text": "after the end"},
                {"start": 1, "end": 2, "text": "kept"},
            ],
            10.0,
        )

        assert srt == "1\n00:00:01,000 --> 00:00:02,000\nkept\n"

    def test_nothing_usable_is_an_error(self):
        with pytest.raises(AIError, match="no usable cues"):
            audio.cues_to_srt([{"start": 0, "end": 1, "text": ""}], 5.0)


def _fake_engine(seconds: float = 9.3) -> MagicMock:
    engine = MagicMock()
    engine.speech_audio.side_effect = lambda source, speech: speech.write_bytes(b"m")
    engine.probe_media.return_value = {"format": {"duration": str(seconds)}}
    return engine


def _fake_client(text: str, cut_off: bool = False) -> MagicMock:
    client = MagicMock()
    uploaded = UploadedFile("files/abc", "u", "audio/mp3", "ACTIVE")
    client.upload.return_value = uploaded
    client.wait_until_ready.return_value = uploaded
    client.ask.return_value = Answer(text, cut_off)
    return client


class TestOperation:
    def test_transcript_sits_next_to_the_video(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")
        client = _fake_client("```text\nHello there.\n```")

        result = audio.transcribe(
            video, engine=_fake_engine(), client=client, model="gemini-test"
        )

        assert result.output_files == [tmp_path / "talk.txt"]
        assert (tmp_path / "talk.txt").read_text(encoding="utf-8") == "Hello there.\n"
        model, prompt, uploaded = client.ask.call_args.args
        assert model == "gemini-test"
        assert prompt == audio.TRANSCRIPT_PROMPT
        assert client.ask.call_args.kwargs == {"schema": None}
        assert client.upload.call_args.args[1] == "audio/mp3"
        client.delete.assert_called_once_with(uploaded)
        assert result.details["seconds"] == 9.3

    def test_subtitles_ask_for_cues_and_write_srt(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")
        cues = json.dumps([{"start": 0, "end": 2, "text": "Hi."}])
        client = _fake_client(cues)

        result = audio.transcribe(
            video, format="srt", engine=_fake_engine(), client=client
        )

        assert result.output_files == [tmp_path / "talk.srt"]
        assert (tmp_path / "talk.srt").read_text(encoding="utf-8") == (
            "1\n00:00:00,000 --> 00:00:02,000\nHi.\n"
        )
        assert client.ask.call_args.kwargs == {"schema": audio.CUES_SCHEMA}

    def test_the_upload_is_deleted_when_gemini_fails(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")
        client = _fake_client("")
        client.ask.side_effect = AIError("quota")

        with pytest.raises(AIError):
            audio.transcribe(video, engine=_fake_engine(), client=client)

        client.delete.assert_called_once()
        assert not (tmp_path / "talk.txt").exists()

    def test_a_cut_off_transcript_is_kept_with_a_note(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")

        result = audio.transcribe(
            video, engine=_fake_engine(), client=_fake_client("Part", cut_off=True)
        )

        assert "output limit" in result.message
        assert result.details["cut_off"] is True

    def test_cut_off_subtitles_save_nothing(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")

        with pytest.raises(AIError, match="output limit"):
            audio.transcribe(
                video,
                format="srt",
                engine=_fake_engine(),
                client=_fake_client('[{"start": 0', cut_off=True),
            )

    def test_subtitles_that_arent_json_save_nothing(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")

        with pytest.raises(AIError, match="expected shape"):
            audio.transcribe(
                video, format="srt", engine=_fake_engine(), client=_fake_client("Hi")
            )

    def test_model_falls_back_to_the_setting_then_the_default(self, monkeypatch):
        from max_cli.config import settings

        monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-mine")
        assert audio._transcribe_model(None) == "gemini-mine"
        monkeypatch.setattr(settings, "GEMINI_MODEL", "")
        assert audio._transcribe_model(None) == audio.DEFAULT_TRANSCRIBE_MODEL

    def test_unknown_format(self, tmp_path):
        video = tmp_path / "talk.mp4"
        video.write_bytes(b"v")

        with pytest.raises(audio.ValidationError, match="Unknown format"):
            audio.transcribe(video, format="docx", client=_fake_client(""))


def test_cli_sends_the_prompt(tmp_path, monkeypatch):
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"v")
    client = _fake_client("مرحبا")
    monkeypatch.setattr(audio, "_gemini_client", lambda: client)

    with patch(
        "max_cli.interface.cli_audio._get_media_engine", return_value=_fake_engine()
    ):
        result = runner.invoke(
            audio_app, ["transcribe", str(video), "-p", "Translate to Arabic."]
        )

    assert result.exit_code == 0, result.output
    assert client.ask.call_args.args[1].endswith("Translate to Arabic.")
    assert (tmp_path / "talk.txt").read_text(encoding="utf-8") == "مرحبا\n"


def test_cli_without_a_key_explains(tmp_path, monkeypatch):
    from max_cli.config import settings

    video = tmp_path / "talk.mp4"
    video.write_bytes(b"v")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)

    with patch(
        "max_cli.interface.cli_audio._get_media_engine", return_value=_fake_engine()
    ):
        result = runner.invoke(audio_app, ["transcribe", str(video)])

    assert "GEMINI_API_KEY" in result.output
    assert not (tmp_path / "talk.txt").exists()
