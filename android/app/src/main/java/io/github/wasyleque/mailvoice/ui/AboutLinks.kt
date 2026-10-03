package io.github.wasyleque.mailvoice.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri

/**
 * Stałe odnośniki projektu (autor, GitHub, darowizna). To JEDYNE miejsce w aplikacji, które otwiera
 * odnośnik, i tylko jeden z poniższych adresów po sprawdzeniu białej listy. Adresy z maili nigdy tu nie
 * trafiają (aplikacja nie wyświetla ich ani nie otwiera — patrz UrlSanitizer).
 */
object AboutLinks {
    const val AUTHOR = "wasyleque"
    const val PROJECT_URL = "https://github.com/wasyleque/read_my_emails_omarchy"
    const val DONATE_URL =
        "https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=wasyl%40o2.pl" +
            "&currency_code=PLN&item_name=MailVoice"

    private val allowed = setOf(PROJECT_URL, DONATE_URL)

    /** Czy adres jest jednym ze stałych, zaufanych adresów projektu. */
    fun isAllowed(url: String): Boolean = url in allowed

    /** Otwiera adres w przeglądarce; zwraca false, gdy adres nie jest na białej liście albo brak przeglądarki. */
    fun open(context: Context, url: String): Boolean {
        if (!isAllowed(url)) return false
        return try {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
            true
        } catch (e: ActivityNotFoundException) {
            false
        }
    }
}
