"""Turns a photographed/screenshotted resume (JPG/PNG) into plain text, using
the vision-capable chat model instead of an OCR dependency like tesseract --
qwen3.5:9b already supports it (confirmed live via Ollama's /api/show:
`capabilities: [..., "vision", ...]`).

Deliberately separate from app/resume/parser.py: that module's whole point is
pure, LLM-free parsing (pdfplumber/python-docx), and its own tests lean on
that being true. This one calls the chat model, so it stays its own file.

The output of transcribe_resume_image() is stored in the same
Resume.extracted_text column a PDF/DOCX upload populates, so every downstream
consumer (resume_score.py's rubric grading and keyword-alignment embedding,
gap_engine.py's text-evidence matching) needs no changes at all -- they
already just read that column as a plain string.
"""

import base64
import io
from pathlib import Path

from PIL import Image

from app.llm.chat import chat

SUPPORTED_IMAGE_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

# Phone-camera photos routinely come in at 3000-4000px on the long edge --
# downscale before base64-encoding so the request stays a reasonable size and
# the model isn't spending its context budget on pixels beyond what a page of
# text actually needs to be legible.
MAX_IMAGE_DIMENSION = 2000

TRANSCRIPTION_SYSTEM_PROMPT = """\
You transcribe the text visible in a photographed or screenshotted resume \
image into plain text. Transcribe EXACTLY what is visible -- every word, \
line, and section, in the order they appear on the page. Do not summarize, \
paraphrase, reformat into different wording, or add any text that is not \
actually visible in the image. If part of the image is blurry, cut off, or \
otherwise illegible, write [illegible] for that part instead of guessing what \
it might say. If the image is not a resume at all, still transcribe whatever \
text is visible in it -- do not refuse, and do not comment on what the \
document is. Output only the transcribed text, nothing else -- no preamble, \
no explanation, no markdown formatting."""


def is_image_resume_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_IMAGE_MIME_TYPES


def _resize_if_needed(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data))
    if max(image.size) <= MAX_IMAGE_DIMENSION:
        return data

    image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def transcribe_resume_image(data: bytes, filename: str) -> str:
    """Returns the transcribed plain text. Raises ChatServiceUnavailable
    (propagated from app.llm.chat.chat) if the model can't be reached --
    there is no partial result to fall back to when there's no text at all
    yet, so the caller should surface this as a real failure, not degrade
    gracefully the way scoring/narrative steps do."""
    suffix = Path(filename).suffix.lower()
    mime_type = SUPPORTED_IMAGE_MIME_TYPES[suffix]

    resized = _resize_if_needed(data)
    # _resize_if_needed re-encodes as JPEG when it actually resizes; an
    # untouched image keeps its original format/mime type.
    if resized is not data:
        mime_type = "image/jpeg"

    b64_data = base64.b64encode(resized).decode("ascii")

    messages = [
        {"role": "system", "content": TRANSCRIPTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Transcribe this resume image:"},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}},
            ],
        },
    ]
    raw = await chat(messages)
    return raw.strip()
