package io.github.wasyleque.mailvoice.net

import okhttp3.Call
import okhttp3.ConnectionSpec
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.TlsVersion
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * Klient HTTP z wymuszonym TLS 1.2+ oraz weryfikacją samopodpisanego certyfikatu
 * serwera w oparciu o stałoczasowe porównanie odcisku palca SHA-256 (Certificate Pinning).
 *
 * Uzasadnienie architektury bezpieczeństwa:
 * 1. Wybór OkHttp zamiast HttpsURLConnection:
 *    - Natywna, bezpieczna konfiguracja własnego X509TrustManager bez modyfikowania
 *      globalnego stanu maszyny JVM (HttpsURLConnection.setDefaultSSLSocketFactory
 *      jest podatne na wyścigi wątków i wpływa na cały proces).
 *    - Pierwszorzędne wsparcie dla puli połączeń, limitów czasu i późniejszego WebSocket (WSS).
 * 2. Weryfikacja odcisku zamiast nazwy hosta (HostnameVerifier):
 *    - Serwer MailVoice działa w sieci lokalnej (LAN), gdzie adres IP może być przydzielany dynamicznie
 *      przez router (DHCP), a nazwy domenowe mDNS nie zawsze są dostępne.
 *    - Przypięcie dokładnego odcisku SHA-256 (DER) certyfikatu serwera jest kryptograficznie
 *      ściśle silniejsze niż weryfikacja nazwy hosta: nawet w przypadku podsłuchu ARP lub
 *      fałszowania DNS, atakujący nie jest w stanie wygenerować certyfikatu o identycznym skrócie SHA-256.
 * 3. Wymuszenie TLS 1.2+:
 *    - Dozwolone są wyłącznie protokoły TLS 1.2 i TLS 1.3. Starsze wersje (SSLv3, TLS 1.0, 1.1)
 *      oraz ruch nieszyfrowany (HTTP) są bezwzględnie blokowane.
 */
class PinnedTlsClient(
    val expectedFingerprintHex: String,
    connectTimeoutSeconds: Long = 10,
    readTimeoutSeconds: Long = 15
) {
    private val normalizedFingerprintHex = expectedFingerprintHex.trim().lowercase()

    init {
        require(normalizedFingerprintHex.length == 64 && normalizedFingerprintHex.all { it in "0123456789abcdef" }) {
            "Nieprawidłowy format odcisku certyfikatu SHA-256: '$expectedFingerprintHex'."
        }
    }

    private val trustManager = FingerprintTrustManager(normalizedFingerprintHex)

    val okHttpClient: OkHttpClient = buildOkHttpClient(connectTimeoutSeconds, readTimeoutSeconds)

    private fun buildOkHttpClient(connectTimeout: Long, readTimeout: Long): OkHttpClient {
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(trustManager), SecureRandom())
        }

        // Wymuszenie nowoczesnego TLS (1.2 i 1.3)
        val tlsSpec = ConnectionSpec.Builder(ConnectionSpec.MODERN_TLS)
            .tlsVersions(TlsVersion.TLS_1_3, TlsVersion.TLS_1_2)
            .build()

        return OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustManager)
            .hostnameVerifier(HostnameVerifier { _, _ ->
                // Weryfikacja tożsamości serwera opiera się w 100% na przypiętym odcisku SHA-256 certyfikatu
                true
            })
            .connectionSpecs(listOf(tlsSpec))
            .connectTimeout(connectTimeout, TimeUnit.SECONDS)
            .readTimeout(readTimeout, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .build()
    }

    /**
     * Tworzy wywołanie HTTP sprawdzając uprzednio, czy protokół to bezpieczne HTTPS.
     */
    fun newCall(request: Request): Call {
        if (!request.isHttps) {
            throw IllegalArgumentException(
                "Nieszyfrowane połączenia HTTP są zabronione przez zasady bezpieczeństwa (wymagane HTTPS)."
            )
        }
        return okHttpClient.newCall(request)
    }

    /**
     * Synchroniczne wykonanie żądania z walidacją protokołu HTTPS.
     */
    fun execute(request: Request): Response {
        return newCall(request).execute()
    }

    /**
     * Własny TrustManager akceptujący wyłącznie certyfikat o identycznym odcisku SHA-256.
     */
    class FingerprintTrustManager(
        private val expectedHex: String
    ) : X509TrustManager {

        private val expectedBytes = hexToByteArray(expectedHex)

        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            // Aplikacja jest klientem, nie weryfikuje certyfikatów klienckich
        }

        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            if (chain.isNullOrEmpty()) {
                throw CertificateException("Brak certyfikatu serwera w trakcie negocjacji TLS.")
            }

            // Pierwszy certyfikat w łańcuchu to certyfikat serwera
            val leafCert = chain[0]
            val derBytes = leafCert.encoded
            val digest = MessageDigest.getInstance("SHA-256")
            val actualBytes = digest.digest(derBytes)

            // Stałoczasowe porównanie skrótów chroniące przed atakami czasowymi (timing attacks)
            if (!MessageDigest.isEqual(actualBytes, expectedBytes)) {
                val actualHex = actualBytes.joinToString("") { "%02x".format(it) }
                throw CertificateException(
                    "Odcisk certyfikatu serwera nie zgadza się! Oczekiwano: $expectedHex, otrzymano: $actualHex."
                )
            }
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()

        companion object {
            private fun hexToByteArray(hex: String): ByteArray {
                val result = ByteArray(hex.length / 2)
                for (i in 0 until hex.length step 2) {
                    result[i / 2] = hex.substring(i, i + 2).toInt(16).toByte()
                }
                return result
            }
        }
    }

    companion object {
        fun create(expectedFingerprintHex: String): OkHttpClient {
            return PinnedTlsClient(expectedFingerprintHex).okHttpClient
        }
    }
}
