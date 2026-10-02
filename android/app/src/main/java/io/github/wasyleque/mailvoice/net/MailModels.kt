package io.github.wasyleque.mailvoice.net

/**
 * Model ważnej wiadomości e-mail zwracanej przez GET /v1/mails/important.
 * Wszystkie linki są zdefangowane ([link pominięty]), brak surowej treści.
 */
data class ImportantMail(
    val id: String,
    val sender: String,
    val subject: String,
    val importance: Int,
    val why: String,
    val summary: String?,
    val suspicious: Boolean,
    val date: String,
    val acknowledged: Boolean
)

/**
 * Model streszczenia pojedynczej wiadomości z GET /v1/mails/{id}/summary.
 */
data class MailSummaryResult(
    val id: String,
    val suspicious: Boolean,
    val warning: String?,
    val summary: String?
)

/**
 * Wynik potwierdzenia odsłuchania wiadomości z POST /v1/mails/{id}/ack.
 */
data class AckResult(
    val status: String,
    val message: String
)

/**
 * Pojedyncza sprawa / temat w podsumowaniu GET /v1/digest.
 */
data class DigestTopic(
    val title: String,
    val status: String, // "oczekuje_na_mnie", "oczekuje_na_innych", "informacyjne", "zamknięte"
    val why: String,
    val importance: Int,
    val mailCount: Int,
    val lastActivity: String,
    val whoToWhom: List<String>
)

/**
 * Zbiorcze podsumowanie tematów z GET /v1/digest.
 */
data class TopicDigest(
    val period: String,
    val topics: List<DigestTopic>
)

/**
 * Odpowiedź na komendę głosową z POST /v1/voice/command.
 */
data class VoiceCommandResponse(
    val action: String, // "next", "repeat", "skip", "stop", "yes", "no", "louder", "quieter", etc.
    val replyText: String
)

/**
 * Status serwera z GET /v1/status.
 */
data class ServerStatus(
    val version: String,
    val accountsCount: Int,
    val activeDevicesCount: Int,
    val lastTick: String? = null
)

/**
 * Generyczny wynik zapytania do API z obsługą błędów po ludzku.
 */
sealed interface ApiResult<out T> {
    data class Success<out T>(val data: T) : ApiResult<T>
    data class Error(
        val message: String,
        val isUnauthorized: Boolean = false,
        val isSecurityAlert: Boolean = false,
        val isNetworkError: Boolean = false,
        val httpCode: Int? = null
    ) : ApiResult<Nothing>
}
