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

class DigestViewModel(
    private val mailApi: MailApi
) : ViewModel() {

    private val _days = MutableStateFlow(30)
    val days: StateFlow<Int> = _days.asStateFlow()

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

    fun loadDigest(targetDays: Int = _days.value) {
        _days.value = targetDays
        _isLoading.value = true
        _errorMessage.value = null

        viewModelScope.launch {
            when (val result = mailApi.getDigest(days = targetDays)) {
                is ApiResult.Success -> {
                    _digest.value = result.data
                    _isLoading.value = false
                }
                is ApiResult.Error -> {
                    _isLoading.value = false
                    _errorMessage.value = result.message
                    if (result.isUnauthorized) {
                        _isUnauthorized.value = true
                    }
                }
            }
        }
    }

    fun setDays(newDays: Int) {
        if (_days.value != newDays) {
            loadDigest(newDays)
        }
    }

    fun dismissError() {
        _errorMessage.value = null
    }
}
