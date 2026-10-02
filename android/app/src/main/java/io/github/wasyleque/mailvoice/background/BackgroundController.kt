package io.github.wasyleque.mailvoice.background

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/** Włączanie i wyłączanie powiadomień w tle (preferencja użytkownika + start usługi). */
object BackgroundController {
    private const val PREFS = "mailvoice_prefs"
    private const val KEY_ENABLED = "background_enabled"

    /** Domyślnie włączone po sparowaniu; użytkownik może wyłączyć w ustawieniach. */
    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ENABLED, true)

    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, enabled).apply()
        if (enabled) start(context) else stop(context)
    }

    fun start(context: Context) {
        ContextCompat.startForegroundService(context, Intent(context, MailEventsService::class.java))
    }

    fun stop(context: Context) {
        context.stopService(Intent(context, MailEventsService::class.java))
    }
}
