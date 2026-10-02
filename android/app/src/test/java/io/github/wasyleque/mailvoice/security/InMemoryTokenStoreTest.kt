package io.github.wasyleque.mailvoice.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class InMemoryTokenStoreTest {

    private lateinit var store: InMemoryTokenStore

    @Before
    fun setUp() {
        store = InMemoryTokenStore()
    }

    @Test
    fun testInitiallyUnpaired() {
        assertFalse(store.isPaired())
        assertNull(store.getToken())
        assertNull(store.getServerFingerprint())
        assertNull(store.getServerHost())
        assertEquals(0, store.getServerPort())
        assertNull(store.getDeviceId())
    }

    @Test
    fun testSaveCredentialsAndIsPaired() {
        store.saveCredentials(
            token = "abc123token",
            serverFingerprint = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            serverHost = "192.168.1.50",
            serverPort = 8765,
            deviceId = "device-99"
        )

        assertTrue(store.isPaired())
        assertEquals("abc123token", store.getToken())
        assertEquals("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", store.getServerFingerprint())
        assertEquals("192.168.1.50", store.getServerHost())
        assertEquals(8765, store.getServerPort())
        assertEquals("device-99", store.getDeviceId())
    }

    @Test
    fun testClearRemovesAllCredentials() {
        store.saveCredentials(
            token = "abc123token",
            serverFingerprint = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            serverHost = "192.168.1.50",
            serverPort = 8765,
            deviceId = "device-99"
        )
        assertTrue(store.isPaired())

        store.clear()

        assertFalse(store.isPaired())
        assertNull(store.getToken())
        assertNull(store.getServerFingerprint())
        assertNull(store.getServerHost())
        assertEquals(0, store.getServerPort())
        assertNull(store.getDeviceId())
    }
}
