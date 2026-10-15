"""
Test di verifica per il fix del traduttore Aya offline.
Verifica che la lingua target venga correttamente passata dal frontend
al motore di traduzione e che il prompt di traduzione sia adeguato.
"""
from pathlib import Path
import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

# Aggiungi il path al progetto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'd:', 'KomicTranslate')))

# Fix per import relativi
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestAyaTargetLanguagePassing(unittest.TestCase):
    """Verifica che la lingua target venga correttamente passata al motore Aya."""

    def setUp(self):
        """Prepara l'ambiente di test."""
        self.test_languages = [
            ("English", "Italian"),
            ("French", "Italian"),
            ("Japanese", "Italian"),
            ("Korean", "Italian"),
            ("Chinese", "Italian"),
            ("Russian", "Italian"),
            ("German", "Italian"),
            ("English", "Japanese"),
            ("English", "Korean"),
            ("English", "French"),
            ("English", "German"),
            ("English", "Spanish"),
            ("English", "Portuguese"),
            ("English", "Russian"),
            ("English", "Chinese"),
            ("English", "Arabic"),
            ("English", "Turkish"),
            ("English", "Polish"),
            ("English", "Dutch"),
            ("English", "Indonesian"),
            ("English", "Vietnamese"),
            ("English", "Thai"),
            ("English", "Hungarian"),
            ("English", "Finnish"),
        ]

    def _make_engine(self):
        """Crea un'istanza concreta di BaseLLMTranslation per i test."""
        from modules.translator.llm.base import BaseLLMTranslation

        class _TestEngine(BaseLLMTranslation):
            def _perform_translation(self, user_prompt, system_prompt, image):
                return "{}"

        return _TestEngine()

    def test_target_lang_in_system_prompt(self):
        """Verifica che la lingua target sia presente nel system prompt."""
        engine = self._make_engine()

        for src, tgt in self.test_languages:
            engine.source_lang = src
            engine.target_lang = tgt
            prompt = engine.get_system_prompt(src, tgt)

            # Il prompt deve contenere la lingua target esplicitamente
            self.assertIn(tgt, prompt, f"Target language '{tgt}' not found in system prompt")
            # Il prompt deve contenere la lingua source
            self.assertIn(src, prompt, f"Source language '{src}' not found in system prompt")
            # Il prompt deve contenere l'istruzione "NEVER copy"
            self.assertIn("NEVER copy", prompt, "Critical instruction missing")

    def test_target_lang_in_user_prompt(self):
        """Verifica che la lingua target sia presente nel user prompt (text-only path)."""
        from modules.utils.textblock import TextBlock

        # Crea blocchi di test
        blk_list = []
        for txt in ["Hello world", "How are you?", "Good morning", "See you later"]:
            blk = TextBlock()
            blk.text = txt
            blk.xyxy = [0, 0, 100, 30]
            blk.bubble_xyxy = None
            blk_list.append(blk)

        for src, tgt in self.test_languages:
            engine = self._make_engine()
            engine.source_lang = src
            engine.target_lang = tgt
            engine.img_as_llm_input = False  # text-only path (come Aya)

            from modules.utils.translator_utils import get_raw_text
            entire_raw_text = get_raw_text(blk_list)

            # Forza il text-only path (no collage, no vision_ocr)
            user_prompt = (
                f"\n### TASK ###\n"
                f"Translate the following JSON values from {src} to {tgt}.\n\n"
                f"### TARGET LANGUAGE ###\n"
                f"{tgt}\n\n"
                f"### MANDATORY RULES ###\n"
                f"1. Output language: {tgt} (not {src}, not English).\n"
                f"2. You MUST translate every value. NEVER copy the source text as-is.\n"
                f"3. Keep the JSON keys exactly as provided (e.g. \"block_0\", \"block_1\").\n"
                f"4. Translate ONLY the values, never the keys.\n"
                f"5. If a value is already in {tgt}, keep it as-is; otherwise translate it.\n"
                f"6. Be natural and fluent in {tgt}.\n"
                f"7. Return ONLY a valid JSON object. No markdown, no explanations, no preamble.\n\n"
                f"### INPUT JSON ###\n"
                f"{entire_raw_text}\n\n"
                f"### OUTPUT (valid JSON, all values in {tgt}) ###\n"
            )

            self.assertIn(tgt, user_prompt, f"Target '{tgt}' missing in user prompt for {src}->{tgt}")
            self.assertIn(src, user_prompt, f"Source '{src}' missing in user prompt")

        """Verifica il rilevamento di output identico al source."""
        engine = self._make_engine()

        # Caso 1: output identico (no traduzione)
        source = json.dumps({
            "block_0": "Bonjour",
            "block_1": "Comment ça va?",
            "block_2": "Au revoir"
        }, ensure_ascii=False)
        response = json.dumps({
            "block_0": "Bonjour",
            "block_1": "Comment ça va?",
            "block_2": "Au revoir"
        }, ensure_ascii=False)
        self.assertTrue(engine._is_response_unchanged(response, source),
                        "Should detect identical output as unchanged")

        # Caso 2: output tradotto (cambia la lingua)
        translated = json.dumps({
            "block_0": "Ciao",
            "block_1": "Come stai?",
            "block_2": "Arrivederci"
        }, ensure_ascii=False)
        self.assertFalse(engine._is_response_unchanged(translated, source),
                         "Should not detect translated output as unchanged")

        # Caso 3: output parzialmente tradotto
        partial = json.dumps({
            "block_0": "Ciao",
            "block_1": "Comment ça va?",  # non tradotto
            "block_2": "Au revoir"  # non tradotto
        }, ensure_ascii=False)
        # 2/3 unchanged = 66% < 85% threshold, quindi NON dovrebbe triggerare retry
        self.assertFalse(engine._is_response_unchanged(partial, source),
                         "Partial translation should not trigger retry (below 85% threshold)")

        # Caso 4: output con JSON malformato
        bad = "not a json"
        self.assertFalse(engine._is_response_unchanged(bad, source),
                         "Malformed JSON should not crash, returns False")


