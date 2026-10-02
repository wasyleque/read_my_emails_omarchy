package io.github.wasyleque.mailvoice.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.wasyleque.mailvoice.net.ApiResult
import io.github.wasyleque.mailvoice.net.IgnoreMode
import io.github.wasyleque.mailvoice.net.ImportantMail
import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.voice.VoiceSessionController
import io.github.wasyleque.mailvoice.voice.VoiceSessionState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MailsUiState {
    data object Loading : MailsUiState
    data class Content(
        val mails: List<ImportantMail>,
        val isRefreshing: Boolean = false,
        val refreshError: String? = null
    ) : MailsUiState
    data object Empty : MailsUiState
    data class Error(
        val message: String,
        val canRetry: Boolean = true
    ) : MailsUiState
}

class MailsViewModel(
    private val mailApi: MailApi,
    private val voiceController: VoiceSessionController = VoiceSessionController(mailApi)
) : ViewModel() {

    private val _uiState = MutableStateFlow<MailsUiState>(MailsUiState.Loading)
    val uiState: StateFlow<MailsUiState> = _uiState.asStateFlow()

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

    // Stan dialogu ignorowania wiadomości
    private val _ignoreDialogTarget = MutableStateFlow<ImportantMail?>(null)
    val ignoreDialogTarget: StateFlow<ImportantMail?> = _ignoreDialogTarget.asStateFlow()

    private val _isIgnoring = MutableStateFlow(false)
    val isIgnoring: StateFlow<Boolean> = _isIgnoring.asStateFlow()

    private val _ignoreErrorMessage = MutableStateFlow<String?>(null)
    val ignoreErrorMessage: StateFlow<String?> = _ignoreErrorMessage.asStateFlow()

    // Stan dialogu oznaczania VIP
    private val _vipDialogTarget = MutableStateFlow<ImportantMail?>(null)
    val vipDialogTarget: StateFlow<ImportantMail?> = _vipDialogTarget.asStateFlow()

    private val _isMarkingVip = MutableStateFlow(false)
    val isMarkingVip: StateFlow<Boolean> = _isMarkingVip.asStateFlow()

    private val _vipErrorMessage = MutableStateFlow<String?>(null)
    val vipErrorMessage: StateFlow<String?> = _vipErrorMessage.asStateFlow()

    private val _userMessage = MutableStateFlow<String?>(null)
    val userMessage: StateFlow<String?> = _userMessage.asStateFlow()

    init {
        loadMails()
    }

    fun loadMails() {
        _isLoading.value = true
        _errorMessage.value = null
        _isSecurityAlert.value = false

        val current = _uiState.value
        if (current is MailsUiState.Content) {
            _uiState.value = current.copy(isRefreshing = true, refreshError = null)
        } else {
            _uiState.value = MailsUiState.Loading
        }

        viewModelScope.launch {
            when (val result = mailApi.getImportantMails(limit = 30)) {
                is ApiResult.Success -> {
                    _mails.value = result.data
                    _isLoading.value = false
                    if (result.data.isEmpty()) {
                        _uiState.value = MailsUiState.Empty
                    } else {
                        _uiState.value = MailsUiState.Content(
                            mails = result.data,
                            isRefreshing = false,
                            refreshError = null
                        )
                    }
                }
                is ApiResult.Error -> {
                    _isLoading.value = false
                    _errorMessage.value = result.message
                    _isSecurityAlert.value = result.isSecurityAlert
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                    val stateNow = _uiState.value
                    if (stateNow is MailsUiState.Content) {
                        _uiState.value = stateNow.copy(
                            isRefreshing = false,
                            refreshError = result.message
                        )
                    } else {
                        _uiState.value = MailsUiState.Error(
                            message = result.message,
                            canRetry = !result.isUnauthorized
                        )
                    }
                }
            }
        }
    }

    fun dismissRefreshError() {
        val current = _uiState.value
        if (current is MailsUiState.Content && current.refreshError != null) {
            _uiState.value = current.copy(refreshError = null)
        }
    }

    fun selectMail(mail: ImportantMail) {
        _selectedMail.value = mail
    }

    fun clearSelectedMail() {
        _selectedMail.value = null
    }

    fun openIgnoreDialog(mail: ImportantMail) {
        _ignoreErrorMessage.value = null
        _ignoreDialogTarget.value = mail
    }

    fun dismissIgnoreDialog() {
        if (!_isIgnoring.value) {
            _ignoreDialogTarget.value = null
            _ignoreErrorMessage.value = null
        }
    }

    fun confirmIgnore(mode: IgnoreMode) {
        val targetMail = _ignoreDialogTarget.value ?: return
        _isIgnoring.value = true
        _ignoreErrorMessage.value = null

        viewModelScope.launch {
            when (val result = mailApi.ignoreMail(targetMail.id, mode.apiValue)) {
                is ApiResult.Success -> {
                    _isIgnoring.value = false
                    _ignoreDialogTarget.value = null
                    // Usuń zignorowaną wiadomość z lokalnej listy
                    val filteredMails = _mails.value.filter { it.id != targetMail.id }
                    _mails.value = filteredMails
                    val current = _uiState.value
                    if (current is MailsUiState.Content) {
                        if (filteredMails.isEmpty()) {
                            _uiState.value = MailsUiState.Empty
                        } else {
                            _uiState.value = current.copy(mails = filteredMails)
                        }
                    }
                    if (_selectedMail.value?.id == targetMail.id) {
                        _selectedMail.value = null
                    }
                    _userMessage.value = "Zignorowano"
                    // Odśwież listę z serwera, aby zniknęły wszystkie podobne
                    loadMails()
                }
                is ApiResult.Error -> {
                    _isIgnoring.value = false
                    _ignoreErrorMessage.value = result.message
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                }
            }
        }
    }

    fun openVipDialog(mail: ImportantMail) {
        // Dla maili oznaczonych jako podejrzane NIE otwieraj dialogu VIP
        if (mail.suspicious) return
        _vipErrorMessage.value = null
        _vipDialogTarget.value = mail
    }

    fun dismissVipDialog() {
        if (!_isMarkingVip.value) {
            _vipDialogTarget.value = null
            _vipErrorMessage.value = null
        }
    }

    fun confirmVip(mode: IgnoreMode) {
        val targetMail = _vipDialogTarget.value ?: return
        if (targetMail.suspicious) return
        _isMarkingVip.value = true
        _vipErrorMessage.value = null

        viewModelScope.launch {
            when (val result = mailApi.vipMail(targetMail.id, mode.apiValue)) {
                is ApiResult.Success -> {
                    _isMarkingVip.value = false
                    _vipDialogTarget.value = null
                    _userMessage.value = "Oznaczono jako VIP"
                    // Odśwież listę z serwera
                    loadMails()
                }
                is ApiResult.Error -> {
                    _isMarkingVip.value = false
                    _vipErrorMessage.value = result.message
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                }
            }
        }
    }

    fun clearUserMessage() {
        _userMessage.value = null
    }

    fun ackMail(mailId: String) {
        viewModelScope.launch {
            when (val result = mailApi.ackMail(mailId)) {
                is ApiResult.Success -> {
                    // Aktualizuj stan lokalnie na liście
                    val updatedMails = _mails.value.map {
                        if (it.id == mailId) it.copy(acknowledged = true) else it
                    }
                    _mails.value = updatedMails
                    val current = _uiState.value
                    if (current is MailsUiState.Content) {
                        _uiState.value = current.copy(mails = updatedMails)
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
