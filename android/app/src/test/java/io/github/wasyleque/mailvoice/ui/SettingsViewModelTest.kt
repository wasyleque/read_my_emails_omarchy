package io.github.wasyleque.mailvoice.ui

import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.net.PinnedTlsClient
import io.github.wasyleque.mailvoice.pairing.PairingRepository
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.security.MessageDigest

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var server: MockWebServer
    private lateinit var heldCertificate: HeldCertificate
    private lateinit var certFingerprintHex: String
    private lateinit var tokenStore: InMemoryTokenStore
    private lateinit var mailApi: MailApi
    private lateinit var pairingRepository: PairingRepository

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
        pairingRepository = PairingRepository(tokenStore, { fp -> PinnedTlsClient.create(fp) }, testDispatcher)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun testRefreshStatusSuccess() = runTest(testDispatcher) {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {
                  "version": "0.3.0",
                  "accounts_count": 2,
                  "active_devices_count": 1
                }
                """.trimIndent()
            )
        )

        val viewModel = SettingsViewModel(mailApi, pairingRepository, tokenStore)
        advanceUntilIdle()

        assertNotNull(viewModel.status.value)
        assertEquals("0.3.0", viewModel.status.value?.version)
        assertEquals(2, viewModel.status.value?.accountsCount)
        assertFalse(viewModel.isLoading.value)
    }

    @Test
    fun testLanguageSelection() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"version":"1.0"}"""))
        val viewModel = SettingsViewModel(mailApi, pairingRepository, tokenStore)
        advanceUntilIdle()

        assertEquals("pl", viewModel.selectedLanguage.value)
        viewModel.setLanguage("en")
        assertEquals("en", viewModel.selectedLanguage.value)
    }

    @Test
    fun testConfirmDisconnectClearsStoreAndTriggersCallback() = runTest(testDispatcher) {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"version":"1.0"}"""))
        val viewModel = SettingsViewModel(mailApi, pairingRepository, tokenStore)
        advanceUntilIdle()

        assertTrue(tokenStore.isPaired())

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))
        var callbackCalled = false
        viewModel.confirmDisconnect {
            callbackCalled = true
        }
        advanceUntilIdle()

        assertTrue(callbackCalled)
        assertFalse(tokenStore.isPaired())
    }
}
