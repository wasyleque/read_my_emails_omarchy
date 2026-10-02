package io.github.wasyleque.mailvoice.voice

import java.util.regex.Pattern

/**
 * Narzędzie oczyszczania tekstu z adresów URL i niebezpiecznych odnośników przed odczytaniem głosem.
 * Zgodnie z SECURITY.md:
 * - Aplikacja nigdy nie podąża za odnośnikami z maili.
 * - Głos nigdy nie czyta surowych adresów URL ani parametrów zapytań.
 */
object UrlSanitizer {

    private const val DEFANGED_TAG = "[link pominięty]"

    // Wyrażenie regularne wychwytujące adresy URL w różnych formatach (http, https, hxxp, ftp, www, domeny)
    private val URL_PATTERN = Pattern.compile(
        """(?i)\b(?:https?|hxxps?|ftp)://[^\s<>"'{}|\\^`]+|\bwww\.[^\s<>"'{}|\\^`]+|\b[a-z0-9.-]+\.(?:com|org|net|pl|eu|info|biz|io|de|uk|ru|cn|xyz|me)(?:/[^\s<>"'{}|\\^`]*)?""",
        Pattern.CASE_INSENSITIVE
    )

    // Wychwytuje istniejące znaczniki defangowania
    private val DEFANGED_PATTERN = Pattern.compile(
        """\[\s*link\s+pomini[eę]ty\s*\]|\[\s*link\s*\]""",
        Pattern.CASE_INSENSITIVE
    )

    /**
     * Zastępuje wszelkie wykryte adresy URL znacznikiem `[link pominięty]`.
     */
    fun sanitizeUrls(text: String, replacement: String = DEFANGED_TAG): String {
        if (text.isBlank()) return ""
        val matcher = URL_PATTERN.matcher(text)
        return matcher.replaceAll(replacement)
    }

    /**
     * Przygotowuje tekst do bezpiecznej syntezy mowy (TTS):
     * 1. Neutralizuje wszelkie adresy URL.
     * 2. Zastępuje znaczniki [link pominięty] naturalną frazą głosową "odnośnik pominięty"
     *    lub usuwa je, aby syntezator mowy nie wymawiał nawiasów kwadratowych.
     * 3. Normalizuje wielokrotne spacje.
     */
    fun prepareForSpeech(text: String, voicePhrase: String = "odnośnik pominięty"): String {
        if (text.isBlank()) return ""
        // Krok 1: zamiana surowych linków na znacznik
        val sanitized = sanitizeUrls(text, replacement = " $voicePhrase ")
        // Krok 2: zamiana ewentualnych istniejących znaczników [link pominięty] z serwera
        val cleanSpeech = DEFANGED_PATTERN.matcher(sanitized).replaceAll(" $voicePhrase ")
        // Krok 3: normalizacja białych znaków
        return cleanSpeech.replace(Regex("""\s+"""), " ").trim()
    }
}
