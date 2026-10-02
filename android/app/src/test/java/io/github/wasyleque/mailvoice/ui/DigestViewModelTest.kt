package io.github.wasyleque.mailvoice.ui

import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.net.PinnedTlsClient
import io.github.wasyleque.mailvoice.security.InMemoryTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.security.MessageDigest

@OptIn(ExperimentalCoroutinesApi::class)
class DigestViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var server: MockWebServer
    private lateinit var heldCertificate: HeldCertificate
    private lateinit var certFingerprintHex: String
    private lateinit var tokenStore: InMemoryTokenStore
    private lateinit var mailApi: MailApi

    private fun sha256Hex(bytes: ByteArray): String {
        val md = MessageDigest.getInstance("SHA-256")
        return md.digest(bytes).joinToString("") { "%02x".format(it) }
    }

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)

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
            saveCredentials("token", certFingerprintHex, server.hostName, server.port)
        }
        mailApi = MailApi(tokenStore, { fp -> PinnedTlsClient.create(fp) }, testDispatcher)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun testLoadDigestSuccess() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "period": "ostatnie 30 dni",
                  "topics": [
                    {
                      "title": "Projekt Alfa",
                      "status": "oczekuje_na_mnie",
                      "why": "Podpisanie umowy",
                      "importance": 9,
                      "mail_count": 4,
                      "last_activity": "2026-10-02T12:00:00Z",
                      "who_to_whom": ["Klient -> Ty"]
                    }
                  ]
                }
                """.trimIndent()
            )
        )

        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()

        assertNotNull(viewModel.digest.value)
        assertEquals(1, viewModel.digest.value?.topics?.size)
        assertEquals("Projekt Alfa", viewModel.digest.value?.topics?.get(0)?.title)
        assertFalse(viewModel.isLoading.value)
    }

    @Test
    fun testSetDaysReloadsDigest() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody("""{"period":"30 dni","topics":[]}""")
        )
        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()

        server.enqueue(
            MockResponse().setResponseCode(200).setBody("""{"period":"7 dni","topics":[]}""")
        )
        viewModel.setDays(7)
        advanceUntilIdle()

        assertEquals(7, viewModel.days.value)
        server.takeRequest() // first req
        val req2 = server.takeRequest() // second req
        assertTrue(req2.path!!.contains("days=7"))
    }

    @Test
    fun testLoadDigestEmptyProducesEmptyStateNotError() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"period":"30 dni","topics":[]}"""))
        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()

        assertTrue("Pusta lista tematów musi dawać stan Empty, a NIE Error", viewModel.uiState.value is DigestUiState.Empty)
        assertFalse(viewModel.isLoading.value)
    }

    @Test
    fun testLoadDigestErrorProducesErrorState() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(500).setBody("Server Error"))
        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value is DigestUiState.Error)
        val errorState = viewModel.uiState.value as DigestUiState.Error
        assertTrue(errorState.canRetry)
        assertTrue(errorState.message.contains("Błąd serwera na komputerze"))
    }

    @Test
    fun testRefreshFailurePreservesOldDigest() = runTest(testDispatcher) {
        // Pierwsze udane ładowanie
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "period": "ostatnie 30 dni",
                  "topics": [
                    {
                      "title": "Projekt Alfa",
                      "status": "oczekuje_na_mnie",
                      "why": "Podpisanie umowy",
                      "importance": 9,
                      "mail_count": 4,
                      "last_activity": "2026-10-02T12:00:00Z",
                      "who_to_whom": ["Klient -> Ty"]
                    }
                  ]
                }
                """.trimIndent()
            )
        )
        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value is DigestUiState.Content)
        server.takeRequest()

        // Drugie nieudane ładowanie (odświeżenie)
        server.enqueue(MockResponse().setResponseCode(500).setBody("Server Error"))
        viewModel.loadDigest()
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value is DigestUiState.Content)
        val contentState = viewModel.uiState.value as DigestUiState.Content
        assertEquals(1, contentState.digest.topics.size)
        assertEquals("Projekt Alfa", contentState.digest.topics[0].title)
        assertNotNull(contentState.refreshError)
        assertTrue(contentState.refreshError!!.contains("Błąd serwera na komputerze"))

        viewModel.dismissError()
        assertNull((viewModel.uiState.value as DigestUiState.Content).refreshError)
    }

    @Test
    fun testSetShowAllRequestsAll1AndLimit100() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"period":"30 dni","topics":[]}"""))
        val viewModel = DigestViewModel(mailApi)
        advanceUntilIdle()
        server.takeRequest()

        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "period": "ostatnie 30 dni",
                  "topics": [
                    {
                      "title": "Zamknięta sprawa",
                      "status": "zamknięte",
                      "why": "Zrobione",
                      "importance": 2,
                      "mail_count": 1,
                      "last_activity": "2026-10-02T10:00:00Z",
                      "who_to_whom": []
                    }
                  ],
                  "counts": {"zamknięte": 1},
                  "total": 1,
                  "shown": 1
                }
                """.trimIndent()
            )
        )

        viewModel.setShowAll(true)
        advanceUntilIdle()

        val req = server.takeRequest()
        assertTrue("Żądanie musi zawierać all=1", req.path!!.contains("all=1"))
        assertTrue("Żądanie musi zawierać limit=100", req.path!!.contains("limit=100"))
        assertTrue(viewModel.showAll.value)
        assertTrue(viewModel.uiState.value is DigestUiState.Content)
        assertTrue((viewModel.uiState.value as DigestUiState.Content).showAll)
    }
}
