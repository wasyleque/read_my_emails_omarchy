package io.github.wasyleque.mailvoice.ui

import io.github.wasyleque.mailvoice.pairing.PairingPayload

sealed interface MainUiState {
    data object Loading : MainUiState

    data class Unpaired(
        val isChecking: Boolean = false,
        val showCameraRationale: Boolean = false,
        val errorMessage: String? = null,
        val isSecurityAlert: Boolean = false
    ) : MainUiState

    data object ScanningQr : MainUiState

    data class ManualEntry(
        val rawLink: String = "",
        val host: String = "",
        val port: String = "8765",
        val code: String = "",
        val fingerprint: String = "",
        val errorMessage: String? = null
    ) : MainUiState

    data class Connecting(
        val host: String,
        val message: String
    ) : MainUiState

    data class Connected(
        val host: String,
        val port: Int,
        val serverVersion: String,
        val accountsCount: Int,
        val activeDevicesCount: Int,
        val lastTick: String? = null,
        val isRefreshing: Boolean = false,
        val showDisconnectDialog: Boolean = false,
        val errorMessage: String? = null,
        val isSecurityAlert: Boolean = false
    ) : MainUiState
}
