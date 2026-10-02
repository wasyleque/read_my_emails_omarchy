package io.github.wasyleque.mailvoice.pairing

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/**
 * Testy jednostkowe parsera kodów QR parowania.
 */
class PairingQrParserTest {

    private val validFingerprint = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
    private val validQr =
        "mailvoice://pair?host=192.168.1.50&port=8765&code=K7P9X2&fp=$validFingerprint&v=1"

    @Test
    fun testParseValidQr() {
        val payload = PairingQrParser.parse(validQr)
        assertEquals("192.168.1.50", payload.host)
        assertEquals(8765, payload.port)
        assertEquals("K7P9X2", payload.code)
        assertEquals(validFingerprint.lowercase(), payload.fingerprint)
        assertEquals(1, payload.version)
    }

    @Test
    fun testParseValidWithUppercaseSchemeAndFp() {
        val upperFp = validFingerprint.uppercase()
        val qr = "MAILVOICE://PAIR?host=10.0.0.2&port=443&code=CODE12&fp=$upperFp&v=1"
        val payload = PairingQrParser.parse(qr)
        assertEquals("10.0.0.2", payload.host)
        assertEquals(443, payload.port)
        assertEquals("CODE12", payload.code)
        assertEquals(validFingerprint.lowercase(), payload.fingerprint)
    }

    @Test
    fun testParseMissingHost() {
        val qr = "mailvoice://pair?port=8765&code=K7P9X2&fp=$validFingerprint&v=1"
        val ex = assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse(qr)
        }
        assert(ex.message!!.contains("host"))
    }

    @Test
    fun testParseMissingPort() {
        val qr = "mailvoice://pair?host=192.168.1.50&code=K7P9X2&fp=$validFingerprint&v=1"
        val ex = assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse(qr)
        }
        assert(ex.message!!.contains("port"))
    }

    @Test
    fun testParseInvalidPortRange() {
        // Port 0
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50&port=0&code=K7P9X2&fp=$validFingerprint&v=1")
        }
        // Port 70000
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50&port=70000&code=K7P9X2&fp=$validFingerprint&v=1")
        }
        // Port niebędący liczbą
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50&port=abc&code=K7P9X2&fp=$validFingerprint&v=1")
        }
    }

    @Test
    fun testParseMissingCode() {
        val qr = "mailvoice://pair?host=192.168.1.50&port=8765&fp=$validFingerprint&v=1"
        val ex = assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse(qr)
        }
        assert(ex.message!!.contains("kod"))
    }

    @Test
    fun testParseInvalidFingerprintLength() {
        // Za krótki (63 znaki)
        val shortFp = validFingerprint.substring(0, 63)
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50&port=8765&code=K7P9X2&fp=$shortFp&v=1")
        }

        // Niepoprawne znaki hex (litera 'z')
        val badFp = validFingerprint.substring(0, 63) + "z"
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50&port=8765&code=K7P9X2&fp=$badFp&v=1")
        }
    }

    @Test
    fun testParseUnknownVersion() {
        val qr = "mailvoice://pair?host=192.168.1.50&port=8765&code=K7P9X2&fp=$validFingerprint&v=2"
        val ex = assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse(qr)
        }
        assert(ex.message!!.contains("wersja"))
    }

    @Test
    fun testParseInjectedCharacters() {
        // Wstrzyknięte znaki nowej linii w hoście
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50%0d%0aevil.com&port=8765&code=K7P9X2&fp=$validFingerprint&v=1")
        }

        // Ścieżka / traversal w hoście
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("mailvoice://pair?host=192.168.1.50/path&port=8765&code=K7P9X2&fp=$validFingerprint&v=1")
        }
    }

    @Test
    fun testParseWrongScheme() {
        assertThrows(InvalidPairingQrException::class.java) {
            PairingQrParser.parse("http://192.168.1.50:8765/pair?code=K7P9X2")
        }
    }
}
