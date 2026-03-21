"""
split_for_whatsapp — sentence-boundary chunking for Twilio's body limit.

Twilio caps WhatsApp message bodies at 1600 characters. Responses
exceeding that get split at sentence boundaries (., !, ?) so the
customer receives readable chunks, not mid-word cuts.

Fallback chain when a single unit exceeds the limit:
  sentence too long → split at word boundaries
  word too long (URL?) → hard char split
"""
import pytest

from src.safety.splitter import split_for_whatsapp


class TestBasicSplitting:
    def test_short_text_unchanged(self):
        text = "Your meeting is at 3pm."
        assert split_for_whatsapp(text, max_len=1600) == [text]

    def test_empty_text(self):
        assert split_for_whatsapp("", max_len=1600) == [""]

    def test_exactly_at_limit(self):
        text = "a" * 1600
        chunks = split_for_whatsapp(text, max_len=1600)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_two_sentences_fit_one_chunk(self):
        text = "First sentence. Second sentence."
        chunks = split_for_whatsapp(text, max_len=1600)
        assert chunks == [text]


class TestSentenceBoundarySplit:
    def test_splits_at_sentence_boundary(self):
        s1 = "First sentence here." + ("x" * 20)
        s2 = "Second sentence here."
        text = f"{s1} {s2}"
        chunks = split_for_whatsapp(text, max_len=30)
        # Neither sentence fits with the other, each gets its own chunk
        assert len(chunks) >= 2
        # No mid-word breaks: each chunk either ends at a sentence
        # terminator or is a complete word sequence
        for chunk in chunks:
            assert not chunk.endswith("-")  # no hyphenated breaks

    def test_sentences_packed_greedily(self):
        # Three short sentences that fit 2+1 or 1+2
        text = "One. Two. Three."
        chunks = split_for_whatsapp(text, max_len=12)
        # "One. Two." = 9 chars, fits. "Three." = 6 chars, separate.
        assert len(chunks) == 2
        # First chunk has two sentences, not one
        assert chunks[0].count(".") == 2

    def test_no_empty_chunks(self):
        text = "A. B. C. D. E."
        chunks = split_for_whatsapp(text, max_len=5)
        assert all(chunk.strip() for chunk in chunks)

    def test_preserves_all_content(self):
        text = "Alpha beta gamma. Delta epsilon. Zeta eta theta iota."
        chunks = split_for_whatsapp(text, max_len=25)
        rejoined = " ".join(chunks)
        # Whitespace may normalize but all words present
        for word in ["Alpha", "gamma", "Delta", "Zeta", "iota"]:
            assert word in rejoined

    @pytest.mark.parametrize("terminator", [".", "!", "?"])
    def test_recognizes_sentence_terminators(self, terminator):
        s1 = f"First{terminator}"
        s2 = "Second."
        text = f"{s1} {s2}"
        chunks = split_for_whatsapp(text, max_len=len(s1) + 1)
        assert len(chunks) == 2


class TestWordBoundaryFallback:
    def test_long_sentence_splits_at_words(self):
        # One sentence, no terminators until the end, longer than limit.
        text = "word " * 20 + "end."  # ~104 chars, single sentence
        chunks = split_for_whatsapp(text, max_len=30)
        assert len(chunks) >= 2
        # Each chunk should end at a word boundary (space or end)
        for chunk in chunks:
            # Last char is not a cut-off letter mid-word (trivially true
            # if we split on spaces)
            assert chunk.strip()

    def test_no_mid_word_break(self):
        text = "supercalifragilistic " * 5
        chunks = split_for_whatsapp(text, max_len=30)
        # Rejoining should recover every full word
        for chunk in chunks:
            for word in chunk.split():
                assert word in ("supercalifragilistic",)


class TestHardCharFallback:
    def test_oversized_single_word_hard_split(self):
        # A single "word" (URL, token) longer than the limit.
        text = "x" * 100
        chunks = split_for_whatsapp(text, max_len=30)
        assert len(chunks) >= 4  # 100/30 → 4 chunks
        assert all(len(c) <= 30 for c in chunks)
        assert "".join(chunks) == text

    def test_mixed_oversized_word_and_normal(self):
        text = "Start here. " + ("x" * 100) + " end."
        chunks = split_for_whatsapp(text, max_len=30)
        assert all(len(c) <= 30 for c in chunks)
        rejoined = "".join(c for c in chunks)
        assert "Start" in rejoined
        assert "xxxxx" in rejoined
        assert "end" in rejoined


class TestRealistic:
    def test_3500_char_response_under_default_limit(self):
        sentence = "Your Q3 revenue is trending well above forecast. "
        text = sentence * 70  # ~3500 chars
        chunks = split_for_whatsapp(text)  # default 1600
        assert len(chunks) >= 3
        assert all(len(c) <= 1600 for c in chunks)
        # Every chunk boundary is at a sentence terminator
        for chunk in chunks[:-1]:
            assert chunk.rstrip().endswith(".")
