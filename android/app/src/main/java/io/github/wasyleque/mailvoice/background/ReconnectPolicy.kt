package io.github.wasyleque.mailvoice.background

import kotlin.random.Random

/** Dlaczego połączenie z komputerem zostało przerwane na stałe (ponawianie nic nie da). */
enum class FatalReason { UNAUTHORIZED, CERTIFICATE_CHANGED }

/**
 * Wykładniczy odstęp między próbami połączenia z losowym rozrzutem (żeby nie obciążać serwera i
 * baterii). Po stabilnym połączeniu odstęp wraca do początkowego.
 */
class ReconnectPolicy(
    private val baseMs: Long = 1_000,
    private val maxMs: Long = 60_000,
    private val random: Random = Random.Default,
) {
    private var attempt = 0

    /** Czas oczekiwania przed kolejną próbą. */
    fun nextDelayMs(): Long {
        val exp = (baseMs shl attempt.coerceAtMost(20)).coerceAtMost(maxMs)
        attempt++
        val jitter = (exp * 0.2 * random.nextDouble()).toLong()
        return (exp + jitter).coerceAtMost(maxMs)
    }

    fun reset() {
        attempt = 0
    }

    companion object {
        /** HTTP 401 = token odwołany/zły: parowanie trzeba powtórzyć, nie ponawiaj. */
        fun fatalFor(httpCode: Int?, error: Throwable?): FatalReason? {
            if (httpCode == 401) return FatalReason.UNAUTHORIZED
            var cause: Throwable? = error
            while (cause != null) {
                val name = cause.javaClass.simpleName
                if (name.contains("CertificateException") || name.contains("SSLHandshake") ||
                    name.contains("SSLPeerUnverified")
                ) {
                    return FatalReason.CERTIFICATE_CHANGED
                }
                cause = cause.cause
            }
            return null
        }
    }
}
