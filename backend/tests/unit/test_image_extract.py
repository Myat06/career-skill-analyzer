"""Tests app/resume/image_extract.py: filename detection, the multimodal
message shape sent to the chat model, oversized-image downscaling, and
ChatServiceUnavailable propagation (there's no partial text to fall back to
when the transcription call itself fails)."""

import base64
import io

import pytest
from PIL import Image

import app.resume.image_extract as image_extract
from app.llm.chat import ChatServiceUnavailable
from app.resume.image_extract import (
    MAX_IMAGE_DIMENSION,
    is_image_resume_filename,
    transcribe_resume_image,
)


def _png_bytes(size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("resume.jpg", True),
        ("resume.JPEG", True),
        ("resume.png", True),
        ("resume.pdf", False),
        ("resume.docx", False),
        ("resume", False),
        ("resume.gif", False),
    ],
)
def test_is_image_resume_filename(filename, expected):
    assert is_image_resume_filename(filename) is expected


@pytest.mark.asyncio
async def test_transcribe_sends_multimodal_message_with_correct_mime_type(monkeypatch):
    seen_messages = None

    async def fake_chat(messages):
        nonlocal seen_messages
        seen_messages = messages
        return "Jane Doe\nSoftware Engineer"

    monkeypatch.setattr(image_extract, "chat", fake_chat)

    result = await transcribe_resume_image(_png_bytes((100, 100)), "resume.png")

    assert result == "Jane Doe\nSoftware Engineer"
    assert seen_messages[0]["role"] == "system"
    user_content = seen_messages[1]["content"]
    assert isinstance(user_content, list)
    text_blocks = [b for b in user_content if b["type"] == "text"]
    image_blocks = [b for b in user_content if b["type"] == "image_url"]
    assert len(text_blocks) == 1
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_transcribe_uses_jpeg_mime_type_for_jpg_input(monkeypatch):
    seen_messages = None

    async def fake_chat(messages):
        nonlocal seen_messages
        seen_messages = messages
        return "text"

    monkeypatch.setattr(image_extract, "chat", fake_chat)

    # A small image stays under MAX_IMAGE_DIMENSION, so it's sent as-is --
    # PIL PNG bytes given a .jpg filename still round-trip through Image.open
    # fine for this size assertion; the mime type comes from the extension.
    await transcribe_resume_image(_png_bytes((100, 100)), "photo.jpg")

    image_block = next(b for b in seen_messages[1]["content"] if b["type"] == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_oversized_image_is_downscaled_before_sending(monkeypatch):
    seen_messages = None

    async def fake_chat(messages):
        nonlocal seen_messages
        seen_messages = messages
        return "text"

    monkeypatch.setattr(image_extract, "chat", fake_chat)

    oversized = _png_bytes((MAX_IMAGE_DIMENSION + 1000, 500))
    await transcribe_resume_image(oversized, "resume.png")

    image_block = next(b for b in seen_messages[1]["content"] if b["type"] == "image_url")
    url = image_block["image_url"]["url"]
    # A resize re-encodes as JPEG regardless of the original extension.
    assert url.startswith("data:image/jpeg;base64,")
    b64_payload = url.split(",", 1)[1]
    decoded = Image.open(io.BytesIO(base64.b64decode(b64_payload)))
    assert max(decoded.size) <= MAX_IMAGE_DIMENSION


@pytest.mark.asyncio
async def test_image_within_limit_is_not_resized_or_reencoded(monkeypatch):
    seen_messages = None

    async def fake_chat(messages):
        nonlocal seen_messages
        seen_messages = messages
        return "text"

    monkeypatch.setattr(image_extract, "chat", fake_chat)

    original = _png_bytes((500, 500))
    await transcribe_resume_image(original, "resume.png")

    image_block = next(b for b in seen_messages[1]["content"] if b["type"] == "image_url")
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    b64_payload = url.split(",", 1)[1]
    assert base64.b64decode(b64_payload) == original


@pytest.mark.asyncio
async def test_chat_service_unavailable_propagates(monkeypatch):
    async def fake_chat(messages):
        raise ChatServiceUnavailable("down")

    monkeypatch.setattr(image_extract, "chat", fake_chat)

    with pytest.raises(ChatServiceUnavailable):
        await transcribe_resume_image(_png_bytes((100, 100)), "resume.png")
