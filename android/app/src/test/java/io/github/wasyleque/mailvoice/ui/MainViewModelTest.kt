package io.github.wasyleque.mailvoice.ui

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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.security.MessageDigest

@OptIn(ExperimentalCoroutinesApi::class)
class MainViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var server: MockWebServer
    private lateinit var heldCertificate: HeldCertificate
    private lateinit var certFingerprintHex: String
    private lateinit var tokenStore: InMemoryTokenStore
    private lateinit var repository: PairingRepository

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

        tokenStore = InMemoryTokenStore()
        repository = PairingRepository(
            tokenStore = tokenStore,
            clientFactory = { fp -> PinnedTlsClient.create(fp) },
            ioDispatcher = testDispatcher
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun testInitialStateUnpairedWhenNoCredentials() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue("Stan początkowy powinien być Unpaired", state is MainUiState.Unpaired)
    }

    @Test
    fun testInitialStateConnectedWhenCredentialsPresent() = runTest(testDispatcher) {
        tokenStore.saveCredentials(
            token = "saved_tok",
            serverFingerprint = certFingerprintHex,
            serverHost = server.hostName,
            serverPort = server.port
        )

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"version":"1.0.0","accounts_count":2,"active_devices_count":1}""")
        )

        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue("Powinien być Connected", state is MainUiState.Connected)
        val connected = state as MainUiState.Connected
        assertEquals("1.0.0", connected.serverVersion)
        assertEquals(2, connected.accountsCount)
        assertFalse(connected.isRefreshing)
    }

    @Test
    fun testStartScanPermissionFlow() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        // Bez uprawnienia -> rationale
        viewModel.onStartScanClicked(hasCameraPermission = false)
        val stateWithRationale = viewModel.uiState.value as MainUiState.Unpaired
        assertTrue(stateWithRationale.showCameraRationale)

        // Odmowa / zamknięcie rationale
        viewModel.onDismissCameraRationale()
        assertFalse((viewModel.uiState.value as MainUiState.Unpaired).showCameraRationale)

        // Przyznanie uprawnienia -> przejście do skanera
        viewModel.onCameraPermissionGranted()
        assertTrue(viewModel.uiState.value is MainUiState.ScanningQr)

        // Powrót
        viewModel.onBackToUnpaired()
        assertTrue(viewModel.uiState.value is MainUiState.Unpaired)
    }

    @Test
    fun testQrScanSuccessFlow() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        // Odpowiedzi serwera
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","device_id":"d1","token":"tok_new","message":"OK"}""")
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"version":"0.1.0","accounts_count":1,"active_devices_count":1}""")
        )

        val qrUrl = "mailvoice://pair?host=${server.hostName}&port=${server.port}&code=K7P9X2&fp=$certFingerprintHex&v=1"
        viewModel.onQrCodeScanned(qrUrl)
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue("Po udanym skanowaniu powinien przejść do Connected", state is MainUiState.Connected)
        val connected = state as MainUiState.Connected
        assertEquals("0.1.0", connected.serverVersion)
        assertEquals(1, connected.accountsCount)
        assertTrue(tokenStore.isPaired())
    }

    @Test
    fun testQrScanInvalidQrFormatShowsError() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        viewModel.onQrCodeScanned("https://google.com")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue(state is MainUiState.Unpaired)
        val unpaired = state as MainUiState.Unpaired
        assertNotNull(unpaired.errorMessage)
        assertTrue(unpaired.errorMessage!!.contains("mailvoice://pair"))
    }

    @Test
    fun testManualEntrySubmit() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        viewModel.onOpenManualEntry()
        assertTrue(viewModel.uiState.value is MainUiState.ManualEntry)

        // Odpowiedzi serwera
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","device_id":"d1","token":"tok_manual","message":"OK"}""")
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"version":"0.1.0","accounts_count":3,"active_devices_count":1}""")
        )

        viewModel.onManualSubmit(
            rawLink = "",
            host = server.hostName,
            portStr = server.port.toString(),
            code = "K7P9X2",
            fp = certFingerprintHex
        )
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue(state is MainUiState.Connected)
        assertEquals("0.1.0", (state as MainUiState.Connected).serverVersion)
    }

    @Test
    fun testManualEntryValidationFailsOnEmptyFields() = runTest(testDispatcher) {
        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()

        viewModel.onOpenManualEntry()

        viewModel.onManualSubmit("", "", "", "", "")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertTrue(state is MainUiState.ManualEntry)
        val manualState = state as MainUiState.ManualEntry
        assertNotNull(manualState.errorMessage)
        assertTrue(manualState.errorMessage!!.contains("wszystkie wymagane pola"))
    }

    @Test
    fun testDisconnectFlow() = runTest(testDispatcher) {
        tokenStore.saveCredentials("tok", certFingerprintHex, server.hostName, server.port)

        server.enqueue(
            MockResponse().setResponseCode(200).setBody("""{"version":"1.0"}""")
        )

        val viewModel = MainViewModel(repository, defaultDeviceName = "TestPhone")
        advanceUntilIdle()
        assertTrue(viewModel.uiState.value is MainUiState.Connected)

        viewModel.onRequestDisconnect()
        assertTrue((viewModel.uiState.value as MainUiState.Connected).showDisconnectDialog)

        viewModel.onDismissDisconnectDialog()
        assertFalse((viewModel.uiState.value as MainUiState.Connected).showDisconnectDialog)

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))
        viewModel.onConfirmDisconnect()
        advanceUntilIdle()

        assertTrue("Po rozłączeniu powinien być Unpaired", viewModel.uiState.value is MainUiState.Unpaired)
        assertFalse(tokenStore.isPaired())
    }
}
