package io.github.wasyleque.mailvoice.background

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings

/**
 * Pomocnik ustawień systemowych potrzebnych, by powiadomienia w tle były niezawodne. Xiaomi/HyperOS
 * (Poco, Redmi) agresywnie usypia aplikacje: potrzebny jest autostart i tryb baterii „bez ograniczeń”.
 */
object BatterySettings {
    fun isIgnoringBatteryOptimizations(context: Context): Boolean =
        context.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(context.packageName)

    /** Systemowe okno „Zezwolić na pracę w tle bez ograniczeń?”. */
    fun requestIgnoreOptimizationsIntent(context: Context): Intent =
        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))

    fun isXiaomiFamily(): Boolean {
        val m = Build.MANUFACTURER.lowercase()
        val b = Build.BRAND.lowercase()
        return m == "xiaomi" || b == "xiaomi" || b == "poco" || b == "redmi"
    }

    /** Ekran autostartu MIUI/HyperOS; gdy go nie ma — szczegóły aplikacji w ustawieniach systemu. */
    fun autostartIntent(context: Context): Intent {
        val miui = Intent().setComponent(
            ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
        )
        return if (miui.resolveActivity(context.packageManager) != null) {
            miui
        } else {
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))
        }
    }
}
