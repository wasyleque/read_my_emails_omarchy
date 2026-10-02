package io.github.wasyleque.mailvoice

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.wasyleque.mailvoice.pairing.PairingRepository
import io.github.wasyleque.mailvoice.security.KeystoreTokenStore
import io.github.wasyleque.mailvoice.ui.ConnectedScreen
import io.github.wasyleque.mailvoice.ui.ConnectingScreen
import io.github.wasyleque.mailvoice.ui.MainUiState
import io.github.wasyleque.mailvoice.ui.MainViewModel
import io.github.wasyleque.mailvoice.ui.ManualEntryScreen
import io.github.wasyleque.mailvoice.ui.PairingScreen
import io.github.wasyleque.mailvoice.ui.QrScannerScreen

/**
 * Główna aktywność aplikacji MailVoice dla systemu Android.
 * Odpowiada za cykl życia interfejsu parowania i bezpiecznego połączenia z komputerem.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val tokenStore = KeystoreTokenStore(applicationContext)
        val repository = PairingRepository(tokenStore)

        setContent {
            val scheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
            MaterialTheme(colorScheme = scheme) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    MailVoiceApp(repository = repository)
                }
            }
        }
    }
}

@Composable
fun MailVoiceApp(
    repository: PairingRepository,
    viewModel: MainViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return MainViewModel(repository) as T
            }
        }
    )
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            viewModel.onCameraPermissionGranted()
        } else {
            viewModel.onDismissCameraRationale()
        }
    }

    when (val state = uiState) {
        is MainUiState.Loading -> {
            ConnectingScreen(message = "Wczytywanie...")
        }
        is MainUiState.Unpaired -> {
            PairingScreen(
                state = state,
                onScanClicked = {
                    val hasPerm = ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.CAMERA
                    ) == PackageManager.PERMISSION_GRANTED
                    viewModel.onStartScanClicked(hasPerm)
                },
                onManualClicked = { viewModel.onOpenManualEntry() },
                onRequestCameraPermission = {
                    cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                },
                onDismissCameraRationale = { viewModel.onDismissCameraRationale() },
                onDismissError = { viewModel.onDismissError() }
            )
        }
        is MainUiState.ScanningQr -> {
            QrScannerScreen(
                onBack = { viewModel.onBackToUnpaired() },
                onManualClicked = { viewModel.onOpenManualEntry() },
                onQrScanned = { raw -> viewModel.onQrCodeScanned(raw) }
            )
        }
        is MainUiState.ManualEntry -> {
            ManualEntryScreen(
                state = state,
                onBack = { viewModel.onBackToUnpaired() },
                onSubmit = { rawLink, host, port, code, fp ->
                    viewModel.onManualSubmit(rawLink, host, port, code, fp)
                },
                onDismissError = { viewModel.onDismissError() }
            )
        }
        is MainUiState.Connecting -> {
            ConnectingScreen(message = state.message)
        }
        is MainUiState.Connected -> {
            ConnectedScreen(
                state = state,
                onRefreshStatus = { viewModel.onRefreshStatus() },
                onRequestDisconnect = { viewModel.onRequestDisconnect() },
                onDismissDisconnectDialog = { viewModel.onDismissDisconnectDialog() },
                onConfirmDisconnect = { viewModel.onConfirmDisconnect() },
                onDismissError = { viewModel.onDismissError() }
            )
        }
    }
}
