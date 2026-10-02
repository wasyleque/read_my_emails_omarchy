package io.github.wasyleque.mailvoice.background

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** Krótki opis maila ze zdarzenia serwera (bez treści — serwer nigdy jej nie wysyła). */
data class MailBrief(
    val id: String,
    val sender: String,
    val subject: String,
    val importance: Int,
    val why: String,
    val suspicious: Boolean,
)

/** Zdarzenia strumienia /v1/events (patrz docs/mobile-api.md). */
sealed interface ServerEvent {
    data class NewImportant(val mails: List<MailBrief>) : ServerEvent
    data class Suspicious(val mail: MailBrief, val reasons: List<String>) : ServerEvent
    data class BeepReminder(val count: Int) : ServerEvent
    data class AskReminder(val count: Int) : ServerEvent
}

/** Odporny parser: zła lub nieznana wiadomość daje `null`, nigdy wyjątek (dane z sieci są niezaufane). */
object EventParser {
    fun parse(json: String): ServerEvent? = try {
        val root = JSONObject(json)
        val data = root.optJSONObject("data")
        when (root.optString("type")) {
            "NewImportant" -> {
                val list = data?.optJSONArray("mails") ?: JSONArray()
                val mails = (0 until list.length()).mapNotNull { list.optJSONObject(it)?.let(::brief) }
                if (mails.isEmpty()) null else ServerEvent.NewImportant(mails)
            }
            "SuspiciousMail" -> {
                val mail = data?.optJSONObject("mail")?.let(::brief)
                val reasons = data?.optJSONArray("reasons")?.let { arr ->
                    (0 until arr.length()).map { arr.optString(it) }
                } ?: emptyList()
                mail?.let { ServerEvent.Suspicious(it.copy(suspicious = true), reasons) }
            }
            "BeepReminder" -> ServerEvent.BeepReminder(data?.optInt("count", 0) ?: 0)
            "AskReminder" -> ServerEvent.AskReminder(data?.optInt("count", 0) ?: 0)
            else -> null
        }
    } catch (_: JSONException) {
        null
    }

    private fun brief(o: JSONObject): MailBrief? {
        val id = o.optString("id")
        if (id.isBlank()) return null
        return MailBrief(
            id = id,
            sender = o.optString("sender"),
            subject = o.optString("subject"),
            importance = o.optInt("importance", 0),
            why = o.optString("why"),
            suspicious = o.optBoolean("suspicious", false),
        )
    }
}
