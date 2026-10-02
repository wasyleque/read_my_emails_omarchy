package io.github.wasyleque.mailvoice.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.wasyleque.mailvoice.R
import io.github.wasyleque.mailvoice.net.DigestTopic

@Composable
fun DigestScreen(
    uiState: DigestUiState,
    days: Int,
    onPeriodSelected: (Int) -> Unit,
    onRefresh: () -> Unit,
    onListenTopic: (DigestTopic) -> Unit,
    onToggleShowAll: (Boolean) -> Unit = {}
) {
    var selectedGroupIndex by remember { mutableIntStateOf(0) }
    val isLoading = uiState is DigestUiState.Loading || (uiState is DigestUiState.Content && uiState.isRefreshing)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        // Górny pasek
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = stringResource(R.string.title_digest),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )

            IconButton(onClick = onRefresh, enabled = !isLoading) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                } else {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = stringResource(R.string.btn_refresh)
                    )
                }
            }
        }

        // Wybór okresu (Tydzień / Miesiąc)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(
                selected = days == 7,
                onClick = { onPeriodSelected(7) },
                label = { Text(stringResource(R.string.digest_week)) },
                modifier = Modifier.weight(1f)
            )
            FilterChip(
                selected = days == 30,
                onClick = { onPeriodSelected(30) },
                label = { Text(stringResource(R.string.digest_month)) },
                modifier = Modifier.weight(1f)
            )
        }

        when (uiState) {
            is DigestUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(48.dp), strokeWidth = 3.dp)
                        Text(
                            text = stringResource(R.string.status_preparing_digest),
                            style = MaterialTheme.typography.bodyLarge,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Text(
                            text = stringResource(R.string.status_preparing_digest_desc),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            is DigestUiState.Error -> {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 24.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Icon(
                            painter = painterResource(id = R.drawable.ic_warning),
                            contentDescription = null,
                            modifier = Modifier.size(44.dp),
                            tint = MaterialTheme.colorScheme.error
                        )
                        Text(
                            text = stringResource(R.string.error_loading_digest),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                        Text(
                            text = uiState.message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                        if (uiState.canRetry) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Button(
                                onClick = onRefresh,
                                modifier = Modifier.fillMaxWidth().height(48.dp)
                            ) {
                                Text(
                                    text = stringResource(R.string.btn_retry),
                                    style = MaterialTheme.typography.titleMedium
                                )
                            }
                        }
                    }
                }
            }
            is DigestUiState.Empty -> {
                // Pokazuj stan pusty WYŁĄCZNIE po udanym pobraniu (200 z pustą listą)
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 32.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            painter = painterResource(id = R.drawable.ic_digest),
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = stringResource(R.string.empty_digest),
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            is DigestUiState.Content -> {
                val allTopics = uiState.digest.topics
                val waitingMe = allTopics.filter { it.status == "oczekuje_na_mnie" }
                val waitingOthers = allTopics.filter { it.status == "oczekuje_na_innych" }
                val informational = allTopics.filter { it.status == "informacyjne" }
                val closed = allTopics.filter { it.status == "zamknięte" }

                val meCount = uiState.digest.counts["oczekuje_na_mnie"] ?: waitingMe.size
                val othersCount = uiState.digest.counts["oczekuje_na_innych"] ?: waitingOthers.size
                val infoCount = uiState.digest.counts["informacyjne"] ?: informational.size
                val closedCount = uiState.digest.counts["zamknięte"] ?: closed.size
                val extraCount = infoCount + closedCount

                // Baner błędu odświeżania (zachowuje starą listę)
                if (uiState.refreshError != null) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 10.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = uiState.refreshError,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                            TextButton(onClick = onRefresh) {
                                Text(stringResource(R.string.btn_retry))
                            }
                        }
                    }
                }

                // Nagłówek z licznikami: „Czeka na Ciebie: X · Czeka na innych: Y”
                Text(
                    text = stringResource(R.string.digest_counts_header_format, meCount, othersCount),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                // Nota, gdy shown < total: „Pokazano 100 z 467 tematów”
                if (uiState.digest.shown != null && uiState.digest.total != null && uiState.digest.shown < uiState.digest.total) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier.padding(bottom = 8.dp)
                    ) {
                        Text(
                            text = stringResource(R.string.digest_shown_total_format, uiState.digest.shown, uiState.digest.total),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                        )
                    }
                }

                // Przycisk lub przełącznik dla tematów zamkniętych i informacyjnych
                if (!uiState.showAll) {
                    if (extraCount > 0 || uiState.digest.counts.containsKey("zamknięte")) {
                        OutlinedButton(
                            onClick = { onToggleShowAll(true) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 10.dp)
                        ) {
                            Text(
                                text = stringResource(R.string.btn_show_closed_and_info_format, extraCount),
                                style = MaterialTheme.typography.labelMedium
                            )
                        }
                    }
                } else {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = stringResource(R.string.digest_toggle_closed_and_info),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Switch(
                            checked = true,
                            onCheckedChange = { onToggleShowAll(it) }
                        )
                    }
                }

                // Dopasowanie aktywnej zakładki przy przełączaniu
                val tabCount = if (uiState.showAll) 4 else 2
                if (selectedGroupIndex >= tabCount) {
                    selectedGroupIndex = 0
                }

                // Zakładki grup spraw
                TabRow(
                    selectedTabIndex = selectedGroupIndex,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp)
                ) {
                    Tab(
                        selected = selectedGroupIndex == 0,
                        onClick = { selectedGroupIndex = 0 },
                        text = { Text(stringResource(R.string.digest_group_me, meCount)) }
                    )
                    Tab(
                        selected = selectedGroupIndex == 1,
                        onClick = { selectedGroupIndex = 1 },
                        text = { Text(stringResource(R.string.digest_group_others, othersCount)) }
                    )
                    if (uiState.showAll) {
                        Tab(
                            selected = selectedGroupIndex == 2,
                            onClick = { selectedGroupIndex = 2 },
                            text = { Text(stringResource(R.string.digest_group_info, infoCount)) }
                        )
                        Tab(
                            selected = selectedGroupIndex == 3,
                            onClick = { selectedGroupIndex = 3 },
                            text = { Text(stringResource(R.string.digest_group_closed, closedCount)) }
                        )
                    }
                }

                val displayedTopics = when (selectedGroupIndex) {
                    0 -> waitingMe
                    1 -> waitingOthers
                    2 -> informational
                    3 -> closed
                    else -> waitingMe
                }

                if (displayedTopics.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = stringResource(R.string.empty_digest),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        items(displayedTopics) { topic ->
                            DigestTopicCard(topic = topic, onListen = { onListenTopic(topic) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DigestTopicCard(
    topic: DigestTopic,
    onListen: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = topic.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )

            if (topic.whoToWhom.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.topic_exchange_format, topic.whoToWhom.joinToString(", ")),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (topic.why.isNotBlank()) {
                Text(
                    text = stringResource(R.string.label_why_prefix) + topic.why,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.topic_mail_count_format, topic.mailCount),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                OutlinedButton(
                    onClick = onListen,
                    modifier = Modifier.height(40.dp)
                ) {
                    Icon(
                        painter = painterResource(id = R.drawable.ic_play),
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(stringResource(R.string.btn_listen_topic))
                }
            }
        }
    }
}
