package io.github.wasyleque.mailvoice.ui

import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.wasyleque.mailvoice.pairing.PairingPayload
import io.github.wasyleque.mailvoice.pairing.PairingQrParser
import io.github.wasyleque.mailvoice.pairing.PairingRepository
import io.github.wasyleque.mailvoice.pairing.PairingResult
import io.github.wasyleque.mailvoice.pairing.ServerStatusResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MainViewModel(
    private val repository: PairingRepository,
    private val defaultDeviceName: String = defaultDeviceName()
) : ViewModel() {

    private val _uiState = MutableStateFlow<MainUiState>(MainUiState.Loading)
    val uiState: StateFlow<MainUiState> = _uiState.asStateFlow()

    init {
        checkInitialStatus()
    }

    private fun checkInitialStatus() {
        if (!repository.isPaired()) {
            _uiState.value = MainUiState.Unpaired()
            return
        }

        val host = repository.getSavedHost().orEmpty()
        val port = repository.getSavedPort()

        _uiState.value = MainUiState.Connected(
            host = host,
            port = port,
            serverVersion = "...",
            accountsCount = 0,
            activeDevicesCount = 1,
            isRefreshing = true
        )

        viewModelScope.launch {
            when (val res = repository.checkStatus()) {
                is ServerStatusResult.Connected -> {
                    _uiState.value = MainUiState.Connected(
                        host = res.serverHost,
                        port = res.serverPort,
                        serverVersion = res.version,
                        accountsCount = res.accountsCount,
                        activeDevicesCount = res.activeDevicesCount,
                        lastTick = res.lastTick,
                        isRefreshing = false
                    )
                }
                is ServerStatusResult.Error -> {
                    if (res.isUnauthorized) {
                        _uiState.value = MainUiState.Unpaired(
                            errorMessage = res.message,
                            isSecurityAlert = false
                        )
                    } else {
                        // Serwer tymczasowo offline, ale poświadczenia są zachowane
                        _uiState.value = MainUiState.Connected(
                            host = host,
                            port = port,
                            serverVersion = "niedostępna",
                            accountsCount = 0,
                            activeDevicesCount = 1,
                            isRefreshing = false,
                            errorMessage = res.message,
                            isSecurityAlert = res.isSecurityAlert
                        )
                    }
                }
            }
        }
    }

    fun onStartScanClicked(hasCameraPermission: Boolean) {
        if (hasCameraPermission) {
            _uiState.value = MainUiState.ScanningQr
        } else {
            val current = _uiState.value as? MainUiState.Unpaired ?: MainUiState.Unpaired()
            _uiState.value = current.copy(showCameraRationale = true)
        }
    }

    fun onCameraPermissionGranted() {
        _uiState.value = MainUiState.ScanningQr
    }

    fun onDismissCameraRationale() {
        val current = _uiState.value as? MainUiState.Unpaired ?: MainUiState.Unpaired()
        _uiState.value = current.copy(showCameraRationale = false)
    }

    fun onOpenManualEntry() {
        _uiState.value = MainUiState.ManualEntry()
    }

    fun onBackToUnpaired() {
        _uiState.value = MainUiState.Unpaired()
    }

    fun onQrCodeScanned(rawContent: String) {
        try {
            val payload = PairingQrParser.parse(rawContent)
            startPairing(payload)
        } catch (e: Exception) {
            _uiState.value = MainUiState.Unpaired(
                errorMessage = e.localizedMessage ?: "Niepoprawny kod QR",
                isSecurityAlert = false
            )
        }
    }

    fun onManualSubmit(
        rawLink: String,
        host: String,
        portStr: String,
        code: String,
        fp: String
    ) {
        val trimmedLink = rawLink.trim()
        if (trimmedLink.isNotBlank()) {
            try {
                val payload = PairingQrParser.parse(trimmedLink)
                startPairing(payload)
                return
            } catch (e: Exception) {
                _uiState.value = MainUiState.ManualEntry(
                    rawLink = rawLink,
                    host = host,
                    port = portStr,
                    code = code,
                    fingerprint = fp,
                    errorMessage = e.localizedMessage ?: "Niepoprawny link parowania"
                )
                return
            }
        }

        // Walidacja pól ręcznych
        val trimmedHost = host.trim()
        val trimmedCode = code.trim().uppercase()
        val trimmedFp = fp.trim().lowercase()
        val port = portStr.trim().toIntOrNull() ?: 0

        if (trimmedHost.isBlank() || trimmedCode.isBlank() || trimmedFp.isBlank()) {
            _uiState.value = MainUiState.ManualEntry(
                rawLink = rawLink,
                host = host,
                port = portStr,
                code = code,
                fingerprint = fp,
                errorMessage = "Wypełnij wszystkie wymagane pola (adres IP, kod oraz odcisk)."
            )
            return
        }

        val syntheticUrl = "mailvoice://pair?host=$trimmedHost&port=$port&code=$trimmedCode&fp=$trimmedFp&v=1"
        try {
            val payload = PairingQrParser.parse(syntheticUrl)
            startPairing(payload)
        } catch (e: Exception) {
            _uiState.value = MainUiState.ManualEntry(
                rawLink = rawLink,
                host = host,
                port = portStr,
                code = code,
                fingerprint = fp,
                errorMessage = e.localizedMessage ?: "Błędne dane parowania"
            )
        }
    }

    private fun startPairing(payload: PairingPayload) {
        _uiState.value = MainUiState.Connecting(
            host = payload.host,
            message = "Łączenie z serwerem MailVoice (${payload.host}:${payload.port})..."
        )

        viewModelScope.launch {
            when (val result = repository.pair(payload, defaultDeviceName)) {
                is PairingResult.Success -> {
                    _uiState.value = MainUiState.Connected(
                        host = result.serverHost,
                        port = result.serverPort,
                        serverVersion = result.serverVersion,
                        accountsCount = result.accountsCount,
                        activeDevicesCount = result.activeDevicesCount
                    )
                }
                is PairingResult.Error -> {
                    _uiState.value = MainUiState.Unpaired(
                        errorMessage = result.message,
                        isSecurityAlert = result.isSecurityAlert
                    )
                }
            }
        }
    }

    fun onRefreshStatus() {
        val current = _uiState.value as? MainUiState.Connected ?: return
        _uiState.value = current.copy(isRefreshing = true, errorMessage = null)

        viewModelScope.launch {
            when (val res = repository.checkStatus()) {
                is ServerStatusResult.Connected -> {
                    _uiState.value = current.copy(
                        host = res.serverHost,
                        port = res.serverPort,
                        serverVersion = res.version,
                        accountsCount = res.accountsCount,
                        activeDevicesCount = res.activeDevicesCount,
                        lastTick = res.lastTick,
                        isRefreshing = false,
                        errorMessage = null
                    )
                }
                is ServerStatusResult.Error -> {
                    if (res.isUnauthorized) {
                        _uiState.value = MainUiState.Unpaired(
                            errorMessage = res.message,
                            isSecurityAlert = false
                        )
                    } else {
                        _uiState.value = current.copy(
                            isRefreshing = false,
                            errorMessage = res.message,
                            isSecurityAlert = res.isSecurityAlert
                        )
                    }
                }
            }
        }
    }

    fun onRequestDisconnect() {
        val current = _uiState.value as? MainUiState.Connected ?: return
        _uiState.value = current.copy(showDisconnectDialog = true)
    }

    fun onDismissDisconnectDialog() {
        val current = _uiState.value as? MainUiState.Connected ?: return
        _uiState.value = current.copy(showDisconnectDialog = false)
    }

    fun onConfirmDisconnect() {
        _uiState.value = MainUiState.Loading
        viewModelScope.launch {
            repository.disconnect()
            _uiState.value = MainUiState.Unpaired()
        }
    }

    fun onDismissError() {
        when (val current = _uiState.value) {
            is MainUiState.Unpaired -> _uiState.value = current.copy(errorMessage = null)
            is MainUiState.Connected -> _uiState.value = current.copy(errorMessage = null)
            is MainUiState.ManualEntry -> _uiState.value = current.copy(errorMessage = null)
            else -> {}
        }
    }

    companion object {
        private fun defaultDeviceName(): String {
            return try {
                val manufacturer = Build.MANUFACTURER.orEmpty().replaceFirstChar { it.uppercase() }
                val model = Build.MODEL.orEmpty()
                if (model.startsWith(manufacturer, ignoreCase = true)) {
                    model
                } else {
                    "$manufacturer $model".trim()
                }.ifBlank { "Android Phone" }
            } catch (_: Exception) {
                "Android Phone"
            }
        }
    }
}
