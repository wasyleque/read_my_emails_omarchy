package io.github.wasyleque.mailvoice.voice

import io.github.wasyleque.mailvoice.net.ApiResult
import io.github.wasyleque.mailvoice.net.ImportantMail
import io.github.wasyleque.mailvoice.net.MailApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

sealed interface VoiceSessionState {
    data object Idle : VoiceSessionState

    data class ReadingMail(
        val mail: ImportantMail,
        val textToSpeak: String,
        val currentIndex: Int,
        val totalCount: Int
    ) : VoiceSessionState

    data class AskingPrompt(
        val mail: ImportantMail,
        val promptText: String,
        val currentIndex: Int,
        val totalCount: Int
    ) : VoiceSessionState

    data class Listening(
        val mail: ImportantMail,
        val currentIndex: Int,
        val totalCount: Int
    ) : VoiceSessionState

    data class ProcessingCommand(
        val recognizedText: String,
        val mail: ImportantMail,
        val currentIndex: Int,
        val totalCount: Int
    ) : VoiceSessionState

    data class SpeakingFeedback(
        val feedbackText: String,
        val mail: ImportantMail,
        val currentIndex: Int,
        val totalCount: Int,
        val onDoneAction: () -> Unit
    ) : VoiceSessionState

    data class Finished(
        val message: String
    ) : VoiceSessionState

    data class Error(
        val message: String
    ) : VoiceSessionState
}

/**
 * Czysty kontroler maszyny stanów sesji głosowej „Czytaj dalej?” (w pełni testowalny na JVM).
 *
 * Gwarancje bezpieczeństwa:
 * 1. Tekst wysyłany do /v1/voice/command pochodzi WYŁĄCZNIE z parametru wejściowego mikrofonu.
 *    Treść maila NIGDY nie staje się komendą głosową.
 * 2. Tekst czytany przez TTS jest filtrowany przez UrlSanitizer (brak odczytu adresów URL).
 * 3. Wiadomości podejrzane (suspicious == true) są blokowane — czytane jest tylko ostrzeżenie.
 */
