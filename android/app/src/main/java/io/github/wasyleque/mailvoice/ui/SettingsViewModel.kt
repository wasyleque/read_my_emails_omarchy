package io.github.wasyleque.mailvoice.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.wasyleque.mailvoice.net.ApiResult
import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.net.ServerStatus
import io.github.wasyleque.mailvoice.pairing.PairingRepository
import io.github.wasyleque.mailvoice.security.TokenStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SettingsViewModel(
    private val mailApi: MailApi,
    private val pairingRepository: PairingRepository,
    private val tokenStore: TokenStore
) : ViewModel() {

    private val _status = MutableStateFlow<ServerStatus?>(null)
    val status: StateFlow<ServerStatus?> = _status.asStateFlow()

    private val _host = MutableStateFlow(tokenStore.getServerHost().orEmpty())
    val host: StateFlow<String> = _host.asStateFlow()

    private val _port = MutableStateFlow(tokenStore.getServerPort())
    val port: StateFlow<Int> = _port.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _selectedLanguage = MutableStateFlow("pl")
    val selectedLanguage: StateFlow<String> = _selectedLanguage.asStateFlow()

    private val _showDisconnectDialog = MutableStateFlow(false)
    val showDisconnectDialog: StateFlow<Boolean> = _showDisconnectDialog.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    init {
        refreshStatus()
    }

    fun refreshStatus() {
        _isLoading.value = true
        _errorMessage.value = null
        _host.value = tokenStore.getServerHost().orEmpty()
        _port.value = tokenStore.getServerPort()

        viewModelScope.launch {
            when (val result = mailApi.getStatus()) {
                is ApiResult.Success -> {
                    _status.value = result.data
                    _isLoading.value = false
                }
                is ApiResult.Error -> {
                    _isLoading.value = false
                    _errorMessage.value = result.message
                }
            }
        }
    }

    fun setLanguage(lang: String) {
        _selectedLanguage.value = lang
    }

    fun showDisconnectDialog() {
        _showDisconnectDialog.value = true
    }

    fun dismissDisconnectDialog() {
        _showDisconnectDialog.value = false
    }

    fun confirmDisconnect(onDisconnected: () -> Unit) {
        _showDisconnectDialog.value = false
        _isLoading.value = true

        viewModelScope.launch {
            pairingRepository.disconnect()
            _isLoading.value = false
            onDisconnected()
        }
    }

    fun dismissError() {
        _errorMessage.value = null
    }
}
