package io.github.wasyleque.mailvoice.ui

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import io.github.wasyleque.mailvoice.R
import io.github.wasyleque.mailvoice.voice.VoiceSessionState

@Composable
fun VoiceSessionDialog(
    state: VoiceSessionState,
    onNext: () -> Unit,
    onRepeat: () -> Unit,
    onSkip: () -> Unit,
    onStop: () -> Unit,
    onRequestMicPermission: () -> Unit,
    hasMicPermission: Boolean
) {
    if (state is VoiceSessionState.Idle) return

    Dialog(onDismissRequest = onStop) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Nagłówek okna
                Text(
                    text = stringResource(R.string.voice_session_title),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )

                when (state) {
                    is VoiceSessionState.ReadingMail -> {
                        MailHeaderInfo(
                            sender = state.mail.sender,
                            subject = state.mail.subject,
                            index = state.currentIndex + 1,
                            total = state.totalCount
                        )
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_play,
                            label = stringResource(R.string.voice_reading),
                            color = MaterialTheme.colorScheme.primary,
                            isPulsing = true
                        )
                    }

                    is VoiceSessionState.AskingPrompt -> {
                        MailHeaderInfo(
                            sender = state.mail.sender,
                            subject = state.mail.subject,
                            index = state.currentIndex + 1,
                            total = state.totalCount
                        )
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_play,
                            label = state.promptText,
                            color = MaterialTheme.colorScheme.tertiary,
                            isPulsing = false
                        )
                    }

                    is VoiceSessionState.Listening -> {
                        MailHeaderInfo(
                            sender = state.mail.sender,
                            subject = state.mail.subject,
                            index = state.currentIndex + 1,
                            total = state.totalCount
                        )
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_mic,
                            label = if (hasMicPermission) {
                                stringResource(R.string.voice_listening)
                            } else {
                                stringResource(R.string.mic_rationale_desc)
                            },
                            color = Color(0xFFE91E63),
                            isPulsing = hasMicPermission
                        )
                        if (!hasMicPermission) {
                            Button(
                                onClick = onRequestMicPermission,
                                modifier = Modifier.padding(top = 8.dp)
                            ) {
                                Text(stringResource(R.string.btn_grant_mic))
                            }
                        }
                    }

                    is VoiceSessionState.ProcessingCommand -> {
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_settings,
                            label = "Przetwarzam komendę: „${state.recognizedText}”...",
                            color = MaterialTheme.colorScheme.secondary,
                            isPulsing = false
                        )
                    }

                    is VoiceSessionState.SpeakingFeedback -> {
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_play,
                            label = state.feedbackText,
                            color = MaterialTheme.colorScheme.tertiary,
                            isPulsing = false
                        )
                    }

                    is VoiceSessionState.Finished -> {
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_check,
                            label = state.message,
                            color = Color(0xFF2E7D32),
                            isPulsing = false
                        )
                    }

                    is VoiceSessionState.Error -> {
                        AudioStateIndicator(
                            iconRes = R.drawable.ic_warning,
                            label = state.message,
                            color = MaterialTheme.colorScheme.error,
                            isPulsing = false
                        )
                    }

                    else -> {}
                }

                // Przyciski sterowania dotykowego (alternatywa dla sterowania głosem)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onRepeat,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(stringResource(R.string.btn_repeat_mail))
                    }
                    OutlinedButton(
                        onClick = onSkip,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(stringResource(R.string.btn_skip_mail))
                    }
                    Button(
                        onClick = onNext,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(stringResource(R.string.btn_next_mail))
                    }
                }

                Button(
                    onClick = onStop,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text(stringResource(R.string.btn_stop_session))
                }
            }
        }
    }
}

@Composable
private fun MailHeaderInfo(
    sender: String,
    subject: String,
    index: Int,
    total: Int
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = MaterialTheme.colorScheme.surfaceVariant
        ) {
            Text(
                text = "Wiadomość $index z $total",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
            )
        }
        Spacer(modifier = Modifier.height(6.dp))
        Text(
            text = sender,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        Text(
            text = subject,
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center
        )
    }
}

@Composable
private fun AudioStateIndicator(
    iconRes: Int,
    label: String,
    color: Color,
    isPulsing: Boolean
) {
    val scale = if (isPulsing) {
        val infiniteTransition = rememberInfiniteTransition(label = "pulse")
        val animScale by infiniteTransition.animateFloat(
            initialValue = 0.9f,
            targetValue = 1.15f,
            animationSpec = infiniteRepeatable(
                animation = tween(600, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse
            ),
            label = "scale"
        )
        animScale
    } else {
        1.0f
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(72.dp)
                .scale(scale)
                .background(color.copy(alpha = 0.2f), shape = CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                painter = painterResource(id = iconRes),
                contentDescription = null,
                modifier = Modifier.size(36.dp),
                tint = color
            )
        }

        Spacer(modifier = Modifier.height(14.dp))

        Text(
            text = label,
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}
