package io.github.wasyleque.mailvoice.pairing

import io.github.wasyleque.mailvoice.net.PinnedTlsClient
import io.github.wasyleque.mailvoice.security.TokenStore
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLException

sealed interface PairingResult {
    data class Success(
        val deviceId: String,
        val serverVersion: String,
        val accountsCount: Int,
        val activeDevicesCount: Int,
        val serverHost: String,
        val serverPort: Int
    ) : PairingResult

    data class Error(
        val message: String,
        val isSecurityAlert: Boolean = false,
        val isNetworkError: Boolean = false
    ) : PairingResult
}

sealed interface ServerStatusResult {
    data class Connected(
        val version: String,
        val accountsCount: Int,
        val activeDevicesCount: Int,
        val serverHost: String,
        val serverPort: Int,
        val lastTick: String? = null
    ) : ServerStatusResult

    data class Error(
        val message: String,
        val isUnauthorized: Boolean = false,
        val isSecurityAlert: Boolean = false,
        val isNetworkError: Boolean = false
    ) : ServerStatusResult
}

sealed interface DisconnectResult {
    data object Success : DisconnectResult
    data class Warning(val message: String) : DisconnectResult
}

/**
 * Repozytorium odpowiedzialne za przepływ parowania, sprawdzanie stanu połączenia
 * oraz bezpieczne odłączanie urządzenia.
 */
