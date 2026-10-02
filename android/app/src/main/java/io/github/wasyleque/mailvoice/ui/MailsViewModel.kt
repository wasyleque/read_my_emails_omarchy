package io.github.wasyleque.mailvoice.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.wasyleque.mailvoice.net.ApiResult
import io.github.wasyleque.mailvoice.net.ImportantMail
import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.voice.VoiceSessionController
import io.github.wasyleque.mailvoice.voice.VoiceSessionState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MailsViewModel(
    private val mailApi: MailApi,
    private val voiceController: VoiceSessionController = VoiceSessionController(mailApi)
) : ViewModel() {

    private val _mails = MutableStateFlow<List<ImportantMail>>(emptyList())
    val mails: StateFlow<List<ImportantMail>> = _mails.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val _isSecurityAlert = MutableStateFlow(false)
    val isSecurityAlert: StateFlow<Boolean> = _isSecurityAlert.asStateFlow()

    private val _isUnauthorized = MutableStateFlow(false)
    val isUnauthorized: StateFlow<Boolean> = _isUnauthorized.asStateFlow()

    private val _selectedMail = MutableStateFlow<ImportantMail?>(null)
    val selectedMail: StateFlow<ImportantMail?> = _selectedMail.asStateFlow()

    private val _isVoiceSessionActive = MutableStateFlow(false)
    val isVoiceSessionActive: StateFlow<Boolean> = _isVoiceSessionActive.asStateFlow()

    val voiceSessionState: StateFlow<VoiceSessionState> = voiceController.state

    init {
        loadMails()
    }

    fun loadMails() {
        _isLoading.value = true
        _errorMessage.value = null
        _isSecurityAlert.value = false

        viewModelScope.launch {
            when (val result = mailApi.getImportantMails(limit = 30)) {
                is ApiResult.Success -> {
                    _mails.value = result.data
                    _isLoading.value = false
                }
                is ApiResult.Error -> {
                    _isLoading.value = false
                    _errorMessage.value = result.message
                    _isSecurityAlert.value = result.isSecurityAlert
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                }
            }
        }
    }

    fun selectMail(mail: ImportantMail) {
        _selectedMail.value = mail
    }

    fun clearSelectedMail() {
        _selectedMail.value = null
    }

    fun ackMail(mailId: String) {
        viewModelScope.launch {
            when (val result = mailApi.ackMail(mailId)) {
                is ApiResult.Success -> {
                    // Aktualizuj stan lokalnie na liście
                    _mails.value = _mails.value.map {
                        if (it.id == mailId) it.copy(acknowledged = true) else it
                    }
                    if (_selectedMail.value?.id == mailId) {
                        _selectedMail.value = _selectedMail.value?.copy(acknowledged = true)
                    }
                }
                is ApiResult.Error -> {
                    _errorMessage.value = result.message
                }
            }
        }
    }

    fun startVoiceSession(targetMails: List<ImportantMail>? = null) {
        val listToRead = targetMails ?: _mails.value.filter { !it.acknowledged }
        if (listToRead.isEmpty()) {
            _errorMessage.value = "Brak wiadomości do przeczytania."
            return
        }
        _isVoiceSessionActive.value = true
        voiceController.start(listToRead)
    }

    fun stopVoiceSession() {
        voiceController.stopSession()
        _isVoiceSessionActive.value = false
    }

    fun onSummaryReadingFinished() {
        voiceController.onSummaryReadingFinished()
    }

    fun onPromptReadingFinished() {
        voiceController.onPromptReadingFinished()
    }

    fun onFeedbackReadingFinished() {
        voiceController.onFeedbackReadingFinished()
    }

    fun handleRecognizedSpeech(text: String) {
        viewModelScope.launch {
            voiceController.handleRecognizedSpeech(text)
        }
    }

    fun nextManual() {
        voiceController.nextManual()
    }

    fun repeatManual() {
        voiceController.repeatManual()
    }

    fun skipManual() {
        voiceController.skipManual()
    }

    fun dismissError() {
        _errorMessage.value = null
        _isSecurityAlert.value = false
    }
}
