package io.github.wasyleque.mailvoice.net

import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.security.MessageDigest
import javax.net.ssl.SSLHandshakeException

/**
 * Testy jednostkowe klienta HTTPS z przypiętym odciskiem certyfikatu (PinnedTlsClient).
 */
class PinnedTlsClientTest {

    private lateinit var server: MockWebServer
    private lateinit var serverCert: HeldCertificate
    private lateinit var validFingerprintHex: String

    @Before
    fun setUp() {
        serverCert = HeldCertificate.Builder()
            .commonName("localhost")
            .addSubjectAlternativeName("127.0.0.1")
            .build()

        val handshakeCertificates = HandshakeCertificates.Builder()
            .heldCertificate(serverCert)
            .build()

        server = MockWebServer().apply {
            useHttps(handshakeCertificates.sslSocketFactory(), false)
            start()
        }

        // Obliczenie SHA-256 (DER) certyfikatu serwera
        val derBytes = serverCert.certificate.encoded
        val digest = MessageDigest.getInstance("SHA-256").digest(derBytes)
        validFingerprintHex = digest.joinToString("") { "%02x".format(it) }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun testRequestSucceedsWithMatchingFingerprint() {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))

        val client = PinnedTlsClient(expectedFingerprintHex = validFingerprintHex)
        val request = Request.Builder()
            .url(server.url("/v1/status"))
            .build()

        val response = client.execute(request)
        assertEquals(200, response.code)
        assertEquals("""{"status":"ok"}""", response.body?.string())
    }

    @Test
    fun testRequestFailsWithWrongFingerprint() {
        // Podajemy celowo sfałszowany odcisk
        val wrongFingerprint = "00".repeat(32)
        val client = PinnedTlsClient(expectedFingerprintHex = wrongFingerprint)
        val request = Request.Builder()
            .url(server.url("/v1/status"))
            .build()

        val ex = assertThrows(SSLHandshakeException::class.java) {
            client.execute(request)
        }
        assertTrue(
            ex.message?.contains("Odcisk") == true ||
            ex.cause?.message?.contains("Odcisk") == true ||
            ex.cause?.message?.contains("CertificateException") == true
        )
    }

    @Test
    fun testPlainHttpIsRejectedWithoutNetworkCall() {
        val client = PinnedTlsClient(expectedFingerprintHex = validFingerprintHex)
        val request = Request.Builder()
            .url("http://127.0.0.1:8765/v1/pair")
            .build()

        val ex = assertThrows(IllegalArgumentException::class.java) {
            client.execute(request)
        }
        assertTrue(ex.message!!.contains("HTTPS"))
    }
}
