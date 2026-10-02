package io.github.wasyleque.mailvoice.background

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import io.github.wasyleque.mailvoice.security.KeystoreTokenStore

/** Po restarcie telefonu wznawia nasłuch, jeśli telefon jest sparowany i powiadomienia są włączone. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (KeystoreTokenStore(context.applicationContext).isPaired() && BackgroundController.isEnabled(context)) {
            BackgroundController.start(context)
        }
    }
}
