package io.github.wasyleque.mailvoice.security

/**
 * Pamięciowa implementacja TokenStore do testów jednostkowych oraz scenariuszy bez stałego magazynu.
 */
class InMemoryTokenStore : TokenStore {
    private var token: String? = null
    private var fingerprint: String? = null
    private var host: String? = null
    private var port: Int = 0
    private var deviceId: String? = null

    @Synchronized
    override fun saveCredentials(
        token: String,
        serverFingerprint: String,
        serverHost: String,
        serverPort: Int,
        deviceId: String?
    ) {
        this.token = token
        this.fingerprint = serverFingerprint
        this.host = serverHost
        this.port = serverPort
        this.deviceId = deviceId
    }

    @Synchronized
    override fun getToken(): String? = token

    @Synchronized
    override fun getServerFingerprint(): String? = fingerprint

    @Synchronized
    override fun getServerHost(): String? = host

    @Synchronized
    override fun getServerPort(): Int = port

    @Synchronized
    override fun getDeviceId(): String? = deviceId

    @Synchronized
    override fun clear() {
        token = null
        fingerprint = null
        host = null
        port = 0
        deviceId = null
    }

    @Synchronized
    override fun isPaired(): Boolean {
        return !token.isNullOrBlank() && !fingerprint.isNullOrBlank()
    }
}
