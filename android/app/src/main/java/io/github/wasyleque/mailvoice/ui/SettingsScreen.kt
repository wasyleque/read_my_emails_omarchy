package io.github.wasyleque.mailvoice.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.wasyleque.mailvoice.R
import io.github.wasyleque.mailvoice.net.ServerStatus

@Composable
fun SettingsScreen(
    status: ServerStatus?,
    host: String,
    port: Int,
    isLoading: Boolean,
    selectedLanguage: String,
    showDisconnectDialog: Boolean,
    onRefresh: () -> Unit,
    onLanguageSelected: (String) -> Unit,
    onRequestDisconnect: () -> Unit,
    onDismissDisconnectDialog: () -> Unit,
    onConfirmDisconnect: () -> Unit
) {
    val scrollState = rememberScrollState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(horizontal = 16.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Text(
            text = stringResource(R.string.title_settings),
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
        )

        // Karta stanu połączenia z serwerem
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    text = stringResource(R.string.settings_server_title),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Text(
                    text = stringResource(R.string.server_address_format, host, port),
                    style = MaterialTheme.typography.bodyLarge
                )

                Text(
                    text = stringResource(R.string.server_version_format, status?.version ?: "..."),
                    style = MaterialTheme.typography.bodyLarge
                )

                Text(
                    text = stringResource(R.string.accounts_count_format, status?.accountsCount ?: 0),
                    style = MaterialTheme.typography.bodyLarge
                )

                Text(
                    text = stringResource(R.string.devices_count_format, status?.activeDevicesCount ?: 1),
                    style = MaterialTheme.typography.bodyLarge
                )

                Spacer(modifier = Modifier.height(4.dp))

                Button(
                    onClick = onRefresh,
                    enabled = !isLoading,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    if (isLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(stringResource(R.string.status_refreshing))
                    } else {
                        Text(stringResource(R.string.btn_check_connection))
                    }
                }
            }
        }

        // Karta wyboru języka głosu
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    text = stringResource(R.string.settings_voice_title),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectable(
                            selected = selectedLanguage == "pl",
                            onClick = { onLanguageSelected("pl") }
                        ),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = selectedLanguage == "pl",
                        onClick = { onLanguageSelected("pl") }
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = stringResource(R.string.lang_pl),
                        style = MaterialTheme.typography.bodyLarge
                    )
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectable(
                            selected = selectedLanguage == "en",
                            onClick = { onLanguageSelected("en") }
                        ),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = selectedLanguage == "en",
                        onClick = { onLanguageSelected("en") }
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = stringResource(R.string.lang_en),
                        style = MaterialTheme.typography.bodyLarge
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        io.github.wasyleque.mailvoice.background.BackgroundSettingsCard()

        Spacer(modifier = Modifier.height(10.dp))

        // Przycisk odłączenia telefonu
        OutlinedButton(
            onClick = onRequestDisconnect,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = MaterialTheme.colorScheme.error
            )
        ) {
            Text(
                text = stringResource(R.string.btn_disconnect),
                style = MaterialTheme.typography.titleMedium
            )
        }

        AboutSection()
    }

    if (showDisconnectDialog) {
        AlertDialog(
            onDismissRequest = onDismissDisconnectDialog,
            title = {
                Text(
                    text = stringResource(R.string.disconnect_dialog_title),
                    style = MaterialTheme.typography.titleMedium
                )
            },
            text = {
                Text(
                    text = stringResource(R.string.disconnect_dialog_desc),
                    style = MaterialTheme.typography.bodyMedium
                )
            },
            confirmButton = {
                Button(
                    onClick = onConfirmDisconnect,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text(stringResource(R.string.btn_disconnect))
                }
            },
            dismissButton = {
                TextButton(onClick = onDismissDisconnectDialog) {
                    Text(stringResource(R.string.btn_cancel))
                }
            }
        )
    }
}
