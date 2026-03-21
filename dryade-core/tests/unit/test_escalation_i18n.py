"""
Tests for multilingual approval/rejection detection in escalation.py.

Covers French, Spanish, German, Italian, Portuguese confirmation words.
Bug: "oui" was treated as refinement (None) instead of approval (True).
"""

from core.orchestrator.escalation import is_approval_message

class TestFrenchApproval:
    """French approval words should return True."""

    def test_oui_is_approval(self):
        assert is_approval_message("oui") is True

    def test_ouais_is_approval(self):
        assert is_approval_message("ouais") is True

    def test_daccord_is_approval(self):
        assert is_approval_message("d'accord") is True

    def test_bien_sur_is_approval(self):
        assert is_approval_message("bien sûr") is True

    def test_evidemment_is_approval(self):
        assert is_approval_message("évidemment") is True

    def test_absolument_is_approval(self):
        assert is_approval_message("absolument") is True

    def test_parfait_is_approval(self):
        assert is_approval_message("parfait") is True

    def test_cest_bon_is_approval(self):
        assert is_approval_message("c'est bon") is True

    def test_vas_y_is_approval(self):
        assert is_approval_message("vas-y") is True

    def test_fais_le_is_approval(self):
        assert is_approval_message("fais-le") is True

    def test_oui_case_insensitive(self):
        assert is_approval_message("OUI") is True

    def test_oui_with_punctuation(self):
        # Leading/trailing punctuation — after strip it still starts with oui
        assert is_approval_message("  oui  ") is True

class TestFrenchRejection:
    """French rejection words should return False."""

    def test_non_is_rejection(self):
        assert is_approval_message("non") is False

    def test_pas_du_tout_is_rejection(self):
        assert is_approval_message("pas du tout") is False

    def test_annuler_is_rejection(self):
        assert is_approval_message("annuler") is False

    def test_arrete_is_rejection(self):
        assert is_approval_message("arrête") is False

    def test_stop_french_is_rejection(self):
        # "stop" is already in English list, but verify it still works
        assert is_approval_message("stop") is False

    def test_non_case_insensitive(self):
        assert is_approval_message("NON") is False

class TestSpanishApproval:
    """Spanish approval words should return True."""

    def test_si_with_accent_is_approval(self):
        assert is_approval_message("sí") is True

    def test_si_without_accent_is_approval(self):
        assert is_approval_message("si") is True

    def test_claro_is_approval(self):
        assert is_approval_message("claro") is True

    def test_por_supuesto_is_approval(self):
        assert is_approval_message("por supuesto") is True

    def test_adelante_is_approval(self):
        assert is_approval_message("adelante") is True

    def test_hazlo_is_approval(self):
        assert is_approval_message("hazlo") is True

    def test_perfecto_is_approval(self):
        assert is_approval_message("perfecto") is True

    def test_de_acuerdo_is_approval(self):
        assert is_approval_message("de acuerdo") is True

    def test_si_case_insensitive(self):
        assert is_approval_message("SÍ") is True

class TestSpanishRejection:
    """Spanish rejection words should return False."""

    def test_no_spanish_is_rejection(self):
        # "no" is already in English rejection, but verify coverage
        assert is_approval_message("no") is False

    def test_para_is_rejection(self):
        assert is_approval_message("para") is False

    def test_cancelar_is_rejection(self):
        assert is_approval_message("cancelar") is False

    def test_detente_is_rejection(self):
        assert is_approval_message("detente") is False

class TestGermanApproval:
    """German approval words should return True."""

    def test_ja_is_approval(self):
        assert is_approval_message("ja") is True

    def test_jawohl_is_approval(self):
        assert is_approval_message("jawohl") is True

    def test_naturlich_is_approval(self):
        assert is_approval_message("natürlich") is True

    def test_klar_is_approval(self):
        assert is_approval_message("klar") is True

    def test_selbstverstandlich_is_approval(self):
        assert is_approval_message("selbstverständlich") is True

    def test_mach_es_is_approval(self):
        assert is_approval_message("mach es") is True

    def test_genau_is_approval(self):
        assert is_approval_message("genau") is True

    def test_richtig_is_approval(self):
        assert is_approval_message("richtig") is True

    def test_ja_case_insensitive(self):
        assert is_approval_message("JA") is True

