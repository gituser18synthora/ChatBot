"""Reply-language detection heuristics (app/utils/language_utils.py)."""
from app.utils import language_utils as lu


class TestDetectReplyLanguage:
    def test_english(self):
        assert lu.detect_reply_language("What is the premium amount for this policy?") == lu.ENGLISH

    def test_hindi_devanagari(self):
        assert lu.detect_reply_language("इस पॉलिसी का प्रीमियम कितना है?") == lu.HINDI

    def test_marathi_devanagari(self):
        assert lu.detect_reply_language("या पॉलिसीचा प्रीमियम किती आहे?") == lu.MARATHI

    def test_hinglish(self):
        assert lu.detect_reply_language("is policy ka premium kitna hai batao") == lu.HINGLISH

    def test_single_loanword_stays_english(self):
        # One ambiguous token must not flip English to Hinglish.
        assert lu.detect_reply_language("Send the acha report today") == lu.ENGLISH

    def test_explicit_request_wins_over_script(self):
        # Hindi-script query explicitly asking for English.
        assert lu.detect_reply_language("इसका उत्तर english में दो") == lu.ENGLISH
        assert lu.detect_reply_language("Explain the policy in hindi") == lu.HINDI
        assert lu.detect_reply_language("summary marathi me do") == lu.MARATHI

    def test_empty(self):
        assert lu.detect_reply_language("") == lu.ENGLISH
        assert lu.detect_reply_language(None) == lu.ENGLISH


class TestNeedsLanguageAlignment:
    HINDI_ANSWER = "इस पॉलिसी का प्रीमियम 5000 रुपये है और यह हर साल देय है।"
    MARATHI_ANSWER = "या पॉलिसीचा प्रीमियम 5000 रुपये आहे आणि तो दरवर्षी देय आहे."
    ENGLISH_ANSWER = "The premium for this policy is Rs. 5000, payable annually."
    HINGLISH_ANSWER = "Is policy ka premium 5000 rupaye hai aur ye har saal dena hota hai."

    def test_english_target(self):
        assert not lu.needs_language_alignment(self.ENGLISH_ANSWER, lu.ENGLISH)
        assert lu.needs_language_alignment(self.HINDI_ANSWER, lu.ENGLISH)

    def test_hindi_target(self):
        assert lu.needs_language_alignment(self.ENGLISH_ANSWER, lu.HINDI)
        assert not lu.needs_language_alignment(self.HINDI_ANSWER, lu.HINDI)

    def test_marathi_target(self):
        assert lu.needs_language_alignment(self.ENGLISH_ANSWER, lu.MARATHI)
        assert not lu.needs_language_alignment(self.MARATHI_ANSWER, lu.MARATHI)
        # Hindi answer for a Marathi user must be re-rendered.
        assert lu.needs_language_alignment(self.HINDI_ANSWER, lu.MARATHI)

    def test_hinglish_target(self):
        assert lu.needs_language_alignment(self.ENGLISH_ANSWER, lu.HINGLISH)
        assert lu.needs_language_alignment(self.HINDI_ANSWER, lu.HINGLISH)
        assert not lu.needs_language_alignment(self.HINGLISH_ANSWER, lu.HINGLISH)

    def test_empty_answer_never_aligned(self):
        assert not lu.needs_language_alignment("", lu.HINDI)
