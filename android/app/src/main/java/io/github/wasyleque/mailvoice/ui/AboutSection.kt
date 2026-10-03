package io.github.wasyleque.mailvoice.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.wasyleque.mailvoice.R

/** Stopka ekranu ustawień: autor, link do projektu na GitHubie i przycisk wsparcia. */
@Composable
fun AboutSection() {
    val context = LocalContext.current
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(
            text = stringResource(R.string.about_created_by, AboutLinks.AUTHOR),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        TextButton(onClick = { AboutLinks.open(context, AboutLinks.PROJECT_URL) }) {
            Text(stringResource(R.string.about_project_github))
        }
        OutlinedButton(onClick = { AboutLinks.open(context, AboutLinks.DONATE_URL) }) {
            Text(stringResource(R.string.btn_donate))
        }
    }
}
