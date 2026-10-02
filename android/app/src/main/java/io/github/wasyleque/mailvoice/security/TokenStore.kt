package io.github.wasyleque.mailvoice.security

/**
 * Bezpieczny magazyn poświadczeń urządzenia (token Bearer, odcisk certyfikatu serwera, adres komputera).
 * Zgodnie z SECURITY.md tokeny i poświadczenia nigdy nie są logowane ani udostępniane w kopiach zapasowych.
 */
interface TokenStore {
    /**
     * Zapisuje bezpiecznie poświadczenia po pomyślnym sparowaniu.
     */
    fun saveCredentials(
        token: String,
        serverFingerprint: String,
        serverHost: String,
        serverPort: Int,
        deviceId: String? = null
    )

    fun getToken(): String?

    fun getServerFingerprint(): String?

    fun getServerHost(): String?

    fun getServerPort(): Int

    fun getDeviceId(): String?

    /**
     * Usuwa wszystkie zapisane poświadczenia z pamięci i magazynu.
     */
    fun clear()

    /**
     * Zwraca true jeśli urządzenie posiada ważny zapisany token i odcisk certyfikatu.
     */
    fun isPaired(): Boolean
}
