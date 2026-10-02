package io.github.wasyleque.mailvoice.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.wasyleque.mailvoice.net.ApiResult
import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.net.TopicDigest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface DigestUiState {
    data object Loading : DigestUiState
    data class Content(
        val digest: TopicDigest,
        val isRefreshing: Boolean = false,
        val refreshError: String? = null,
        val showAll: Boolean = false
    ) : DigestUiState
    data object Empty : DigestUiState
    data class Error(
        val message: String,
        val canRetry: Boolean = true
    ) : DigestUiState
}

class DigestViewModel(
    private val mailApi: MailApi
) : ViewModel() {

    private val _uiState = MutableStateFlow<DigestUiState>(DigestUiState.Loading)
    val uiState: StateFlow<DigestUiState> = _uiState.asStateFlow()

    private val _days = MutableStateFlow(30)
    val days: StateFlow<Int> = _days.asStateFlow()

    private val _showAll = MutableStateFlow(false)
    val showAll: StateFlow<Boolean> = _showAll.asStateFlow()

    private val _digest = MutableStateFlow<TopicDigest?>(null)
    val digest: StateFlow<TopicDigest?> = _digest.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val _isUnauthorized = MutableStateFlow(false)
    val isUnauthorized: StateFlow<Boolean> = _isUnauthorized.asStateFlow()

    init {
        loadDigest()
    }

    fun loadDigest(targetDays: Int = _days.value, all: Boolean = _showAll.value) {
        _days.value = targetDays
        _showAll.value = all
        _isLoading.value = true
        _errorMessage.value = null

        val current = _uiState.value
        if (current is DigestUiState.Content) {
            _uiState.value = current.copy(isRefreshing = true, refreshError = null, showAll = all)
        } else {
            _uiState.value = DigestUiState.Loading
        }

        viewModelScope.launch {
            val limit = if (all) 100 else 60
            when (val result = mailApi.getDigest(days = targetDays, limit = limit, all = all)) {
                is ApiResult.Success -> {
                    _digest.value = result.data
                    _isLoading.value = false
                    if (result.data.topics.isEmpty()) {
                        _uiState.value = DigestUiState.Empty
                    } else {
                        _uiState.value = DigestUiState.Content(
                            digest = result.data,
                            isRefreshing = false,
                            refreshError = null,
                            showAll = all
                        )
                    }
                }
                is ApiResult.Error -> {
                    _isLoading.value = false
                    _errorMessage.value = result.message
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                    val stateNow = _uiState.value
                    if (stateNow is DigestUiState.Content) {
                        _uiState.value = stateNow.copy(
                            isRefreshing = false,
                            refreshError = result.message,
                            showAll = all
                        )
                    } else {
                        _uiState.value = DigestUiState.Error(
                            message = result.message,
                            canRetry = !result.isUnauthorized
                        )
                    }
                }
            }
        }
    }

    fun setDays(newDays: Int) {
        if (_days.value != newDays) {
            loadDigest(targetDays = newDays, all = _showAll.value)
        }
    }

    fun setShowAll(all: Boolean) {
        if (_showAll.value != all) {
            loadDigest(targetDays = _days.value, all = all)
        }
    }

    fun dismissError() {
        _errorMessage.value = null
        val current = _uiState.value
        if (current is DigestUiState.Content && current.refreshError != null) {
            _uiState.value = current.copy(refreshError = null)
        }
    }
}
