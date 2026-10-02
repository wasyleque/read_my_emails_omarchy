package io.github.wasyleque.mailvoice.pairing

import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * Wyjątek rzucany w przypadku błędnego formatu lub niepoprawnych danych w kodzie QR.
 */
class InvalidPairingQrException(message: String) : Exception(message)

/**
 * Bezpieczny parser kodów QR parowania aplikacji MailVoice.
 *
 * Oczekiwany format:
 *   mailvoice://pair?host=<ip>&port=<port>&code=<kod>&fp=<sha256 hex>&v=1
 */
object PairingQrParser {

    private const val EXPECTED_SCHEME_PREFIX = "mailvoice://pair?"
    private val HEX_64_REGEX = Regex("^[0-9a-fA-F]{64}$")
    private val CODE_REGEX = Regex("^[A-Za-z0-9_-]{1,32}$")
    private val HOST_REGEX = Regex("^[a-zA-Z0-9.\\[\\]:_\\-]+$")

    /**
     * Parsuje i waliduje surowy ciąg znaków z kodu QR.
     *
     * @param rawText Tekst zdekodowany ze skanu kodu QR.
     * @return Zwalidowany obiekt [PairingPayload].
     * @throws InvalidPairingQrException Gdy dane są niekompletne, uszkodzone lub niebezpieczne.
     */
    fun parse(rawText: String): PairingPayload {
        val trimmed = rawText.trim()
        if (trimmed.isEmpty()) {
            throw InvalidPairingQrException("Zeskanowany kod QR jest pusty.")
        }

        // Sprawdzenie schematu i akcji
        if (!trimmed.startsWith(EXPECTED_SCHEME_PREFIX, ignoreCase = true)) {
            throw InvalidPairingQrException(
                "Kod nie jest poprawnym adresem parowania MailVoice (oczekiwano mailvoice://pair?...)."
            )
        }

        val queryString = trimmed.substring(EXPECTED_SCHEME_PREFIX.length)
        if (queryString.isEmpty()) {
            throw InvalidPairingQrException("Brak parametrów konfiguracyjnych w kodzie QR.")
        }

        val params = parseQueryString(queryString)

        // 1. Walidacja wersji
        val versionStr = params["v"]
            ?: throw InvalidPairingQrException("Brak parametru wersji (v) w kodzie QR.")
        val version = versionStr.toIntOrNull()
        if (version != 1) {
            throw InvalidPairingQrException(
                "Nieobsługiwana wersja protokołu parowania: '$versionStr' (wymagana wersja 1)."
            )
        }

        // 2. Walidacja hosta
        val host = params["host"]?.trim()
        if (host.isNullOrEmpty()) {
            throw InvalidPairingQrException("Brak adresu serwera (host) w kodzie QR.")
        }
        if (!HOST_REGEX.matches(host) || host.contains(" ") || host.contains("/") || host.contains("\\")) {
            throw InvalidPairingQrException("Nieprawidłowy lub niebezpieczny adres serwera: '$host'.")
        }

        // 3. Walidacja portu
        val portStr = params["port"]?.trim()
            ?: throw InvalidPairingQrException("Brak numeru portu serwera w kodzie QR.")
        val port = portStr.toIntOrNull()
        if (port == null || port !in 1..65535) {
            throw InvalidPairingQrException(
                "Nieprawidłowy numer portu serwera: '$portStr' (wymagany port 1–65535)."
            )
        }

        // 4. Walidacja kodu parowania
        val code = params["code"]?.trim()
        if (code.isNullOrEmpty()) {
            throw InvalidPairingQrException("Brak kodu parowania w kodzie QR.")
        }
        if (!CODE_REGEX.matches(code)) {
            throw InvalidPairingQrException("Nieprawidłowy format kodu parowania.")
        }

        // 5. Walidacja odcisku certyfikatu SHA-256
        val fp = params["fp"]?.trim()
        if (fp.isNullOrEmpty()) {
            throw InvalidPairingQrException("Brak odcisku certyfikatu serwera (fp) w kodzie QR.")
        }
        if (!HEX_64_REGEX.matches(fp)) {
            throw InvalidPairingQrException(
                "Nieprawidłowy odcisk certyfikatu serwera (wymagany 64-znakowy skrót SHA-256 w systemie szesnastkowym)."
            )
        }

        return PairingPayload(
            host = host,
            port = port,
            code = code,
            fingerprint = fp.lowercase(),
            version = version
        )
    }

    private fun parseQueryString(query: String): Map<String, String> {
        val result = mutableMapOf<String, String>()
        val pairs = query.split('&')
        for (pair in pairs) {
            if (pair.isEmpty()) continue
            val parts = pair.split('=', limit = 2)
            val key = URLDecoder.decode(parts[0], StandardCharsets.UTF_8.name())
            val value = if (parts.size == 2) {
                URLDecoder.decode(parts[1], StandardCharsets.UTF_8.name())
            } else {
                ""
            }
            result[key] = value
        }
        return result
    }
}