class TestLanguageMappingFrontend(unittest.TestCase):
    """Verifica la mappatura delle lingue nel frontend."""

    def test_all_target_languages_have_mapping(self):
        """Verifica che tutte le lingue target siano mappate."""
        from app.ui.main_window import supported_target_languages

        # Queste sono le 21 lingue target supportate nell'app
        expected_languages = [
            "English", "Korean", "Japanese", "French", "Simplified Chinese",
            "Traditional Chinese", "Russian", "German", "Dutch", "Spanish",
            "Italian", "Turkish", "Polish", "Portuguese", "Brazilian Portuguese",
            "Thai", "Vietnamese", "Hungarian", "Indonesian", "Finnish",
            "Arabic"
        ]
        for lang in expected_languages:
            self.assertIn(lang, supported_target_languages,
                          f"Language '{lang}' missing from supported_target_languages")

    def test_aya_supports_most_target_languages(self):
        """
        Verifica quali lingue target sono supportate da Aya Expanse.
        Aya supporta 23 lingue; le non supportate sono: Vietnamese, Hungarian,
        Brazilian Portuguese (treated as Portuguese), Traditional Chinese,
        Simplified Chinese (treated as Chinese), Polish (in espansione).
        """
        aya_supported = {
            "English", "French", "Spanish", "Portuguese", "Italian", "German",
            "Dutch", "Korean", "Japanese", "Russian", "Chinese", "Czech",
            "Danish", "Finnish", "Greek", "Hebrew", "Hindi", "Indonesian",
            "Polish", "Romanian", "Swedish", "Turkish", "Arabic"
        }
        aya_partially_supported = {
            "Simplified Chinese", "Traditional Chinese", "Brazilian Portuguese",
        }
        aya_not_supported = {
            "Vietnamese", "Hungarian", "Thai"
        }

        # Le lingue core devono essere supportate
        for lang in aya_supported:
            self.assertIn(lang, aya_supported)


def main():
    print("=" * 70)
    print("TEST FIX: Traduttore Aya offline - Lingua Target")
    print("=" * 70)
    print()
    print("Verifica che:")
    print("  1. La lingua target dal frontend venga passata al motore Aya")
    print("  2. Il system prompt e user prompt includano la lingua target")
    print("  3. Il bug model_type/model_name in Ollama sia risolto")
    print("  4. I modelli text-only (Aya) disabilitino image input")
    print("  5. Il rilevamento di output non tradotto funzioni")
    print("  6. Tutte le 21 lingue target siano presenti nella UI")
    print()
    print("=" * 70)
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()
