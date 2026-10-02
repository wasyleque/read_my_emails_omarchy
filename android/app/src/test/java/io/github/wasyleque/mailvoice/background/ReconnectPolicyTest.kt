package io.github.wasyleque.mailvoice.background

import java.io.IOException
import java.security.cert.CertificateException
import javax.net.ssl.SSLHandshakeException
import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReconnectPolicyTest {
    private val noJitter = object : Random() {
        override fun nextBits(bitCount: Int) = 0
        override fun nextDouble() = 0.0
    }

    @Test
    fun backoffDoublesAndIsCapped() {
        val p = ReconnectPolicy(1_000, 60_000, noJitter)
        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L), List(4) { p.nextDelayMs() })
        repeat(10) { p.nextDelayMs() }
        assertEquals(60_000L, p.nextDelayMs())
    }

    @Test
    fun resetStartsOver() {
        val p = ReconnectPolicy(1_000, 60_000, noJitter)
        repeat(5) { p.nextDelayMs() }
        p.reset()
        assertEquals(1_000L, p.nextDelayMs())
    }

    @Test
    fun jitterNeverExceedsMax() {
        val p = ReconnectPolicy(1_000, 60_000)
        repeat(50) { assertTrue(p.nextDelayMs() <= 60_000L) }
    }

    @Test
    fun fatalReasons() {
        assertEquals(FatalReason.UNAUTHORIZED, ReconnectPolicy.fatalFor(401, null))
        assertEquals(
            FatalReason.CERTIFICATE_CHANGED,
            ReconnectPolicy.fatalFor(null, SSLHandshakeException("x").apply { initCause(CertificateException("odcisk")) }),
        )
        assertEquals(
            FatalReason.CERTIFICATE_CHANGED,
            ReconnectPolicy.fatalFor(null, IOException("owinięty", CertificateException("odcisk"))),
        )
        assertNull(ReconnectPolicy.fatalFor(null, IOException("brak sieci")))
        assertNull(ReconnectPolicy.fatalFor(500, null))
    }
}
