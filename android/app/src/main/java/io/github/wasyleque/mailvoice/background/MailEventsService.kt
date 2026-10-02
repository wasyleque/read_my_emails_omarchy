package io.github.wasyleque.mailvoice.background

import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import io.github.wasyleque.mailvoice.security.KeystoreTokenStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Usługa pierwszoplanowa utrzymująca połączenie z komputerem i zamieniająca zdarzenia na
 * powiadomienia. Nie używa serwerów Google (FCM): treść wiadomości nigdy nie opuszcza Twojej sieci.
 */
class MailEventsService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        NotificationHelper.ensureChannels(this)
        showForeground("Łączę z komputerem…")
        if (job?.isActive != true) job = scope.launch { loop() }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private fun showForeground(status: String) {
        val notification = NotificationHelper.serviceNotification(this, status)
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, NotificationHelper.FOREGROUND_ID, notification, type)
    }

    private suspend fun loop() {
        val policy = ReconnectPolicy()
        while (scope.isActive) {
            val store = KeystoreTokenStore(applicationContext)
            val token = store.getToken()
            val host = store.getServerHost()
            val fingerprint = store.getServerFingerprint()
            if (!store.isPaired() || token == null || host == null || fingerprint == null) {
                stopSelf()
                return
            }
            val outcome = EventsClient(host, store.getServerPort(), token, fingerprint).runOnce(
                onConnected = {
                    policy.reset()
                    showForeground("Połączono z komputerem")
                },
                onEvent = ::handle,
            )
            outcome.fatal?.let {
                onFatal(it)
                return
            }
            showForeground("Łączę ponownie…")
            delay(policy.nextDelayMs())
        }
    }

    private fun handle(event: ServerEvent) {
        when (event) {
            is ServerEvent.NewImportant -> NotificationHelper.post(
                this,
                event.mails.first().id.hashCode(),
                NotificationContent.forNewImportant(event.mails),
                NotificationHelper.CHANNEL_IMPORTANT,
                event.mails.first().id,
            )
            is ServerEvent.Suspicious -> NotificationHelper.post(
                this,
                event.mail.id.hashCode(),
                NotificationContent.forSuspicious(event.mail),
                NotificationHelper.CHANNEL_SUSPICIOUS,
                event.mail.id,
            )
            is ServerEvent.BeepReminder -> reminder(event.count, ask = false)
            is ServerEvent.AskReminder -> reminder(event.count, ask = true)
        }
    }

    private fun reminder(count: Int, ask: Boolean) = NotificationHelper.post(
        this,
        NotificationHelper.REMINDER_ID,
        NotificationContent.forReminder(count, ask),
        NotificationHelper.CHANNEL_IMPORTANT,
        null,
    )

    private fun onFatal(reason: FatalReason) {
        val text = when (reason) {
            FatalReason.UNAUTHORIZED -> "Komputer odrzucił ten telefon (odłączony?). Sparuj go ponownie."
            FatalReason.CERTIFICATE_CHANGED -> "Certyfikat komputera się zmienił. Sparuj telefon ponownie."
        }
        NotificationHelper.post(
            this,
            NotificationHelper.FATAL_ID,
            NotificationText("Wymagane ponowne parowanie", text, "Wymagane ponowne parowanie"),
            NotificationHelper.CHANNEL_IMPORTANT,
            null,
        )
        NotificationManagerCompat.from(this).cancel(NotificationHelper.FOREGROUND_ID)
        stopSelf()
    }
}
