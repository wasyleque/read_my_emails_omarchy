package io.github.wasyleque.mailvoice.background

/** Treść powiadomienia: pełna (po odblokowaniu) i publiczna (na ekranie blokady — bez danych). */
data class NotificationText(val title: String, val text: String, val publicText: String)

/**
 * Buduje treść powiadomień. Zasady prywatności: na zablokowanym ekranie pokazujemy tylko liczbę,
 * a w pełnej treści nigdy adresu URL ani tematu maila podejrzanego (temat phishingu bywa pułapką).
 */
object NotificationContent {
    private val url = Regex("""(?i)\b((https?|ftp)://|www\.)\S+|\b[a-z0-9-]+(\.[a-z0-9-]+)+\.[a-z]{2,}/\S*""")

    fun stripUrls(text: String): String = url.replace(text, "[link pominięty]")

    /** Samo imię/nazwa nadawcy z „Nazwa <adres>”; bez adresu, jeśli jest nazwa. */
    fun senderName(raw: String): String {
        val name = raw.substringBefore('<').trim().trim('"')
        return stripUrls(if (name.isNotEmpty()) name else raw.trim('<', '>', ' '))
    }

    private fun clip(s: String, max: Int = 80) = if (s.length <= max) s else s.take(max - 1) + "…"

    fun forNewImportant(mails: List<MailBrief>): NotificationText {
        val publicText = if (mails.size == 1) "Ważny mail" else "Ważne maile: ${mails.size}"
        val first = mails.first()
        return if (mails.size == 1) {
            NotificationText(
                title = "Ważny mail: ${clip(senderName(first.sender), 40)}",
                text = clip(stripUrls(first.subject.ifBlank { first.why })),
                publicText = publicText,
            )
        } else {
            NotificationText(
                title = "Ważne maile: ${mails.size}",
                text = clip(mails.joinToString(", ") { senderName(it.sender) }),
                publicText = publicText,
            )
        }
    }

    fun forSuspicious(mail: MailBrief): NotificationText = NotificationText(
        title = "⚠ Podejrzana wiadomość",
        text = "Od: ${clip(senderName(mail.sender), 40)}. Nie otwieraj linków ani załączników.",
        publicText = "Podejrzana wiadomość",
    )

    fun forReminder(count: Int, ask: Boolean): NotificationText {
        val what = if (count == 1) "1 ważny mail czeka" else "Ważne maile czekają: $count"
        return NotificationText(
            title = what,
            text = if (ask) "Czy masz teraz czas ich wysłuchać? Otwórz aplikację." else "Otwórz aplikację, aby je przejrzeć.",
            publicText = what,
        )
    }
}
