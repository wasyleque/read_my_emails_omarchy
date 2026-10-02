package io.github.wasyleque.mailvoice.net

import io.github.wasyleque.mailvoice.security.TokenStore
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLException

/**
 * Klient API serwera MailVoice wykorzystujący PinnedTlsClient oraz autoryzację Bearer Token.
 * Zgodnie z SECURITY.md żaden token ani treść maila nie trafia do logów systemowych.
 */
class MailApi(
    private val tokenStore: TokenStore,
    private val clientFactory: (fingerprint: String) -> OkHttpClient = { fp ->
        PinnedTlsClient.create(fp)
    },
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO
) {

    /**
     * Pobiera listę ważnych wiadomości (GET /v1/mails/important?limit=...).
     */
    suspend fun getImportantMails(limit: Int = 20): ApiResult<List<ImportantMail>> =
        executeRequest(
            endpoint = "/v1/mails/important?limit=$limit",
            builder = Request.Builder().get()
        ) { bodyString ->
            val json = JSONObject(bodyString)
            val jsonArray = json.optJSONArray("mails") ?: JSONArray()
            val list = mutableListOf<ImportantMail>()
            for (i in 0 until jsonArray.length()) {
                val item = jsonArray.getJSONObject(i)
                list.add(
                    ImportantMail(
                        id = item.optString("id"),
                        sender = item.optString("sender"),
                        subject = item.optString("subject"),
                        importance = item.optInt("importance", 0),
                        why = item.optString("why"),
                        summary = if (item.isNull("summary")) null else item.optString("summary").ifBlank { null },
                        suspicious = item.optBoolean("suspicious", false),
                        date = item.optString("date"),
                        acknowledged = item.optBoolean("acknowledged", false)
                    )
                )
            }
            list
        }

    /**
     * Pobiera streszczenie pojedynczej wiadomości (GET /v1/mails/{id}/summary).
     */
    suspend fun getMailSummary(mailId: String): ApiResult<MailSummaryResult> =
        executeRequest(
            endpoint = "/v1/mails/$mailId/summary",
            builder = Request.Builder().get()
        ) { bodyString ->
            val json = JSONObject(bodyString)
            MailSummaryResult(
                id = json.optString("id", mailId),
                suspicious = json.optBoolean("suspicious", false),
                warning = if (json.isNull("warning")) null else json.optString("warning").ifBlank { null },
                summary = if (json.isNull("summary")) null else json.optString("summary").ifBlank { null }
            )
        }

    /**
     * Potwierdza odsłuchanie wiadomości (POST /v1/mails/{id}/ack).
     */
    suspend fun ackMail(mailId: String): ApiResult<AckResult> {
        val emptyBody = "{}".toRequestBody("application/json; charset=utf-8".toMediaType())
        return executeRequest(
            endpoint = "/v1/mails/$mailId/ack",
            builder = Request.Builder().post(emptyBody)
        ) { bodyString ->
            val json = JSONObject(bodyString)
            AckResult(
                status = json.optString("status", "ok"),
                message = json.optString("message", "Wiadomość oznaczona jako wysłuchana.")
            )
        }
    }

    /**
     * Ignoruje wiadomość i dodaje regułę na komputerze (POST /v1/mails/{id}/ignore).
     * @param mailId identyfikator wiadomości (24 znaki hex HMAC)
     * @param mode tryb ignorowania ("similar" | "sender" | "domain")
     */
    suspend fun ignoreMail(mailId: String, mode: String = "similar"): ApiResult<IgnoreResult> {
        val jsonPayload = JSONObject().apply {
            put("mode", mode)
        }.toString()
        val body = jsonPayload.toRequestBody("application/json; charset=utf-8".toMediaType())

        return executeRequest(
            endpoint = "/v1/mails/$mailId/ignore",
            builder = Request.Builder().post(body)
        ) { bodyString ->
            val json = JSONObject(bodyString)
            IgnoreResult(
                status = json.optString("status", "ok"),
                mode = json.optString("mode", mode),
                rule = json.optString("rule", "")
            )
        }
    }

    /**
     * Pobiera podsumowanie tematów (GET /v1/digest?days=...&limit=...[&all=1]).
     * Używa dedykowanego limitu czasu odczytu 30 sekund.
     */
    suspend fun getDigest(
        days: Int = 30,
        limit: Int = 60,
        all: Boolean = false
    ): ApiResult<TopicDigest> {
        val queryParams = buildString {
            append("days=").append(days)
            append("&limit=").append(limit)
            if (all) {
                append("&all=1")
            }
        }

        return executeRequest(
            endpoint = "/v1/digest?$queryParams",
            builder = Request.Builder().get(),
            readTimeoutMs = 30_000L
        ) { bodyString ->
            val json = JSONObject(bodyString)
            val period = json.optString("period", "ostatnie $days dni")
            val topicsArray = json.optJSONArray("topics") ?: JSONArray()
            val topicsList = mutableListOf<DigestTopic>()

            for (i in 0 until topicsArray.length()) {
                val item = topicsArray.getJSONObject(i)
                val whoArray = item.optJSONArray("who_to_whom") ?: JSONArray()
                val whoList = mutableListOf<String>()
                for (j in 0 until whoArray.length()) {
                    whoList.add(whoArray.getString(j))
                }

                topicsList.add(
                    DigestTopic(
                        title = item.optString("title"),
                        status = item.optString("status", "informacyjne"),
                        why = item.optString("why"),
                        importance = item.optInt("importance", 0),
                        mailCount = item.optInt("mail_count", 1),
                        lastActivity = item.optString("last_activity"),
                        whoToWhom = whoList
                    )
                )
            }

            val countsMap = mutableMapOf<String, Int>()
            val countsObj = json.optJSONObject("counts")
            if (countsObj != null) {
                val keys = countsObj.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    countsMap[key] = countsObj.optInt(key, 0)
                }
            }

            val total = if (json.has("total")) json.optInt("total") else null
            val shown = if (json.has("shown")) json.optInt("shown") else null

            TopicDigest(
                period = period,
                topics = topicsList,
                counts = countsMap,
                total = total,
                shown = shown
            )
        }
    }

    /**
     * Przesyła komendę głosową użytkownika do interpretacji przez serwer (POST /v1/voice/command).
     */
    suspend fun sendVoiceCommand(text: String, lang: String = "pl"): ApiResult<VoiceCommandResponse> {
        val jsonPayload = JSONObject().apply {
            put("text", text)
            put("lang", lang)
        }.toString()
        val body = jsonPayload.toRequestBody("application/json; charset=utf-8".toMediaType())

        return executeRequest(
            endpoint = "/v1/voice/command",
            builder = Request.Builder().post(body)
        ) { bodyString ->
            val json = JSONObject(bodyString)
            VoiceCommandResponse(
                action = json.optString("action", "unknown"),
                replyText = json.optString("reply_text", "")
            )
        }
    }

    /**
     * Sprawdza status serwera (GET /v1/status).
     */
    suspend fun getStatus(): ApiResult<ServerStatus> =
        executeRequest(
            endpoint = "/v1/status",
            builder = Request.Builder().get()
        ) { bodyString ->
            val json = JSONObject(bodyString)
            ServerStatus(
                version = json.optString("version", "nieznana"),
                accountsCount = json.optInt("accounts_count", 0),
                activeDevicesCount = json.optInt("active_devices_count", 0),
                lastTick = json.optString("last_tick").ifBlank { null }
            )
        }

    private suspend fun <T> executeRequest(
        endpoint: String,
        builder: Request.Builder,
        readTimeoutMs: Long? = null,
        parser: (String) -> T
    ): ApiResult<T> = withContext(ioDispatcher) {
        if (!tokenStore.isPaired()) {
            return@withContext ApiResult.Error(
                message = "Aplikacja nie jest sparowana z komputerem.",
                isUnauthorized = true
            )
        }

        val token = tokenStore.getToken() ?: return@withContext ApiResult.Error(
            message = "Brak zapisanego tokenu autoryzacyjnego.",
            isUnauthorized = true
        )
        val fingerprint = tokenStore.getServerFingerprint() ?: return@withContext ApiResult.Error(
            message = "Brak odcisku certyfikatu serwera.",
            isUnauthorized = true
        )
        val host = tokenStore.getServerHost() ?: return@withContext ApiResult.Error(
            message = "Brak adresu serwera.",
            isUnauthorized = true
        )
        val port = tokenStore.getServerPort()

        val baseClient = try {
            clientFactory(fingerprint)
        } catch (e: Exception) {
            return@withContext ApiResult.Error(
                message = "Błąd inicjalizacji klienta TLS: ${e.localizedMessage ?: "brak szczegółów"}",
                isSecurityAlert = true
            )
        }

        val client = if (readTimeoutMs != null) {
            baseClient.newBuilder()
                .readTimeout(readTimeoutMs, java.util.concurrent.TimeUnit.MILLISECONDS)
                .build()
        } else {
            baseClient
        }

        val request = builder
            .url("https://$host:$port$endpoint")
            .header("Authorization", "Bearer $token")
            .build()

        try {
            client.newCall(request).execute().use { response ->
                when (response.code) {
                    200 -> {
                        val body = response.body?.string().orEmpty()
                        try {
                            ApiResult.Success(parser(body))
                        } catch (e: Exception) {
                            ApiResult.Error("Błąd przetwarzania odpowiedzi serwera.")
                        }
                    }
                    400 -> {
                        val errorDetail = parseErrorMessage(response.body?.string())
                        ApiResult.Error(
                            message = errorDetail ?: "Niepoprawne żądanie (kod 400).",
                            httpCode = 400
                        )
                    }
                    401 -> {
                        tokenStore.clear()
                        ApiResult.Error(
                            message = "Komputer odrzucił telefon — sparuj ponownie.",
                            isUnauthorized = true,
                            httpCode = 401
                        )
                    }
                    403 -> {
                        val errorDetail = parseErrorMessage(response.body?.string())
                        ApiResult.Error(
                            message = errorDetail ?: "Brak uprawnień do wykonania operacji (kod 403).",
                            httpCode = 403
                        )
                    }
                    404 -> {
                        val errorDetail = parseErrorMessage(response.body?.string())
                        ApiResult.Error(
                            message = errorDetail ?: "Wiadomość nie została odnaleziona na komputerze (kod 404).",
                            httpCode = 404
                        )
                    }
                    429 -> ApiResult.Error("Zbyt wiele zapytań, spróbuj za chwilę.", httpCode = 429)
                    500 -> ApiResult.Error("Błąd serwera na komputerze.", httpCode = 500)
                    503 -> {
                        val errorDetail = parseErrorMessage(response.body?.string())
                        ApiResult.Error(
                            message = errorDetail ?: "Funkcja ignorowania jest obecnie niedostępna na komputerze (kod 503).",
                            httpCode = 503
                        )
                    }
                    else -> {
                        val errorDetail = parseErrorMessage(response.body?.string())
                        ApiResult.Error(
                            message = errorDetail ?: "Serwer zwrócił nieoczekiwany kod błędu (${response.code}).",
                            httpCode = response.code
                        )
                    }
                }
            }
        } catch (e: SSLHandshakeException) {
            ApiResult.Error(
                message = "Certyfikat komputera się zmienił lub nie pasuje do odcisku. Ze względów bezpieczeństwa połączenie zostało zablokowane. Sparuj telefon ponownie.",
                isSecurityAlert = true
            )
        } catch (e: SSLException) {
            ApiResult.Error(
                message = "Błąd szyfrowania TLS: ${e.localizedMessage ?: "brak szczegółów"}",
                isSecurityAlert = true
            )
        } catch (e: ConnectException) {
            ApiResult.Error(
                message = "Brak połączenia z komputerem.",
                isNetworkError = true
            )
        } catch (e: UnknownHostException) {
            ApiResult.Error(
                message = "Nie znaleziono adresu komputera ($host).",
                isNetworkError = true
            )
        } catch (e: SocketTimeoutException) {
            ApiResult.Error(
                message = "Komputer nie odpowiedział na czas.",
                isNetworkError = true
            )
        } catch (e: IOException) {
            ApiResult.Error(
                message = "Błąd połączenia z komputerem: ${e.localizedMessage ?: "brak szczegółów"}",
                isNetworkError = true
            )
        }
    }

    private fun parseErrorMessage(body: String?): String? {
        if (body.isNullOrBlank()) return null
        return try {
            val json = JSONObject(body)
            val error = json.optString("error").ifBlank {
                json.optString("detail").ifBlank { null }
            }
            error
        } catch (_: Exception) {
            null
        }
    }
}
