package io.github.wasyleque.mailvoice.background

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import io.github.wasyleque.mailvoice.MainActivity

/** Kanały i budowanie powiadomień. Na ekranie blokady pokazujemy tylko wersję publiczną (bez danych). */
object NotificationHelper {
    const val CHANNEL_SERVICE = "mailvoice_service"
    const val CHANNEL_IMPORTANT = "mailvoice_important"
    const val CHANNEL_SUSPICIOUS = "mailvoice_suspicious"
    const val EXTRA_MAIL_ID = "mail_id"
    const val FOREGROUND_ID = 1
    const val REMINDER_ID = 2
    const val FATAL_ID = 3

    fun ensureChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_SERVICE, "Połączenie z komputerem", NotificationManager.IMPORTANCE_MIN).apply {
                description = "Stałe powiadomienie, dzięki któremu telefon może odbierać ważne maile."
                setShowBadge(false)
            },
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_IMPORTANT, "Ważne maile", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Powiadomienia o ważnych mailach."
            },
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_SUSPICIOUS, "Podejrzane wiadomości", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Ostrzeżenia o wiadomościach wyglądających na phishing."
            },
        )
    }

    private fun openApp(context: Context, mailId: String?): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            mailId?.let { putExtra(EXTRA_MAIL_ID, it) }
        }
        return PendingIntent.getActivity(
            context,
            mailId?.hashCode() ?: 0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    fun serviceNotification(context: Context, status: String): Notification =
        NotificationCompat.Builder(context, CHANNEL_SERVICE)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle("MailVoice")
            .setContentText(status)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .setContentIntent(openApp(context, null))
            .build()

    fun post(context: Context, id: Int, text: NotificationText, channel: String, mailId: String?) {
        val manager = NotificationManagerCompat.from(context)
        if (!manager.areNotificationsEnabled()) return // brak zgody: usługa działa dalej, ale cicho
        val public = NotificationCompat.Builder(context, channel)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle(text.publicText)
            .build()
        val notification = NotificationCompat.Builder(context, channel)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle(text.title)
            .setContentText(text.text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text.text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(public)
            .setContentIntent(openApp(context, mailId))
            .build()
        @Suppress("MissingPermission") // sprawdzone wyżej przez areNotificationsEnabled()
        manager.notify(id, notification)
    }
}