class TestGermanRejection:
    """German rejection words should return False."""

    def test_nein_is_rejection(self):
        assert is_approval_message("nein") is False

    def test_stopp_is_rejection(self):
        assert is_approval_message("stopp") is False

    def test_abbrechen_is_rejection(self):
        assert is_approval_message("abbrechen") is False

    def test_halt_is_rejection(self):
        assert is_approval_message("halt") is False

class TestItalianApproval:
    """Italian approval words should return True."""

    def test_si_italian_is_approval(self):
        # "sì" (with grave accent) — Italian "yes"
        assert is_approval_message("sì") is True

    def test_certo_is_approval(self):
        assert is_approval_message("certo") is True

    def test_certamente_is_approval(self):
        assert is_approval_message("certamente") is True

    def test_ovviamente_is_approval(self):
        assert is_approval_message("ovviamente") is True

    def test_perfetto_is_approval(self):
        assert is_approval_message("perfetto") is True

    def test_vai_is_approval(self):
        assert is_approval_message("vai") is True

    def test_fallo_is_approval(self):
        assert is_approval_message("fallo") is True

class TestItalianRejection:
    """Italian rejection words should return False."""

    def test_no_italian_is_rejection(self):
        assert is_approval_message("no") is False

    def test_ferma_is_rejection(self):
        assert is_approval_message("ferma") is False

    def test_annulla_is_rejection(self):
        assert is_approval_message("annulla") is False

    def test_basta_is_rejection(self):
        assert is_approval_message("basta") is False

class TestPortugueseApproval:
    """Portuguese approval words should return True."""

    def test_sim_is_approval(self):
        assert is_approval_message("sim") is True

    def test_claro_pt_is_approval(self):
        assert is_approval_message("claro") is True

    def test_com_certeza_is_approval(self):
        assert is_approval_message("com certeza") is True

    def test_pode_fazer_is_approval(self):
        assert is_approval_message("pode fazer") is True

    def test_perfeito_is_approval(self):
        assert is_approval_message("perfeito") is True

class TestPortugueseRejection:
    """Portuguese rejection words should return False."""

    def test_nao_is_rejection(self):
        assert is_approval_message("não") is False

    def test_parar_is_rejection(self):
        assert is_approval_message("parar") is False

    def test_cancelar_pt_is_rejection(self):
        assert is_approval_message("cancelar") is False

class TestNeutralMessages:
    """Non-approval/rejection messages should return None."""

    def test_random_text_is_none(self):
        assert is_approval_message("how are you") is None

    def test_question_is_none(self):
        assert is_approval_message("what should I do?") is None

    def test_empty_string_is_none(self):
        assert is_approval_message("") is None

    def test_partial_word_is_none(self):
        # "siren" starts with "si" but should not match Spanish "si" as standalone word
        # "si" pattern uses word boundary, "siren" should be None
        assert is_approval_message("siren") is None

    def test_ja_in_word_is_none(self):
        # "january" starts with "ja" but "ja" pattern needs word boundary
        # Note: ^ja\b matches "ja" at start with word boundary after it
        # "january" -> "jan..." so "ja" is followed by "n" which is a word char -> no match
        assert is_approval_message("january") is None

    def test_partial_non_is_none(self):
        # "notion" starts with "no" but should not match "no" rejection
        # "no" pattern ^no\b -> "notion" has no word boundary after "no" (followed by "t") -> no match
        assert is_approval_message("notion") is None

class TestExistingEnglishStillWork:
    """Regression tests: existing English patterns still return correct results."""

    def test_yes_is_approval(self):
        assert is_approval_message("yes") is True

    def test_ok_is_approval(self):
        assert is_approval_message("ok") is True

    def test_sure_is_approval(self):
        assert is_approval_message("sure") is True

    def test_no_is_rejection(self):
        assert is_approval_message("no") is False

    def test_cancel_is_rejection(self):
        assert is_approval_message("cancel") is False

    def test_stop_is_rejection(self):
        assert is_approval_message("stop") is False
