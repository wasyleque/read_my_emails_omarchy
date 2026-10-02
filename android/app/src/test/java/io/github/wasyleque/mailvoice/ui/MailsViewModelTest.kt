package io.github.wasyleque.mailvoice.ui

import io.github.wasyleque.mailvoice.net.IgnoreMode
import io.github.wasyleque.mailvoice.net.ImportantMail
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
class MailsViewModelTest {

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
    fun testLoadMailsSuccess() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m1",
                      "sender": "Jan",
                      "subject": "Spotkanie",
                      "importance": 8,
                      "why": "Projekt",
                      "summary": "Streszczenie",
                      "suspicious": false,
                      "date": "2026-10-02T19:00:00Z",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )

        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()

        assertEquals(1, viewModel.mails.value.size)
        val mail = viewModel.mails.value[0]
        assertEquals("m1", mail.id)
        assertEquals("Jan", mail.sender)
        assertFalse(viewModel.isLoading.value)
    }

    @Test
    fun testSelectAndClearMail() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"mails":[]}"""))
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()

        val mail = ImportantMail(
            id = "m1",
            sender = "Nadawca",
            subject = "Temat",
            importance = 7,
            why = "Powód",
            summary = "Opis",
            suspicious = false,
            date = "dziś",
            acknowledged = false
        )

        assertNull(viewModel.selectedMail.value)
        viewModel.selectMail(mail)
        assertEquals("m1", viewModel.selectedMail.value?.id)

        viewModel.clearSelectedMail()
        assertNull(viewModel.selectedMail.value)
    }

    @Test
    fun testAckMailUpdatesLocalState() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m1",
                      "sender": "Jan",
                      "subject": "Temat",
                      "importance": 5,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()

        assertFalse(viewModel.mails.value[0].acknowledged)

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok","message":"Acked"}"""))
        viewModel.ackMail("m1")
        advanceUntilIdle()

        assertTrue(viewModel.mails.value[0].acknowledged)
    }

    @Test
    fun testStartVoiceSession() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m1",
                      "sender": "Jan",
                      "subject": "Temat",
                      "importance": 5,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()

        assertFalse(viewModel.isVoiceSessionActive.value)

        viewModel.startVoiceSession()
        assertTrue(viewModel.isVoiceSessionActive.value)

        viewModel.stopVoiceSession()
        assertFalse(viewModel.isVoiceSessionActive.value)
    }

    @Test
    fun testOpenAndDismissIgnoreDialog() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"mails":[]}"""))
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()

        val mail = ImportantMail(
            id = "m1",
            sender = "Jan",
            subject = "Temat",
            importance = 5,
            why = "P",
            summary = "S",
            suspicious = false,
            date = "d",
            acknowledged = false
        )

        assertNull(viewModel.ignoreDialogTarget.value)
        viewModel.openIgnoreDialog(mail)
        assertEquals("m1", viewModel.ignoreDialogTarget.value?.id)
        assertNull(viewModel.ignoreErrorMessage.value)

        viewModel.dismissIgnoreDialog()
        assertNull(viewModel.ignoreDialogTarget.value)
    }

    @Test
    fun testConfirmIgnoreSuccessRemovesMailAndRefreshes() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m1",
                      "sender": "Jan",
                      "subject": "Temat 1",
                      "importance": 5,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    },
                    {
                      "id": "m2",
                      "sender": "Adam",
                      "subject": "Temat 2",
                      "importance": 6,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()
        server.takeRequest() // konsumujemy początkowe GET /v1/mails/important

        assertEquals(2, viewModel.mails.value.size)
        val mail1 = viewModel.mails.value[0]
        viewModel.selectMail(mail1)
        assertEquals("m1", viewModel.selectedMail.value?.id)

        // Otwórz dialog ignorowania
        viewModel.openIgnoreDialog(mail1)
        assertEquals("m1", viewModel.ignoreDialogTarget.value?.id)

        // Odpowiedź na ignoreMail i odpowiedź na odświeżenie loadMails
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"status":"ok","mode":"similar","rule":"Jan"}"""
            )
        )
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m2",
                      "sender": "Adam",
                      "subject": "Temat 2",
                      "importance": 6,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )

        viewModel.confirmIgnore(IgnoreMode.SIMILAR)
        advanceUntilIdle()

        // Żądanie ignore
        val ignoreReq = server.takeRequest()
        assertEquals("/v1/mails/m1/ignore", ignoreReq.path)
        assertEquals("POST", ignoreReq.method)
        assertTrue(ignoreReq.body.readUtf8().contains("\"mode\":\"similar\""))

        // Żądanie refresh
        val refreshReq = server.takeRequest()
        assertEquals("/v1/mails/important?limit=30", refreshReq.path)

        // Stan po sukcesie
        assertFalse(viewModel.isIgnoring.value)
        assertNull(viewModel.ignoreDialogTarget.value)
        assertNull(viewModel.selectedMail.value) // m1 był wybrany, więc został wyczyszczony
        assertEquals("Zignorowano", viewModel.userMessage.value)
        assertEquals(1, viewModel.mails.value.size)
        assertEquals("m2", viewModel.mails.value[0].id)

        viewModel.clearUserMessage()
        assertNull(viewModel.userMessage.value)
    }

    @Test
    fun testConfirmIgnoreErrorPreservesDialogStateForRetry() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "mails": [
                    {
                      "id": "m1",
                      "sender": "Jan",
                      "subject": "Temat 1",
                      "importance": 5,
                      "why": "P",
                      "summary": "S",
                      "suspicious": false,
                      "date": "d",
                      "acknowledged": false
                    }
                  ]
                }
                """.trimIndent()
            )
        )
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()
        server.takeRequest()

        val mail1 = viewModel.mails.value[0]
        viewModel.openIgnoreDialog(mail1)

        server.enqueue(
            MockResponse().setResponseCode(400).setBody(
                """{"error":"Niepoprawny tryb ignorowania"}"""
            )
        )

        viewModel.confirmIgnore(IgnoreMode.SIMILAR)
        advanceUntilIdle()

        assertFalse(viewModel.isIgnoring.value)
        assertEquals("Niepoprawny tryb ignorowania", viewModel.ignoreErrorMessage.value)
        assertNotNull(viewModel.ignoreDialogTarget.value) // nadal otwarty do ponowienia
        assertEquals(1, viewModel.mails.value.size)
    }

    @Test
    fun testConfirmIgnoreUnauthorizedMarksUnauthorized() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"mails":[]}"""))
        val viewModel = MailsViewModel(mailApi)
        advanceUntilIdle()
        server.takeRequest()

        val mail = ImportantMail(
            id = "m1",
            sender = "Jan",
            subject = "Temat",
            importance = 5,
            why = "P",
            summary = "S",
            suspicious = false,
            date = "d",
            acknowledged = false
        )
        viewModel.openIgnoreDialog(mail)

        server.enqueue(
            MockResponse().setResponseCode(401).setBody(
                """{"error":"Brak autoryzacji"}"""
            )
        )

        viewModel.confirmIgnore(IgnoreMode.SIMILAR)
        advanceUntilIdle()

        assertFalse(viewModel.isIgnoring.value)
        assertTrue(viewModel.isUnauthorized.value)
    }
}
