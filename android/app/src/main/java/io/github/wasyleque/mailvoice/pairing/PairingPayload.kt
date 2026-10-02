package io.github.wasyleque.mailvoice.pairing

/**
 * Model danych odczytanych z kodu QR lub wprowadzonych ręcznie podczas parowania.
 *
 * @property host Adres IP lub nazwa hosta komputera w sieci lokalnej (np. 192.168.1.50).
 * @property port Port HTTPS serwera (domyślnie 8765).
 * @property code Jednorazowy kod parowania wygenerowany przez komputer.
 * @property fingerprint 64-znakowy heksadecymalny odcisk palca SHA-256 certyfikatu serwera.
 * @property version Wersja protokołu parowania (obecnie 1).
 */
data class PairingPayload(
    val host: String,
    val port: Int,
    val code: String,
    val fingerprint: String,
    val version: Int = 1
)
