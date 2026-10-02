package io.github.wasyleque.mailvoice.pairing

import io.github.wasyleque.mailvoice.net.PinnedTlsClient
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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.security.MessageDigest

@OptIn(ExperimentalCoroutinesApi::class)
class PairingRepositoryTest {

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

        tokenStore = InMemoryTokenStore()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun createRepository(): PairingRepository {
        return PairingRepository(
            tokenStore = tokenStore,
            clientFactory = { fp -> PinnedTlsClient.create(fp) },
            ioDispatcher = testDispatcher
        )
    }

    private fun createPayload(
        host: String = server.hostName,
        port: Int = server.port,
        code: String = "K7P9X2",
        fp: String = certFingerprintHex
    ): PairingPayload {
        return PairingPayload(
            host = host,
            port = port,
            code = code,
            fingerprint = fp,
            version = 1
        )
    }

    @Test
    fun testSuccessfulPairingAndStatusCheck() = runTest(testDispatcher) {
        val repo = createRepository()

        // 1. Response for POST /v1/pair
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"status":"ok","device_id":"dev-123","token":"token_secret_32b","message":"Pomyślnie"}""")
        )
        // 2. Response for subsequent GET /v1/status
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"version":"0.1.0","accounts_count":2,"active_devices_count":1,"last_tick":"2026-10-02T19:00:00Z"}""")
        )

        val result = repo.pair(createPayload(), "Poco F4")

        assertTrue("Powinien zakończyć się sukcesem", result is PairingResult.Success)
        val success = result as PairingResult.Success
        assertEquals("dev-123", success.deviceId)
        assertEquals("0.1.0", success.serverVersion)
        assertEquals(2, success.accountsCount)
        assertEquals(1, success.activeDevicesCount)
        assertEquals(server.hostName, success.serverHost)
        assertEquals(server.port, success.serverPort)

        assertTrue(tokenStore.isPaired())
        assertEquals("token_secret_32b", tokenStore.getToken())
        assertEquals(certFingerprintHex, tokenStore.getServerFingerprint())
        assertEquals("dev-123", tokenStore.getDeviceId())

        // Weryfikacja zapytań
        val pairReq = server.takeRequest()
        assertEquals("/v1/pair", pairReq.path)
        assertEquals("POST", pairReq.method)
        assertTrue(pairReq.body.readUtf8().contains("K7P9X2"))

        val statusReq = server.takeRequest()
        assertEquals("/v1/status", statusReq.path)
        assertEquals("GET", statusReq.method)
        assertEquals("Bearer token_secret_32b", statusReq.getHeader("Authorization"))
    }

    @Test
    fun testPairingFailsOnInvalidOrExpiredCode400() = runTest(testDispatcher) {
        val repo = createRepository()
        server.enqueue(MockResponse().setResponseCode(400).setBody("""{"detail":"Nieprawidłowy kod"}"""))

        val result = repo.pair(createPayload(), "Poco F4")

        assertTrue(result is PairingResult.Error)
        val error = result as PairingResult.Error
        assertTrue("Komunikat powinien wspominać o wygasłym kodzie", error.message.contains("wygasły kod"))
        assertFalse(tokenStore.isPaired())
    }

    @Test
    fun testPairingFailsOnDeviceLimit403() = runTest(testDispatcher) {
        val repo = createRepository()
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"detail":"Limit osiągnięty"}"""))

        val result = repo.pair(createPayload(), "Poco F4")

        assertTrue(result is PairingResult.Error)
        val error = result as PairingResult.Error
        assertTrue("Komunikat powinien wspominać o limicie urządzeń", error.message.contains("limit"))
        assertFalse(tokenStore.isPaired())
    }

    @Test
    fun testPairingFailsOnRateLimit429() = runTest(testDispatcher) {
        val repo = createRepository()
        server.enqueue(MockResponse().setResponseCode(429).setBody("""{"detail":"Zbyt wiele prób"}"""))

        val result = repo.pair(createPayload(), "Poco F4")

        assertTrue(result is PairingResult.Error)
        val error = result as PairingResult.Error
        assertTrue("Komunikat powinien wspominać o zbyt wielu próbach", error.message.contains("prób"))
        assertFalse(tokenStore.isPaired())
    }

    @Test
    fun testPairingFailsOnWrongCertificateFingerprint() = runTest(testDispatcher) {
        val repo = createRepository()
        val badFp = "0".repeat(64)
        val payload = createPayload(fp = badFp)

        val result = repo.pair(payload, "Poco F4")

        assertTrue(result is PairingResult.Error)
        val error = result as PairingResult.Error
        assertTrue("Powinien być alert bezpieczeństwa", error.isSecurityAlert)
        assertTrue(error.message.contains("Certyfikat"))
        assertFalse(tokenStore.isPaired())
    }

    @Test
    fun testPairingFailsOnConnectionRefused() = runTest(testDispatcher) {
        val repo = createRepository()
        // Używamy portu, na którym nic nie słucha
        val deadPort = 65432
        val payload = createPayload(port = deadPort)

        val result = repo.pair(payload, "Poco F4")

        assertTrue(result is PairingResult.Error)
        val error = result as PairingResult.Error
        assertTrue("Powinien być oznaczony jako błąd sieciowy", error.isNetworkError)
        assertTrue(error.message.contains("Nie można połączyć"))
        assertFalse(tokenStore.isPaired())
    }

    @Test
    fun testCheckStatusSuccess() = runTest(testDispatcher) {
        val repo = createRepository()
        tokenStore.saveCredentials(
            token = "saved_token",
            serverFingerprint = certFingerprintHex,
            serverHost = server.hostName,
            serverPort = server.port,
            deviceId = "dev-1"
        )

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"version":"0.2.1","accounts_count":3,"active_devices_count":2,"last_tick":"2026-10-02T19:20:00Z"}""")
        )

        val statusResult = repo.checkStatus()

        assertTrue(statusResult is ServerStatusResult.Connected)
        val connected = statusResult as ServerStatusResult.Connected
        assertEquals("0.2.1", connected.version)
        assertEquals(3, connected.accountsCount)
        assertEquals(2, connected.activeDevicesCount)
        assertEquals("2026-10-02T19:20:00Z", connected.lastTick)
    }

    @Test
    fun testCheckStatusUnauthorizedClearsTokenStore() = runTest(testDispatcher) {
        val repo = createRepository()
        tokenStore.saveCredentials(
            token = "revoked_token",
            serverFingerprint = certFingerprintHex,
            serverHost = server.hostName,
            serverPort = server.port
        )
        assertTrue(tokenStore.isPaired())

        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Token revoked"}"""))

        val statusResult = repo.checkStatus()

        assertTrue(statusResult is ServerStatusResult.Error)
        val error = statusResult as ServerStatusResult.Error
        assertTrue(error.isUnauthorized)
        assertFalse("TokenStore powinien zostać wyczyszczony po 401", tokenStore.isPaired())
    }

    @Test
    fun testCheckStatusWhenUnpaired() = runTest(testDispatcher) {
        val repo = createRepository()
        assertFalse(tokenStore.isPaired())

        val statusResult = repo.checkStatus()

        assertTrue(statusResult is ServerStatusResult.Error)
        val error = statusResult as ServerStatusResult.Error
        assertTrue(error.isUnauthorized)
        assertTrue(error.message.contains("nie jest sparowana"))
    }

    @Test
    fun testDisconnectSendsDeleteAndClearsStore() = runTest(testDispatcher) {
        val repo = createRepository()
        tokenStore.saveCredentials(
            token = "my_token",
            serverFingerprint = certFingerprintHex,
            serverHost = server.hostName,
            serverPort = server.port
        )
        assertTrue(tokenStore.isPaired())

        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))

        val disconnectRes = repo.disconnect()

        assertEquals(DisconnectResult.Success, disconnectRes)
        assertFalse("Po odłączeniu magazyn musi być pusty", tokenStore.isPaired())

        val req = server.takeRequest()
        assertEquals("/v1/devices/self", req.path)
        assertEquals("DELETE", req.method)
        assertEquals("Bearer my_token", req.getHeader("Authorization"))
    }

    @Test
    fun testDisconnectWhenServerUnreachableStillClearsStore() = runTest(testDispatcher) {
        val repo = createRepository()
        tokenStore.saveCredentials(
            token = "my_token",
            serverFingerprint = certFingerprintHex,
            serverHost = "127.0.0.1",
            serverPort = 65432 // dead port
        )
        assertTrue(tokenStore.isPaired())

        val disconnectRes = repo.disconnect()

        assertTrue(disconnectRes is DisconnectResult.Warning)
        assertFalse("Nawet przy braku sieci magazyn musi być natychmiast wyczyszczony", tokenStore.isPaired())
    }
}