class PairingRepository(
    private val tokenStore: TokenStore,
    private val clientFactory: (fingerprint: String) -> OkHttpClient = { fp ->
        PinnedTlsClient.create(fp)
    },
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO
) {

    fun isPaired(): Boolean = tokenStore.isPaired()

    fun getSavedHost(): String? = tokenStore.getServerHost()

    fun getSavedPort(): Int = tokenStore.getServerPort()

    /**
     * Wykonuje parowanie z serwerem:
     * 1. POST /v1/pair z kodem i nazwą urządzenia przez PinnedTlsClient.
     * 2. Zapis tokenu i odcisku w bezpiecznym magazynie.
     * 3. GET /v1/status weryfikujący poprawność działania autoryzacji.
     */
    suspend fun pair(payload: PairingPayload, deviceName: String): PairingResult =
        withContext(ioDispatcher) {
            val client = try {
                clientFactory(payload.fingerprint)
            } catch (e: Exception) {
                return@withContext PairingResult.Error(
                    message = "Błąd inicjalizacji klienta TLS: ${e.localizedMessage ?: "brak szczegółów"}",
                    isSecurityAlert = true
                )
            }

            val jsonBody = JSONObject().apply {
                put("code", payload.code)
                put("device_name", deviceName)
            }.toString()

            val request = Request.Builder()
                .url("https://${payload.host}:${payload.port}/v1/pair")
                .post(jsonBody.toRequestBody("application/json; charset=utf-8".toMediaType()))
                .build()

            val token: String
            val deviceId: String

            try {
                client.newCall(request).execute().use { response ->
                    when (response.code) {
                        200 -> {
                            val bodyString = response.body?.string().orEmpty()
                            val jsonResp = try {
                                JSONObject(bodyString)
                            } catch (e: Exception) {
                                return@withContext PairingResult.Error("Błędny format odpowiedzi serwera (niepoprawny JSON).")
                            }

                            token = jsonResp.optString("token")
                            deviceId = jsonResp.optString("device_id")

                            if (token.isBlank()) {
                                return@withContext PairingResult.Error("Serwer nie przekazał wymaganego tokenu autoryzacyjnego.")
                            }

                            // Zapis poświadczeń
                            tokenStore.saveCredentials(
                                token = token,
                                serverFingerprint = payload.fingerprint,
                                serverHost = payload.host,
                                serverPort = payload.port,
                                deviceId = deviceId.ifBlank { null }
                            )
                        }
                        400 -> {
                            return@withContext PairingResult.Error(
                                "Niepoprawny lub wygasły kod parowania. Wygeneruj nowy kod QR w programie MailVoice na komputerze."
                            )
                        }
                        403 -> {
                            return@withContext PairingResult.Error(
                                "Osiągnięto limit sparowanych urządzeń w programie MailVoice (maksymalnie 5). Usuń nieużywane urządzenia w ustawieniach na komputerze."
                            )
                        }
                        429 -> {
                            return@withContext PairingResult.Error(
                                "Zbyt wiele prób połączenia. Odczekaj chwilę przed kolejną próbą (ochrona przed atakiem)."
                            )
                        }
                        500 -> {
                            return@withContext PairingResult.Error(
                                "Wewnętrzny błąd programu MailVoice na komputerze."
                            )
                        }
                        else -> {
                            return@withContext PairingResult.Error(
                                "Serwer zwrócił nieoczekiwany kod błędu (${response.code})."
                            )
                        }
                    }
                }
            } catch (e: SSLHandshakeException) {
                return@withContext PairingResult.Error(
                    message = "Certyfikat serwera nie pasuje do odcisku z kodu QR. Połączenie zostało zablokowane ze względów bezpieczeństwa.",
                    isSecurityAlert = true
                )
            } catch (e: SSLException) {
                return@withContext PairingResult.Error(
                    message = "Błąd szyfrowania TLS podczas łączenia z serwerem (${e.localizedMessage ?: "brak szczegółów"}).",
                    isSecurityAlert = true
                )
            } catch (e: ConnectException) {
                return@withContext PairingResult.Error(
                    message = "Nie można połączyć się z serwerem (${payload.host}:${payload.port}). Upewnij się, że komputer i telefon są w tej samej sieci Wi-Fi i program MailVoice jest włączony.",
                    isNetworkError = true
                )
            } catch (e: SocketTimeoutException) {
                return@withContext PairingResult.Error(
                    message = "Przekroczono czas oczekiwania na odpowiedź serwera (${payload.host}:${payload.port}). Sprawdź połączenie Wi-Fi.",
                    isNetworkError = true
                )
            } catch (e: UnknownHostException) {
                return@withContext PairingResult.Error(
                    message = "Nie znaleziono adresu komputera (${payload.host}). Sprawdź poprawność adresu.",
                    isNetworkError = true
                )
            } catch (e: IOException) {
                return@withContext PairingResult.Error(
                    message = "Błąd połączenia sieciowego: ${e.localizedMessage ?: "brak szczegółów"}",
                    isNetworkError = true
                )
            }

            // Krok 3: Weryfikacja połączenia i pobranie danych serwera przez GET /v1/status
            when (val statusRes = checkStatusInternal(client, payload.host, payload.port, token)) {
                is ServerStatusResult.Connected -> {
                    PairingResult.Success(
                        deviceId = deviceId,
                        serverVersion = statusRes.version,
                        accountsCount = statusRes.accountsCount,
                        activeDevicesCount = statusRes.activeDevicesCount,
                        serverHost = payload.host,
                        serverPort = payload.port
                    )
                }
                is ServerStatusResult.Error -> {
                    PairingResult.Error(
                        message = "Urządzenie sparowane, ale test połączenia nie powiódł się: ${statusRes.message}",
                        isSecurityAlert = statusRes.isSecurityAlert,
                        isNetworkError = statusRes.isNetworkError
                    )
                }
            }
        }

    /**
     * Sprawdza stan połączenia z serwerem dla wcześniej sparowanego urządzenia.
     */
    suspend fun checkStatus(): ServerStatusResult = withContext(ioDispatcher) {
        if (!tokenStore.isPaired()) {
            return@withContext ServerStatusResult.Error(
                message = "Aplikacja nie jest sparowana z komputerem.",
                isUnauthorized = true
            )
        }

        val token = tokenStore.getToken() ?: return@withContext ServerStatusResult.Error(
            message = "Brak zapisanego tokenu autoryzacyjnego.",
            isUnauthorized = true
        )
        val fingerprint = tokenStore.getServerFingerprint() ?: return@withContext ServerStatusResult.Error(
            message = "Brak zapisanego odcisku certyfikatu.",
            isUnauthorized = true
        )
        val host = tokenStore.getServerHost() ?: return@withContext ServerStatusResult.Error(
            message = "Brak zapisanego adresu serwera.",
            isUnauthorized = true
        )
        val port = tokenStore.getServerPort()

        val client = try {
            clientFactory(fingerprint)
        } catch (e: Exception) {
            return@withContext ServerStatusResult.Error(
                message = "Błąd inicjalizacji klienta TLS: ${e.localizedMessage ?: "brak szczegółów"}",
                isSecurityAlert = true
            )
        }

        checkStatusInternal(client, host, port, token)
    }

    private fun checkStatusInternal(
        client: OkHttpClient,
        host: String,
        port: Int,
        token: String
    ): ServerStatusResult {
        val request = Request.Builder()
            .url("https://$host:$port/v1/status")
            .header("Authorization", "Bearer $token")
            .get()
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                when (response.code) {
                    200 -> {
                        val bodyString = response.body?.string().orEmpty()
                        val json = try {
                            JSONObject(bodyString)
                        } catch (e: Exception) {
                            return ServerStatusResult.Error("Błędny format odpowiedzi statusu (niepoprawny JSON).")
                        }

                        ServerStatusResult.Connected(
                            version = json.optString("version", "nieznana"),
                            accountsCount = json.optInt("accounts_count", 0),
                            activeDevicesCount = json.optInt("active_devices_count", 0),
                            serverHost = host,
                            serverPort = port,
                            lastTick = json.optString("last_tick").ifBlank { null }
                        )
                    }
                    401 -> {
                        tokenStore.clear()
                        ServerStatusResult.Error(
                            message = "Autoryzacja wygasła lub została cofnięta na komputerze. Sparuj telefon ponownie.",
                            isUnauthorized = true
                        )
                    }
                    else -> {
                        ServerStatusResult.Error("Serwer zwrócił błąd statusu (kod ${response.code}).")
                    }
                }
            }
        } catch (e: SSLHandshakeException) {
            ServerStatusResult.Error(
                message = "Certyfikat serwera nie pasuje do odcisku. Połączenie zostało zablokowane ze względów bezpieczeństwa.",
                isSecurityAlert = true
            )
        } catch (e: SSLException) {
            ServerStatusResult.Error(
                message = "Błąd szyfrowania TLS: ${e.localizedMessage ?: "brak szczegółów"}",
                isSecurityAlert = true
            )
        } catch (e: ConnectException) {
            ServerStatusResult.Error(
                message = "Nie można połączyć się z serwerem ($host:$port). Upewnij się, że komputer i telefon są w tej samej sieci Wi-Fi.",
                isNetworkError = true
            )
        } catch (e: SocketTimeoutException) {
            ServerStatusResult.Error(
                message = "Przekroczono czas oczekiwania na odpowiedź serwera ($host:$port).",
                isNetworkError = true
            )
        } catch (e: UnknownHostException) {
            ServerStatusResult.Error(
                message = "Nie znaleziono adresu komputera ($host).",
                isNetworkError = true
            )
        } catch (e: IOException) {
            ServerStatusResult.Error(
                message = "Błąd połączenia z serwerem: ${e.localizedMessage ?: "brak szczegółów"}",
                isNetworkError = true
            )
        }
    }

    /**
     * Odłącza urządzenie:
     * 1. Wysyła DELETE /v1/devices/self do serwera (z krótkim timeoutem).
     * 2. Niezależnie od wyniku sieciowego bezwarunkowo czyści lokalny TokenStore.
     */
    suspend fun disconnect(): DisconnectResult = withContext(ioDispatcher) {
        val token = tokenStore.getToken()
        val fingerprint = tokenStore.getServerFingerprint()
        val host = tokenStore.getServerHost()
        val port = tokenStore.getServerPort()

        var warningMessage: String? = null

        if (!token.isNullOrBlank() && !fingerprint.isNullOrBlank() && !host.isNullOrBlank()) {
            try {
                val client = clientFactory(fingerprint)
                val request = Request.Builder()
                    .url("https://$host:$port/v1/devices/self")
                    .header("Authorization", "Bearer $token")
                    .delete()
                    .build()

                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful && response.code != 401 && response.code != 404) {
                        warningMessage = "Urządzenie odłączone lokalnie (serwer zwrócił kod ${response.code})."
                    }
                }
            } catch (e: Exception) {
                warningMessage = "Urządzenie odłączone lokalnie (komputer był niedostępny w sieci)."
            }
        }

        // Zawsze bezwarunkowo usuwamy poświadczenia z telefonu
        tokenStore.clear()

        val finalWarning = warningMessage
        if (finalWarning != null) {
            DisconnectResult.Warning(finalWarning)
        } else {
            DisconnectResult.Success
        }
    }
}
