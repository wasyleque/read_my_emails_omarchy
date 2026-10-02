package io.github.wasyleque.mailvoice.net

import io.github.wasyleque.mailvoice.security.InMemoryTokenStore
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.security.MessageDigest

@OptIn(ExperimentalCoroutinesApi::class)
class MailApiTest {

    private lateinit var server: MockWebServer
    private lateinit var heldCertificate: HeldCertificate
    private lateinit var certFingerprintHex: String
    private lateinit var tokenStore: InMemoryTokenStore
    private val testDispatcher = StandardTestDispatcher()

    private fun sha256Hex(bytes: ByteArray): String {
        val md = MessageDigest.getInstance("SHA-256")
        return md.digest(bytes).joinToString("") { "%02x".format(it) }
    }

    @Before
    fun setUp() {
        heldCertificate = HeldCertificate.Builder()
            .addSubjectAlternativeName("localhost")
            .addSubjectAlternativeName("127.0.0.1")
            .build()
        certFingerprintHex = sha256Hex(heldCertificate.certificate.encoded)

        val serverCertificates = HandshakeCertificates.Builder()
            .heldCertificate(heldCertificate)
            .build()

        server = MockWebServer()
        server.useHttps(serverCertificates.sslSocketFactory(), false)
        server.start(InetAddress.getByName("127.0.0.1"), 0)

        tokenStore = InMemoryTokenStore().apply {
            saveCredentials(
                token = "test_bearer_token",
                serverFingerprint = certFingerprintHex,
                serverHost = server.hostName,
                serverPort = server.port,
                deviceId = "dev-1"
            )
        }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun createApi(): MailApi {
        return MailApi(
            tokenStore = tokenStore,
            clientFactory = { fp -> PinnedTlsClient.create(fp) },
            ioDispatcher = testDispatcher
        )
    }

    @Test
    fun testGetImportantMailsSuccess() = runTest(testDispatcher) {
        val api = createApi()

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "mails": [
                        {
                          "id": "mail-1",
                          "sender": "Jan Kowalski <jan@firma.pl>",
                          "subject": "Raport miesięczny [link pominięty]",
                          "importance": 9,
                          "why": "Ważny raport od szefa",
                          "summary": "Przesyłam raport za wrzesień.",
                          "suspicious": false,
                          "date": "2026-10-02T18:00:00Z",
                          "acknowledged": false
                        },
                        {
                          "id": "mail-2",
                          "sender": "Bank <alert@oszustwo.com>",
                          "subject": "Twoje konto zostało zablokowane",
                          "importance": 7,
                          "why": "Presja czasu",
                          "summary": null,
                          "suspicious": true,
                          "date": "2026-10-02T17:00:00Z",
                          "acknowledged": false
                        }
                      ]
                    }
                    """.trimIndent()
                )
        )

        val result = api.getImportantMails(limit = 10)

        assertTrue(result is ApiResult.Success)
        val mails = (result as ApiResult.Success).data
        assertEquals(2, mails.size)

        val first = mails[0]
        assertEquals("mail-1", first.id)
        assertEquals("Jan Kowalski <jan@firma.pl>", first.sender)
        assertEquals(9, first.importance)
        assertEquals("Przesyłam raport za wrzesień.", first.summary)
        assertFalse(first.suspicious)

        val second = mails[1]
        assertEquals("mail-2", second.id)
        assertTrue(second.suspicious)
        assertNull(second.summary)

        val request = server.takeRequest()
        assertEquals("/v1/mails/important?limit=10", request.path)
        assertEquals("Bearer test_bearer_token", request.getHeader("Authorization"))
    }

    @Test
    fun testGetMailSummarySuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "mail-123",
                      "suspicious": false,
                      "warning": null,
                      "summary": "Podsumowanie w 3 zdaniach."
                    }
                    """.trimIndent()
                )
        )

        val result = api.getMailSummary("mail-123")

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("mail-123", data.id)
        assertFalse(data.suspicious)
        assertEquals("Podsumowanie w 3 zdaniach.", data.summary)
    }

    @Test
    fun testAckMailSuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","message":"Wiadomość oznaczona jako wysłuchana."}""")
        )

        val result = api.ackMail("mail-99")

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("ok", data.status)

        val request = server.takeRequest()
        assertEquals("/v1/mails/mail-99/ack", request.path)
        assertEquals("POST", request.method)
    }

    @Test
    fun testGetDigestSuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "period": "ostatnie 30 dni",
                      "topics": [
                        {
                          "title": "Wdrożenie ERP",
                          "status": "oczekuje_na_mnie",
                          "why": "Akceptacja kosztorysu",
                          "importance": 9,
                          "mail_count": 5,
                          "last_activity": "2026-10-02T15:00:00Z",
                          "who_to_whom": ["Kowalski -> Ty", "Ty -> Zarząd"]
                        }
                      ]
                    }
                    """.trimIndent()
                )
        )

        val result = api.getDigest(days = 30)

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("ostatnie 30 dni", data.period)
        assertEquals(1, data.topics.size)
        val topic = data.topics[0]
        assertEquals("Wdrożenie ERP", topic.title)
        assertEquals("oczekuje_na_mnie", topic.status)
        assertEquals(2, topic.whoToWhom.size)
        assertEquals("Kowalski -> Ty", topic.whoToWhom[0])
    }

    @Test
    fun testSendVoiceCommandSuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"action":"next","reply_text":"Przechodzę do kolejnej wiadomości."}""")
        )

        val result = api.sendVoiceCommand(text = "następny mail", lang = "pl")

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("next", data.action)
        assertEquals("Przechodzę do kolejnej wiadomości.", data.replyText)

        val request = server.takeRequest()
        assertEquals("/v1/voice/command", request.path)
        val bodyStr = request.body.readUtf8()
        assertTrue(bodyStr.contains("następny mail"))
        assertTrue(bodyStr.contains("pl"))
    }

    @Test
    fun testUnauthorized401ClearsTokenStore() = runTest(testDispatcher) {
        val api = createApi()
        assertTrue(tokenStore.isPaired())

        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Token unieważniony"}"""))

        val result = api.getImportantMails()

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertTrue(error.isUnauthorized)
        assertEquals(401, error.httpCode)
        assertFalse("TokenStore powinien zostać wyczyszczony przy 401", tokenStore.isPaired())
    }

    @Test
    fun testCertificateMismatchProducesSecurityAlert() = runTest(testDispatcher) {
        val badStore = InMemoryTokenStore().apply {
            saveCredentials(
                token = "test_token",
                serverFingerprint = "0".repeat(64),
                serverHost = server.hostName,
                serverPort = server.port
            )
        }
        val api = MailApi(
            tokenStore = badStore,
            clientFactory = { fp -> PinnedTlsClient.create(fp) },
            ioDispatcher = testDispatcher
        )

        val result = api.getStatus()

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertTrue(error.isSecurityAlert)
        assertTrue(error.message.contains("Certyfikat komputera się zmienił"))
    }

    @Test
    fun testIgnoreMailSuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","mode":"similar","rule":"Nadawca info@sklep.pl i podobny temat"}""")
        )

        val result = api.ignoreMail("m123", mode = "similar")

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("ok", data.status)
        assertEquals("similar", data.mode)
        assertEquals("Nadawca info@sklep.pl i podobny temat", data.rule)

        val request = server.takeRequest()
        assertEquals("/v1/mails/m123/ignore", request.path)
        assertEquals("POST", request.method)
        assertEquals("Bearer test_bearer_token", request.getHeader("Authorization"))
        val bodyStr = request.body.readUtf8()
        assertTrue(bodyStr.contains("\"mode\":\"similar\""))
    }

    @Test
    fun testIgnoreMail400BadRequest() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setBody("""{"error":"Nieznany tryb ignorowania."}""")
        )

        val result = api.ignoreMail("m123", mode = "invalid_mode")

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertEquals(400, error.httpCode)
        assertTrue(error.message.contains("Nieznany tryb ignorowania"))
    }

    @Test
    fun testIgnoreMail404NotFound() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(404)
                .setBody("""{"error":"Wiadomość nie znaleziona."}""")
        )

        val result = api.ignoreMail("nonexistent", mode = "sender")

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertEquals(404, error.httpCode)
        assertTrue(error.message.contains("Wiadomość nie znaleziona"))
    }

    @Test
    fun testIgnoreMail503ServiceUnavailable() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(503)
                .setBody("""{"error":"Ignorowanie jest niedostępne."}""")
        )

        val result = api.ignoreMail("m123", mode = "domain")

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertEquals(503, error.httpCode)
        assertTrue(error.message.contains("Ignorowanie jest niedostępne"))
    }

    @Test
    fun testIgnoreMail401Unauthorized() = runTest(testDispatcher) {
        val api = createApi()
        assertTrue(tokenStore.isPaired())

        server.enqueue(
            MockResponse()
                .setResponseCode(401)
                .setBody("""{"error":"Brak autoryzacji"}""")
        )

        val result = api.ignoreMail("m123", mode = "similar")

        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertTrue(error.isUnauthorized)
        assertEquals(401, error.httpCode)
        assertFalse("TokenStore musi zostać wyczyszczony przy 401", tokenStore.isPaired())
    }

    @Test
    fun testGetDigestWithCountsTotalShownAndAllParameter() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "period": "ostatnie 30 dni",
                      "topics": [
                        {
                          "title": "Projekt ERP",
                          "status": "oczekuje_na_mnie",
                          "why": "Zatwierdzenie",
                          "importance": 8,
                          "mail_count": 3,
                          "last_activity": "2026-10-02T16:00:00Z",
                          "who_to_whom": ["Klient -> Ty"]
                        }
                      ],
                      "counts": {
                        "oczekuje_na_mnie": 134,
                        "oczekuje_na_innych": 36,
                        "zamknięte": 200,
                        "informacyjne": 97
                      },
                      "total": 467,
                      "shown": 100
                    }
                    """.trimIndent()
                )
        )

        val result = api.getDigest(days = 30, limit = 100, all = true)

        val recorded = server.takeRequest()
        assertEquals("/v1/digest?days=30&limit=100&all=1", recorded.path)

        assertTrue(result is ApiResult.Success)
        val digest = (result as ApiResult.Success).data
        assertEquals("ostatnie 30 dni", digest.period)
        assertEquals(1, digest.topics.size)
        assertEquals(134, digest.counts["oczekuje_na_mnie"])
        assertEquals(36, digest.counts["oczekuje_na_innych"])
        assertEquals(200, digest.counts["zamknięte"])
        assertEquals(97, digest.counts["informacyjne"])
        assertEquals(467, digest.total)
        assertEquals(100, digest.shown)
        // Licznik ukrytych tematów
        val hiddenCount = (digest.total ?: 0) - (digest.shown ?: 0)
        assertEquals(367, hiddenCount)
    }

    @Test
    fun testGetDigestWithoutCountsBackwardCompatible() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "period": "ostatnie 30 dni",
                      "topics": []
                    }
                    """.trimIndent()
                )
        )

        val result = api.getDigest(days = 30, limit = 60, all = false)

        val recorded = server.takeRequest()
        assertEquals("/v1/digest?days=30&limit=60", recorded.path)

        assertTrue(result is ApiResult.Success)
        val digest = (result as ApiResult.Success).data
        assertTrue(digest.counts.isEmpty())
        assertNull(digest.total)
        assertNull(digest.shown)
    }

    @Test
    fun testErrorMapping429RateLimit() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(MockResponse().setResponseCode(429).setBody("Too Many Requests"))

        val result = api.getImportantMails()
        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertEquals(429, error.httpCode)
        assertTrue(error.message.contains("Zbyt wiele zapytań"))
    }

    @Test
    fun testErrorMapping500ServerError() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(MockResponse().setResponseCode(500).setBody("Internal Server Error"))

        val result = api.getImportantMails()
        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertEquals(500, error.httpCode)
        assertTrue(error.message.contains("Błąd serwera na komputerze"))
    }

    @Test
    fun testErrorMappingInvalidJson() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(MockResponse().setResponseCode(200).setBody("not valid json"))

        val result = api.getImportantMails()
        assertTrue(result is ApiResult.Error)
        val error = result as ApiResult.Error
        assertTrue(error.message.contains("Błąd przetwarzania odpowiedzi serwera"))
    }

    // ---------- VIP (lustro „Ignoruj”) ----------

    @Test
    fun testVipMailSuccess() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","mode":"similar","rule":"od: faktury@dostawca.pl, temat zawiera: faktura"}""")
        )

        val result = api.vipMail("m123", mode = "similar")

        assertTrue(result is ApiResult.Success)
        val data = (result as ApiResult.Success).data
        assertEquals("ok", data.status)
        assertEquals("similar", data.mode)
        assertEquals("od: faktury@dostawca.pl, temat zawiera: faktura", data.rule)

        val request = server.takeRequest()
        assertEquals("/v1/mails/m123/vip", request.path)
        assertEquals("POST", request.method)
        assertEquals("Bearer test_bearer_token", request.getHeader("Authorization"))
        assertTrue(request.body.readUtf8().contains("\"mode\":\"similar\""))
    }

    @Test
    fun testVipMailErrors() = runTest(testDispatcher) {
        val api = createApi()
        for ((code, body, fragment) in listOf(
            Triple(400, """{"error":"Nieznany tryb."}""", "Nieznany tryb"),
            Triple(404, """{"error":"Wiadomość nie znaleziona."}""", "Wiadomość nie znaleziona"),
            Triple(503, """{"error":"Ta funkcja jest niedostępna."}""", "niedostępna"),
        )) {
            server.enqueue(MockResponse().setResponseCode(code).setBody(body))
            val result = api.vipMail("m123", mode = "sender")
            assertTrue("kod $code", result is ApiResult.Error)
            val error = result as ApiResult.Error
            assertEquals(code, error.httpCode)
            assertTrue("kod $code: ${error.message}", error.message.contains(fragment))
            server.takeRequest()
        }
    }

    @Test
    fun testVipMail401Unauthorized() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"Brak autoryzacji"}"""))

        val result = api.vipMail("m123", mode = "domain")

        assertTrue(result is ApiResult.Error)
        assertTrue((result as ApiResult.Error).isUnauthorized)
        assertFalse("TokenStore musi zostać wyczyszczony przy 401", tokenStore.isPaired())
    }

    @Test
    fun testDigestParsesOptionalVipFlag() = runTest(testDispatcher) {
        val api = createApi()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {"period":"ostatnie 30 dni","topics":[
                  {"title":"Sprawa VIP","status":"oczekuje_na_mnie","why":"p","importance":9,"mail_count":2,
                   "last_activity":"2026-10-02T10:00:00","who_to_whom":["a -> b"],"vip":true},
                  {"title":"Zwykła","status":"oczekuje_na_mnie","why":"p","importance":5,"mail_count":1,
                   "last_activity":"2026-10-02T09:00:00","who_to_whom":[]}
                ]}
                """.trimIndent()
            )
        )

        val result = api.getDigest(days = 30)

        assertTrue(result is ApiResult.Success)
        val topics = (result as ApiResult.Success).data.topics
        assertTrue(topics[0].vip)
        assertFalse("stary serwer nie wysyła pola vip", topics[1].vip)
    }
}
