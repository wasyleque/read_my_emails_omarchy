package io.github.wasyleque.mailvoice.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.wasyleque.mailvoice.R
import io.github.wasyleque.mailvoice.net.IgnoreMode
import io.github.wasyleque.mailvoice.net.ImportantMail

enum class RuleDialogKind {
    IGNORE,
    VIP
}

@Composable
fun MailRuleDialog(
    kind: RuleDialogKind,
    mail: ImportantMail,
    isSubmitting: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onConfirm: (mode: IgnoreMode) -> Unit
) {
    var selectedMode by remember { mutableStateOf(IgnoreMode.SIMILAR) }

    AlertDialog(
        onDismissRequest = {
            if (!isSubmitting) onDismiss()
        },
        shape = RoundedCornerShape(20.dp),
        title = {
            Text(
                text = stringResource(
                    if (kind == RuleDialogKind.VIP) R.string.vip_dialog_title else R.string.ignore_dialog_title
                ),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = "${mail.sender}: ${mail.subject}",
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                Text(
                    text = stringResource(
                        if (kind == RuleDialogKind.VIP) R.string.vip_dialog_question else R.string.ignore_dialog_desc
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // Opcja 1: Podobne maile (domyślna)
                RuleOptionRow(
                    text = stringResource(
                        if (kind == RuleDialogKind.VIP) R.string.vip_mode_similar else R.string.ignore_mode_similar
                    ),
                    selected = selectedMode == IgnoreMode.SIMILAR,
                    enabled = !isSubmitting,
                    onSelect = { selectedMode = IgnoreMode.SIMILAR }
                )

                // Opcja 2: Wszystkie od tego nadawcy
                RuleOptionRow(
                    text = stringResource(
                        if (kind == RuleDialogKind.VIP) R.string.vip_mode_sender else R.string.ignore_mode_sender
                    ),
                    selected = selectedMode == IgnoreMode.SENDER,
                    enabled = !isSubmitting,
                    onSelect = { selectedMode = IgnoreMode.SENDER }
                )

                // Opcja 3: Cała domena firmy
                RuleOptionRow(
                    text = stringResource(
                        if (kind == RuleDialogKind.VIP) R.string.vip_mode_domain else R.string.ignore_mode_domain
                    ),
                    selected = selectedMode == IgnoreMode.DOMAIN,
                    enabled = !isSubmitting,
                    onSelect = { selectedMode = IgnoreMode.DOMAIN }
                )

                if (kind == RuleDialogKind.VIP) {
                    Text(
                        text = stringResource(R.string.vip_dialog_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                if (errorMessage != null) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = errorMessage,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        fontWeight = FontWeight.Medium
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(selectedMode) },
                enabled = !isSubmitting,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (kind == RuleDialogKind.VIP) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.error
                    }
                )
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = if (kind == RuleDialogKind.VIP) {
                            MaterialTheme.colorScheme.onPrimary
                        } else {
                            MaterialTheme.colorScheme.onError
                        },
                        strokeWidth = 2.dp
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        stringResource(
                            if (kind == RuleDialogKind.VIP) R.string.status_marking_vip else R.string.status_ignoring
                        )
                    )
                } else {
                    Text(
                        stringResource(
                            if (kind == RuleDialogKind.VIP) R.string.btn_confirm_vip else R.string.btn_confirm_ignore
                        )
                    )
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSubmitting
            ) {
                Text(stringResource(R.string.btn_cancel))
            }
        }
    )
}

@Composable
fun IgnoreMailDialog(
    mail: ImportantMail,
    isSubmitting: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onConfirm: (mode: IgnoreMode) -> Unit
) {
    MailRuleDialog(
        kind = RuleDialogKind.IGNORE,
        mail = mail,
        isSubmitting = isSubmitting,
        errorMessage = errorMessage,
        onDismiss = onDismiss,
        onConfirm = onConfirm
    )
}

@Composable
fun VipMailDialog(
    mail: ImportantMail,
    isSubmitting: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onConfirm: (mode: IgnoreMode) -> Unit
) {
    MailRuleDialog(
        kind = RuleDialogKind.VIP,
        mail = mail,
        isSubmitting = isSubmitting,
        errorMessage = errorMessage,
        onDismiss = onDismiss,
        onConfirm = onConfirm
    )
}

@Composable
private fun RuleOptionRow(
    text: String,
    selected: Boolean,
    enabled: Boolean,
    onSelect: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .selectable(
                selected = selected,
                enabled = enabled,
                onClick = onSelect
            )
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(
            selected = selected,
            onClick = if (enabled) onSelect else null,
            enabled = enabled
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f)
        )
    }
}
