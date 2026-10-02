package io.github.wasyleque.mailvoice.background

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import io.github.wasyleque.mailvoice.R

private fun notificationsAllowed(context: Context): Boolean =
    NotificationManagerCompat.from(context).areNotificationsEnabled()

private fun needsRuntimeNotificationPermission(context: Context): Boolean =
    Build.VERSION.SDK_INT >= 33 &&
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED

/** Po sparowaniu: prosi (raz) o zgodę na powiadomienia i uruchamia nasłuch w tle. */
@Composable
fun BackgroundBootstrap() {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        if (BackgroundController.isEnabled(context)) BackgroundController.start(context)
    }
    LaunchedEffect(Unit) {
        if (!BackgroundController.isEnabled(context)) return@LaunchedEffect
        if (needsRuntimeNotificationPermission(context)) {
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            BackgroundController.start(context)
        }
    }
}

/** Karta w Ustawieniach: przełącznik powiadomień w tle i pomoc z ustawieniami baterii/autostartu. */
@Composable
fun BackgroundSettingsCard() {
    val context = LocalContext.current
    var enabled by remember { mutableStateOf(BackgroundController.isEnabled(context)) }
    var notifications by remember { mutableStateOf(notificationsAllowed(context)) }
    var batteryFree by remember { mutableStateOf(BatterySettings.isIgnoringBatteryOptimizations(context)) }

    // Po powrocie z ustawień systemowych odśwież stan.
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                notifications = notificationsAllowed(context)
                batteryFree = BatterySettings.isIgnoringBatteryOptimizations(context)
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        notifications = notificationsAllowed(context)
    }

    fun open(intent: android.content.Intent) {
        try {
            context.startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            // brak takiego ekranu na tym telefonie — użytkownik zrobi to ręcznie w ustawieniach systemu
        }
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(stringResource(R.string.bg_title), style = MaterialTheme.typography.titleMedium)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.bg_switch), modifier = Modifier.weight(1f))
                Switch(checked = enabled, onCheckedChange = {
                    enabled = it
                    BackgroundController.setEnabled(context, it)
                    if (it && needsRuntimeNotificationPermission(context)) {
                        permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                })
            }
            Text(
                stringResource(if (notifications) R.string.bg_notif_ok else R.string.bg_notif_off),
                style = MaterialTheme.typography.bodyMedium,
            )
            if (!notifications) {
                OutlinedButton(onClick = {
                    if (needsRuntimeNotificationPermission(context)) {
                        permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        open(android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                            .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, context.packageName))
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.bg_allow_notif)) }
            }
            Text(
                stringResource(if (batteryFree) R.string.bg_battery_ok else R.string.bg_battery_limited),
                style = MaterialTheme.typography.bodyMedium,
            )
            if (!batteryFree) {
                Button(onClick = { open(BatterySettings.requestIgnoreOptimizationsIntent(context)) },
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.bg_allow_battery)) }
            }
            if (BatterySettings.isXiaomiFamily()) {
                Text(stringResource(R.string.bg_xiaomi_hint), style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = { open(BatterySettings.autostartIntent(context)) },
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.bg_open_autostart)) }
            }
        }
    }
}
