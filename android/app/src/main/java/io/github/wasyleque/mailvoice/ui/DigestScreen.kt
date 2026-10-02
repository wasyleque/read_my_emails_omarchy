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
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.wasyleque.mailvoice.R
import io.github.wasyleque.mailvoice.net.DigestTopic
import io.github.wasyleque.mailvoice.net.TopicDigest

@Composable
fun DigestScreen(
    digest: TopicDigest?,
    days: Int,
    isLoading: Boolean,
    onPeriodSelected: (Int) -> Unit,
    onRefresh: () -> Unit,
    onListenTopic: (DigestTopic) -> Unit
) {
    var selectedGroupIndex by remember { mutableIntStateOf(0) }

    val allTopics = digest?.topics.orEmpty()
    val waitingMe = allTopics.filter { it.status == "oczekuje_na_mnie" }
    val waitingOthers = allTopics.filter { it.status == "oczekuje_na_innych" }
    val informational = allTopics.filter { it.status !in listOf("oczekuje_na_mnie", "oczekuje_na_innych") }

    val displayedTopics = when (selectedGroupIndex) {
        0 -> waitingMe
        1 -> waitingOthers
        else -> informational
    }

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
                text = { Text(stringResource(R.string.digest_group_me, waitingMe.size)) }
            )
            Tab(
                selected = selectedGroupIndex == 1,
                onClick = { selectedGroupIndex = 1 },
                text = { Text(stringResource(R.string.digest_group_others, waitingOthers.size)) }
            )
            Tab(
                selected = selectedGroupIndex == 2,
                onClick = { selectedGroupIndex = 2 },
                text = { Text(stringResource(R.string.digest_group_info, informational.size)) }
            )
        }

        if (displayedTopics.isEmpty() && !isLoading) {
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
