"""
Simple internationalization (i18n) helper module.

This module provides a minimal `I18nManager` class responsible for loading
translations from JSON files and returning translated strings. Translation
files are expected to live in a configurable directory (by default
`locales`) and be named with their language code (e.g. `zh_TW.json`,
`en_US.json`). Each JSON file should map translation keys to the user-facing
strings for that language.

Example usage::

    from i18n_helper import I18nManager
    i18n = I18nManager(locales_dir='locales', default_lang='zh_TW')
    i18n.set_language('en_US')
    print(i18n.t('file_explorer_title'))

If a key is missing from the loaded language file it will fall back to
returning the key itself. This makes it easy to identify untranslated
strings during development.

The helper stores the currently loaded translations in memory so that
subsequent lookups are fast. Changing the language simply reloads the
appropriate JSON file.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional


class I18nManager:
    """Manages translations loaded from JSON files."""

    def __init__(self, locales_dir: str = 'locales', default_lang: str = 'zh_TW') -> None:
        """
        Create a new I18nManager.

        :param locales_dir: Directory where translation JSON files are stored.
        :param default_lang: Language code to fall back on if a file cannot be
                             loaded for the requested language.
        """
        self.locales_dir = locales_dir
        self.default_lang = default_lang
        self.lang: str = default_lang
        self.translations: Dict[str, str] = {}
        self.set_language(default_lang)

    def _load_file(self, lang: str) -> Dict[str, str]:
        """
        Attempt to load a JSON file for the specified language.

        If the file cannot be found or parsed the returned dictionary will be empty.

        :param lang: Language code (e.g. 'en_US', 'zh_TW').
        :return: Dictionary mapping translation keys to strings.
        """
        filename = f"{lang}.json"
        path = os.path.join(self.locales_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except Exception:
            # ignore errors; return empty dict
            pass
        return {}

    def set_language(self, lang: str) -> None:
        """
        Set the active language. This will reload the translation file for
        the given language. If the file cannot be loaded the previous
        language will remain in use.

        :param lang: Language code to activate.
        """
        translations = self._load_file(lang)
        if translations:
            self.translations = translations
            self.lang = lang
        else:
            # fall back to default language
            fallback = self._load_file(self.default_lang)
            self.translations = fallback
            self.lang = self.default_lang

    def t(self, key: str) -> str:
        """
        Translate a key into the current language.

        :param key: Translation key.
        :return: The translated string if available, otherwise the key itself.
        """
        return self.translations.get(key, key)

    def available_languages(self) -> Dict[str, str]:
        """
        Discover available languages by scanning the locales directory.

        :return: Mapping of language codes to human readable names if defined.
        """
        langs: Dict[str, str] = {}
        try:
            for filename in os.listdir(self.locales_dir):
                if filename.endswith('.json'):
                    code = filename[:-5]
                    langs[code] = code
        except Exception:
            pass
        return langs


# --- i18n: discover available languages from a locales folder ---
def list_available_languages(locales_dir: str):
    """
    Returns a list of tuples (code, display_name). 'code' is the filename stem,
    e.g. 'zh_TW' for 'zh_TW.json'. If the JSON file contains 'language_name',
    that string is used as the display name; otherwise we fall back to the code.
    """
    import os, json
    langs = []
    try:
        for fn in os.listdir(locales_dir):
            if not fn.lower().endswith(".json"):
                continue
            code = os.path.splitext(fn)[0]
            display = code
            try:
                with open(os.path.join(locales_dir, fn), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    display = data.get("language_name") or code
            except Exception:
                pass
            langs.append((code, display))
    except Exception:
        pass
    # Keep it deterministic
    langs.sort(key=lambda x: x[1].lower())
    return langs

