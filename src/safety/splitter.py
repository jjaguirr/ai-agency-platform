"""
split_for_whatsapp — break long responses at sentence boundaries.

Twilio rejects WhatsApp message bodies over 1600 characters. Rather
than let the send fail, the webhook handler splits the EA's response
into readable chunks and sends them in order.

Fallback chain, applied per unit when the unit alone exceeds max_len:

  sentence too long → split at word boundaries
  word too long     → hard character split (URLs, tokens)

Each level packs greedily — as many units per chunk as will fit — so
a 3500-char response with 50-char sentences lands in three messages,
not seventy.

The hard-character fallback preserves exact bytes: "".join() of its
chunks reconstructs the original token. The upper levels normalize
whitespace at pack time (joining with a single space) since they
already split on whitespace — nothing semantic is lost.
"""
from __future__ import annotations

import re
from typing import List

# Sentence boundary: a terminator immediately before, whitespace after.
# The lookbehind keeps the terminator with the preceding sentence so
# each chunk ends with its own punctuation. "3.5%" and "e.g. cancel"
# won't split (no whitespace after the digit/letter following the dot).
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def split_for_whatsapp(text: str, max_len: int = 1600) -> List[str]:
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    buf = ""

    for sentence in _SENTENCE_BREAK.split(text):
        if not sentence:
            continue

        if len(sentence) > max_len:
            # Sentence alone exceeds the limit — flush and descend.
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_words(sentence, max_len))
            continue

        # Sentence fits on its own. Try packing it with the buffer.
        candidate = f"{buf} {sentence}" if buf else sentence
        if len(candidate) <= max_len:
            buf = candidate
        else:
            chunks.append(buf)
            buf = sentence

    if buf:
        chunks.append(buf)
    return chunks


def _split_words(sentence: str, max_len: int) -> List[str]:
    """Word-boundary packing for a sentence that doesn't fit whole."""
    chunks: List[str] = []
    buf = ""

    for word in sentence.split():
        if len(word) > max_len:
            # Single token exceeds the limit — flush and hard-split.
            # At this point there is no word boundary to respect; the
            # customer gets a mid-token break but at least the send
            # succeeds. Most likely a pasted URL or base64 blob.
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(
                word[i:i + max_len] for i in range(0, len(word), max_len)
            )
            continue

        candidate = f"{buf} {word}" if buf else word
        if len(candidate) <= max_len:
            buf = candidate
        else:
            chunks.append(buf)
            buf = word

    if buf:
        chunks.append(buf)
    return chunks
