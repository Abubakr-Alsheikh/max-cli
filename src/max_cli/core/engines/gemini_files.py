"""Gemini's own REST API for audio and video: upload a file, ask about it, delete it.

The chat goes through Gemini's OpenAI-compatible endpoint (`ai_providers`),
which takes media only inline, up to 20 MB a request. Long recordings go
through the Files API instead: a resumable upload, a wait until Google has
processed the file, one `generateContent` call that points at it, then a
delete (Google would drop it after 48 hours anyway).
https://ai.google.dev/gemini-api/docs/files
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.common.exceptions import AIError, ConfigurationError, NetworkError

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com"
UPLOAD_URL = f"{API_ROOT}/upload/v1beta/files"
API_URL = f"{API_ROOT}/v1beta"
KEY_HEADER = "x-goog-api-key"
UPLOAD_URL_HEADER = "x-goog-upload-url"
CONNECT_TIMEOUT_SECONDS = 30
UPLOAD_TIMEOUT_SECONDS = 600
# A long recording can take Gemini several minutes to transcribe.
ANSWER_TIMEOUT_SECONDS = 900
PROCESSING_WAIT_SECONDS = 300
POLL_SECONDS = 2.0
ACTIVE = "ACTIVE"
FAILED = "FAILED"
# finishReason when the answer hit the model's output limit.
CUT_OFF_REASON = "MAX_TOKENS"


@dataclass(frozen=True)
class UploadedFile:
    name: str  # "files/abc123", for get and delete
    uri: str  # what a prompt points at
    mime_type: str
    state: str


@dataclass(frozen=True)
class Answer:
    text: str
    cut_off: bool  # the model stopped at its output limit


def _error_text(response: Any) -> str:
    """Google's own message for a failed request, else the status line."""
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return f"HTTP {response.status_code} {response.reason}"


def _file(data: dict[str, Any]) -> UploadedFile:
    info = data.get("file", data)
    return UploadedFile(
        name=str(info.get("name", "")),
        uri=str(info.get("uri", "")),
        mime_type=str(info.get("mimeType", "")),
        state=str(info.get("state", "")),
    )


class GeminiFiles:
    """One API key's calls to the Files API and `generateContent`."""

    def __init__(self, api_key: Optional[str]) -> None:
        if not api_key:
            raise ConfigurationError(
                "Transcripts use Google Gemini, which needs GEMINI_API_KEY. Get a "
                "key at https://aistudio.google.com/apikey, then add it on the "
                "dashboard's Settings page or run: max config setup"
            )
        self._headers = {KEY_HEADER: api_key}

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        import requests

        try:
            response = requests.request(
                method,
                url,
                headers={**self._headers, **kwargs.pop("headers", {})},
                **kwargs,
            )
        except requests.RequestException as exc:
            raise NetworkError(f"Couldn't reach Google Gemini: {exc}") from exc
        if not response.ok:
            raise AIError(f"Google Gemini refused the request: {_error_text(response)}")
        return response

    def upload(self, path: Path, mime_type: str) -> UploadedFile:
        """Send `path` in Google's resumable protocol: a start request names
        the file and gets an upload URL, then one request sends the bytes."""
        size = path.stat().st_size
        start = self._request(
            "POST",
            UPLOAD_URL,
            headers={
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(size),
                "X-Goog-Upload-Header-Content-Type": mime_type,
            },
            json={"file": {"display_name": path.name}},
            timeout=(CONNECT_TIMEOUT_SECONDS, CONNECT_TIMEOUT_SECONDS),
        )
        upload_url = start.headers.get(UPLOAD_URL_HEADER)
        if not upload_url:
            raise AIError("Google Gemini gave no upload address for the file.")
        with open(path, "rb") as audio:
            sent = self._request(
                "POST",
                upload_url,
                headers={
                    "Content-Length": str(size),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                data=audio,
                timeout=(CONNECT_TIMEOUT_SECONDS, UPLOAD_TIMEOUT_SECONDS),
            )
        return _file(sent.json())

    def wait_until_ready(
        self,
        uploaded: UploadedFile,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> UploadedFile:
        """Poll until Google has processed the file (audio is usually ready
        at once). Raises AIError when processing fails or takes too long."""
        deadline = clock() + PROCESSING_WAIT_SECONDS
        while uploaded.state != ACTIVE:
            if uploaded.state == FAILED:
                raise AIError("Google Gemini couldn't process the file.")
            if clock() > deadline:
                raise AIError("Google Gemini took too long to process the file.")
            sleep(POLL_SECONDS)
            uploaded = _file(
                self._request(
                    "GET",
                    f"{API_URL}/{uploaded.name}",
                    timeout=(CONNECT_TIMEOUT_SECONDS, CONNECT_TIMEOUT_SECONDS),
                ).json()
            )
        return uploaded

    def ask(
        self,
        model: str,
        prompt: str,
        uploaded: UploadedFile,
        schema: Optional[dict[str, Any]] = None,
    ) -> Answer:
        """One `generateContent` call with the prompt and the file. With a
        `schema`, Gemini answers JSON in that shape."""
        body: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "file_data": {
                                "mime_type": uploaded.mime_type,
                                "file_uri": uploaded.uri,
                            }
                        },
                    ]
                }
            ]
        }
        if schema:
            body["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            }
        data = self._request(
            "POST",
            f"{API_URL}/models/{model}:generateContent",
            json=body,
            timeout=(CONNECT_TIMEOUT_SECONDS, ANSWER_TIMEOUT_SECONDS),
        ).json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "")
            raise AIError(
                f"Google Gemini gave no answer{f' ({reason})' if reason else ''}."
            )
        first = candidates[0]
        parts = (first.get("content") or {}).get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise AIError("Google Gemini's answer was empty.")
        return Answer(text, first.get("finishReason") == CUT_OFF_REASON)

    def delete(self, uploaded: UploadedFile) -> None:
        """Remove the file from Google. A failure only logs: Google deletes
        uploads after 48 hours by itself."""
        try:
            self._request(
                "DELETE",
                f"{API_URL}/{uploaded.name}",
                timeout=(CONNECT_TIMEOUT_SECONDS, CONNECT_TIMEOUT_SECONDS),
            )
        except (AIError, NetworkError) as exc:
            logger.warning("Couldn't delete %s from Gemini: %s", uploaded.name, exc)