class VoiceSessionController(
    private val mailApi: MailApi,
    private val defaultPromptText: String = "Czytać dalej?",
    private val language: String = "pl"
) {

    private val _state = MutableStateFlow<VoiceSessionState>(VoiceSessionState.Idle)
    val state: StateFlow<VoiceSessionState> = _state.asStateFlow()

    private var playlist: List<ImportantMail> = emptyList()
    private var currentIndex: Int = 0

    /**
     * Rozpoczyna sesję czytania zadanej listy ważnych maili.
     */
    fun start(mails: List<ImportantMail>) {
        if (mails.isEmpty()) {
            _state.value = VoiceSessionState.Finished("Brak wiadomości do przeczytania.")
            return
        }
        playlist = mails
        currentIndex = 0
        readCurrentMail()
    }

    private fun readCurrentMail() {
        if (currentIndex !in playlist.indices) {
            _state.value = VoiceSessionState.Finished("Przeczytano wszystkie wiadomości.")
            return
        }

        val currentMail = playlist[currentIndex]

        // Reguła bezpieczeństwa: mail podejrzany ma zablokowaną treść
        val textToSpeak = if (currentMail.suspicious) {
            val senderSafe = UrlSanitizer.prepareForSpeech(currentMail.sender)
            "Uwaga. Wiadomość od: $senderSafe, została oznaczona jako podejrzana. Treść nie została pobrana ze względów bezpieczeństwa."
        } else {
            val senderSafe = UrlSanitizer.prepareForSpeech(currentMail.sender)
            val subjectSafe = UrlSanitizer.prepareForSpeech(currentMail.subject)
            val summarySafe = currentMail.summary?.let { UrlSanitizer.prepareForSpeech(it) }.orEmpty()

            buildString {
                append("Wiadomość od: ").append(senderSafe).append(". ")
                append("Temat: ").append(subjectSafe).append(". ")
                if (summarySafe.isNotBlank()) {
                    append(summarySafe)
                }
            }
        }

        _state.value = VoiceSessionState.ReadingMail(
            mail = currentMail,
            textToSpeak = textToSpeak,
            currentIndex = currentIndex,
            totalCount = playlist.size
        )
    }

    /**
     * Wywoływane gdy syntezator TTS skończy czytać streszczenie bieżącego maila.
     * Przechodzi do zadania pytania „Czytać dalej?”.
     */
    fun onSummaryReadingFinished() {
        val current = _state.value as? VoiceSessionState.ReadingMail ?: return

        // Jeśli to był ostatni mail z listy, kończymy sesję
        if (current.currentIndex >= current.totalCount - 1) {
            _state.value = VoiceSessionState.Finished("To była ostatnia wiadomość.")
            return
        }

        _state.value = VoiceSessionState.AskingPrompt(
            mail = current.mail,
            promptText = defaultPromptText,
            currentIndex = current.currentIndex,
            totalCount = current.totalCount
        )
    }

    /**
     * Wywoływane gdy syntezator TTS skończy wymawiać pytanie „Czytać dalej?”.
     * Przechodzi w stan nasłuchu mikrofonu (STT).
     */
    fun onPromptReadingFinished() {
        val current = _state.value as? VoiceSessionState.AskingPrompt ?: return
        _state.value = VoiceSessionState.Listening(
            mail = current.mail,
            currentIndex = current.currentIndex,
            totalCount = current.totalCount
        )
    }

    /**
     * Bezpieczne przetworzenie tekstu rozpoznanego z mikrofonu użytkownika.
     * Parametr [microphoneText] pochodzi WYŁĄCZNIE z silnika STT.
     */
    suspend fun handleRecognizedSpeech(microphoneText: String) {
        val currentListening = _state.value as? VoiceSessionState.Listening ?: return

        val cleanMicrophoneInput = microphoneText.trim()
        if (cleanMicrophoneInput.isBlank()) {
            // Brak mowy: ponów pytanie
            _state.value = VoiceSessionState.AskingPrompt(
                mail = currentListening.mail,
                promptText = "Nie usłyszałem odpowiedzi. $defaultPromptText",
                currentIndex = currentListening.currentIndex,
                totalCount = currentListening.totalCount
            )
            return
        }

        _state.value = VoiceSessionState.ProcessingCommand(
            recognizedText = cleanMicrophoneInput,
            mail = currentListening.mail,
            currentIndex = currentListening.currentIndex,
            totalCount = currentListening.totalCount
        )

        // Wywołanie API z tekstem WYŁĄCZNIE z mikrofonu
        when (val result = mailApi.sendVoiceCommand(cleanMicrophoneInput, lang = language)) {
            is ApiResult.Success -> {
                executeVoiceAction(
                    action = VoiceAction.fromString(result.data.action),
                    replyText = result.data.replyText,
                    currentMail = currentListening.mail
                )
            }
            is ApiResult.Error -> {
                _state.value = VoiceSessionState.Error("Błąd serwera przy przetwarzaniu komendy: ${result.message}")
            }
        }
    }

    private fun executeVoiceAction(
        action: VoiceAction,
        replyText: String,
        currentMail: ImportantMail
    ) {
        when (action) {
            VoiceAction.NEXT, VoiceAction.YES -> {
                currentIndex++
                readCurrentMail()
            }
            VoiceAction.REPEAT -> {
                readCurrentMail()
            }
            VoiceAction.SKIP, VoiceAction.NO -> {
                currentIndex++
                readCurrentMail()
            }
            VoiceAction.STOP -> {
                _state.value = VoiceSessionState.Finished("Zatrzymano odtwarzanie.")
            }
            VoiceAction.UNKNOWN -> {
                val feedback = replyText.ifBlank { "Nie zrozumiałem polecenia." }
                _state.value = VoiceSessionState.SpeakingFeedback(
                    feedbackText = feedback,
                    mail = currentMail,
                    currentIndex = currentIndex,
                    totalCount = playlist.size,
                    onDoneAction = {
                        _state.value = VoiceSessionState.AskingPrompt(
                            mail = currentMail,
                            promptText = defaultPromptText,
                            currentIndex = currentIndex,
                            totalCount = playlist.size
                        )
                    }
                )
            }
            else -> {
                // Pozostałe akcje (np. głośniej/ciszej)
                val feedback = replyText.ifBlank { "Wykonano polecenie." }
                _state.value = VoiceSessionState.SpeakingFeedback(
                    feedbackText = feedback,
                    mail = currentMail,
                    currentIndex = currentIndex,
                    totalCount = playlist.size,
                    onDoneAction = {
                        _state.value = VoiceSessionState.AskingPrompt(
                            mail = currentMail,
                            promptText = defaultPromptText,
                            currentIndex = currentIndex,
                            totalCount = playlist.size
                        )
                    }
                )
            }
        }
    }

    /**
     * Ręczne akcje dotykowe (alternatywa dla sterowania głosem).
     */
    fun nextManual() {
        currentIndex++
        readCurrentMail()
    }

    fun repeatManual() {
        readCurrentMail()
    }

    fun skipManual() {
        currentIndex++
        readCurrentMail()
    }

    fun stopSession() {
        _state.value = VoiceSessionState.Finished("Zakończono odsłuchiwanie.")
    }

    fun onFeedbackReadingFinished() {
        val current = _state.value as? VoiceSessionState.SpeakingFeedback ?: return
        current.onDoneAction()
    }
}
