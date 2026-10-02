package io.github.wasyleque.mailvoice

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.wasyleque.mailvoice.net.MailApi
import io.github.wasyleque.mailvoice.pairing.PairingRepository
import io.github.wasyleque.mailvoice.security.KeystoreTokenStore
import io.github.wasyleque.mailvoice.ui.ConnectingScreen
import io.github.wasyleque.mailvoice.ui.DigestScreen
import io.github.wasyleque.mailvoice.ui.DigestViewModel
import io.github.wasyleque.mailvoice.ui.MailDetailScreen
import io.github.wasyleque.mailvoice.ui.MailsListScreen
import io.github.wasyleque.mailvoice.ui.MailsViewModel
import io.github.wasyleque.mailvoice.ui.MainUiState
import io.github.wasyleque.mailvoice.ui.MainViewModel
import io.github.wasyleque.mailvoice.ui.ManualEntryScreen
import io.github.wasyleque.mailvoice.ui.PairingScreen
import io.github.wasyleque.mailvoice.ui.QrScannerScreen
import io.github.wasyleque.mailvoice.ui.SettingsScreen
import io.github.wasyleque.mailvoice.ui.SettingsViewModel
import io.github.wasyleque.mailvoice.ui.VoiceSessionDialog
import io.github.wasyleque.mailvoice.voice.AndroidSpeechHelper
import io.github.wasyleque.mailvoice.voice.AndroidTtsHelper
import io.github.wasyleque.mailvoice.voice.VoiceSessionState

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val tokenStore = KeystoreTokenStore(applicationContext)
        val pairingRepository = PairingRepository(tokenStore)
        val mailApi = MailApi(tokenStore)

        setContent {
            val scheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
            MaterialTheme(colorScheme = scheme) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    MailVoiceApp(
                        pairingRepository = pairingRepository,
                        mailApi = mailApi,
                        tokenStore = tokenStore
                    )
                }
            }
        }
    }
}

@Composable
fun MailVoiceApp(
    pairingRepository: PairingRepository,
    mailApi: MailApi,
    tokenStore: io.github.wasyleque.mailvoice.security.TokenStore,
    mainViewModel: MainViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return MainViewModel(pairingRepository) as T
            }
        }
    )
) {
    val uiState by mainViewModel.uiState.collectAsState()
    val context = LocalContext.current

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            mainViewModel.onCameraPermissionGranted()
        } else {
            mainViewModel.onDismissCameraRationale()
        }
    }

    when (val state = uiState) {
        is MainUiState.Loading -> {
            ConnectingScreen(message = stringResource(R.string.status_connecting))
        }
        is MainUiState.Unpaired -> {
            PairingScreen(
                state = state,
                onScanClicked = {
                    val hasPerm = ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.CAMERA
                    ) == PackageManager.PERMISSION_GRANTED
                    mainViewModel.onStartScanClicked(hasPerm)
                },
                onManualClicked = { mainViewModel.onOpenManualEntry() },
                onRequestCameraPermission = {
                    cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                },
                onDismissCameraRationale = { mainViewModel.onDismissCameraRationale() },
                onDismissError = { mainViewModel.onDismissError() }
            )
        }
        is MainUiState.ScanningQr -> {
            QrScannerScreen(
                onBack = { mainViewModel.onBackToUnpaired() },
                onManualClicked = { mainViewModel.onOpenManualEntry() },
                onQrScanned = { raw -> mainViewModel.onQrCodeScanned(raw) }
            )
        }
        is MainUiState.ManualEntry -> {
            ManualEntryScreen(
                state = state,
                onBack = { mainViewModel.onBackToUnpaired() },
                onSubmit = { rawLink, host, port, code, fp ->
                    mainViewModel.onManualSubmit(rawLink, host, port, code, fp)
                },
                onDismissError = { mainViewModel.onDismissError() }
            )
        }
        is MainUiState.Connecting -> {
            ConnectingScreen(message = state.message)
        }
        is MainUiState.Connected -> {
            // Gdy urządzenie jest sparowane, wyświetlamy główny interfejs aplikacji z zakładkami
            PairedAppMain(
                mailApi = mailApi,
                pairingRepository = pairingRepository,
                tokenStore = tokenStore,
                onDisconnected = {
                    io.github.wasyleque.mailvoice.background.BackgroundController.stop(context.applicationContext)
                    mainViewModel.onBackToUnpaired()
                }
            )
        }
    }
}

@Composable
fun PairedAppMain(
    mailApi: MailApi,
    pairingRepository: PairingRepository,
    tokenStore: io.github.wasyleque.mailvoice.security.TokenStore,
    onDisconnected: () -> Unit
) {
    val context = LocalContext.current
    io.github.wasyleque.mailvoice.background.BackgroundBootstrap()
    var selectedTab by remember { mutableIntStateOf(0) }

    val mailsViewModel: MailsViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return MailsViewModel(mailApi) as T
            }
        }
    )

    val digestViewModel: DigestViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return DigestViewModel(mailApi) as T
            }
        }
    )

    val settingsViewModel: SettingsViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return SettingsViewModel(mailApi, pairingRepository, tokenStore) as T
            }
        }
    )

    // Pomocnicy syntezy i rozpoznawania mowy
    val ttsHelper = remember { AndroidTtsHelper(context) }
    val speechHelper = remember { AndroidSpeechHelper(context) }

    DisposableEffect(Unit) {
        onDispose {
            ttsHelper.shutdown()
            speechHelper.destroy()
        }
    }

    // Uprawnienie do mikrofonu
    var showMicRationale by remember { mutableStateOf(false) }
    val micPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (!isGranted) {
            showMicRationale = false
        }
    }

    val hasMicPermission = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.RECORD_AUDIO
    ) == PackageManager.PERMISSION_GRANTED

    // Obsługa utraty autoryzacji (401)
    val isMailsUnauthorized by mailsViewModel.isUnauthorized.collectAsState()
    val isDigestUnauthorized by digestViewModel.isUnauthorized.collectAsState()
    LaunchedEffect(isMailsUnauthorized, isDigestUnauthorized) {
        if (isMailsUnauthorized || isDigestUnauthorized) {
            onDisconnected()
        }
    }

    // Maszyna stanów sesji głosowej
    val isVoiceActive by mailsViewModel.isVoiceSessionActive.collectAsState()
    val voiceState by mailsViewModel.voiceSessionState.collectAsState()

    LaunchedEffect(voiceState) {
        when (val s = voiceState) {
            is VoiceSessionState.ReadingMail -> {
                speechHelper.stopListening()
                ttsHelper.speak(s.textToSpeak) {
                    mailsViewModel.onSummaryReadingFinished()
                }
            }
            is VoiceSessionState.AskingPrompt -> {
                speechHelper.stopListening()
                ttsHelper.speak(s.promptText) {
                    mailsViewModel.onPromptReadingFinished()
                }
            }
            is VoiceSessionState.Listening -> {
                ttsHelper.stop()
                if (hasMicPermission) {
                    speechHelper.startListening(
                        language = "pl-PL",
                        onResult = { text -> mailsViewModel.handleRecognizedSpeech(text) },
                        onError = { mailsViewModel.handleRecognizedSpeech("") }
                    )
                } else {
                    showMicRationale = true
                }
            }
            is VoiceSessionState.SpeakingFeedback -> {
                speechHelper.stopListening()
                ttsHelper.speak(s.feedbackText) {
                    mailsViewModel.onFeedbackReadingFinished()
                }
            }
            is VoiceSessionState.Finished -> {
                speechHelper.stopListening()
                ttsHelper.speak(s.message)
            }
            else -> {}
        }
    }

    val selectedMail by mailsViewModel.selectedMail.collectAsState()

    if (selectedMail != null) {
        MailDetailScreen(
            mail = selectedMail!!,
            onBack = { mailsViewModel.clearSelectedMail() },
            onListenClicked = { mail -> mailsViewModel.startVoiceSession(listOf(mail)) },
            onAckClicked = { mailId -> mailsViewModel.ackMail(mailId) }
        )
    } else {
        Scaffold(
            bottomBar = {
                NavigationBar {
                    NavigationBarItem(
                        selected = selectedTab == 0,
                        onClick = { selectedTab = 0 },
                        icon = {
                            Icon(
                                painter = painterResource(id = R.drawable.ic_mail),
                                contentDescription = stringResource(R.string.tab_important)
                            )
                        },
                        label = { Text(stringResource(R.string.tab_important)) }
                    )
                    NavigationBarItem(
                        selected = selectedTab == 1,
                        onClick = { selectedTab = 1 },
                        icon = {
                            Icon(
                                painter = painterResource(id = R.drawable.ic_digest),
                                contentDescription = stringResource(R.string.tab_digest)
                            )
                        },
                        label = { Text(stringResource(R.string.tab_digest)) }
                    )
                    NavigationBarItem(
                        selected = selectedTab == 2,
                        onClick = { selectedTab = 2 },
                        icon = {
                            Icon(
                                painter = painterResource(id = R.drawable.ic_settings),
                                contentDescription = stringResource(R.string.tab_settings)
                            )
                        },
                        label = { Text(stringResource(R.string.tab_settings)) }
                    )
                }
            }
        ) { paddingValues ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
            ) {
                when (selectedTab) {
                    0 -> {
                        val mails by mailsViewModel.mails.collectAsState()
                        val isLoading by mailsViewModel.isLoading.collectAsState()
                        MailsListScreen(
                            mails = mails,
                            isLoading = isLoading,
                            onRefresh = { mailsViewModel.loadMails() },
                            onMailClicked = { mail -> mailsViewModel.selectMail(mail) },
                            onStartVoiceSession = { mailsViewModel.startVoiceSession() }
                        )
                    }
                    1 -> {
                        val digest by digestViewModel.digest.collectAsState()
                        val days by digestViewModel.days.collectAsState()
                        val isLoading by digestViewModel.isLoading.collectAsState()
                        DigestScreen(
                            digest = digest,
                            days = days,
                            isLoading = isLoading,
                            onPeriodSelected = { newDays -> digestViewModel.setDays(newDays) },
                            onRefresh = { digestViewModel.loadDigest() },
                            onListenTopic = { topic ->
                                val topicText = "Sprawa: ${topic.title}. ${topic.why}"
                                ttsHelper.speak(topicText)
                            }
                        )
                    }
                    2 -> {
                        val status by settingsViewModel.status.collectAsState()
                        val host by settingsViewModel.host.collectAsState()
                        val port by settingsViewModel.port.collectAsState()
                        val isLoading by settingsViewModel.isLoading.collectAsState()
                        val lang by settingsViewModel.selectedLanguage.collectAsState()
                        val showDisconnect by settingsViewModel.showDisconnectDialog.collectAsState()

                        SettingsScreen(
                            status = status,
                            host = host,
                            port = port,
                            isLoading = isLoading,
                            selectedLanguage = lang,
                            showDisconnectDialog = showDisconnect,
                            onRefresh = { settingsViewModel.refreshStatus() },
                            onLanguageSelected = { newLang -> settingsViewModel.setLanguage(newLang) },
                            onRequestDisconnect = { settingsViewModel.showDisconnectDialog() },
                            onDismissDisconnectDialog = { settingsViewModel.dismissDisconnectDialog() },
                            onConfirmDisconnect = {
                                settingsViewModel.confirmDisconnect {
                                    onDisconnected()
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    // Modal sesji odsłuchiwania głosem
    if (isVoiceActive) {
        VoiceSessionDialog(
            state = voiceState,
            onNext = { mailsViewModel.nextManual() },
            onRepeat = { mailsViewModel.repeatManual() },
            onSkip = { mailsViewModel.skipManual() },
            onStop = {
                ttsHelper.stop()
                speechHelper.stopListening()
                mailsViewModel.stopVoiceSession()
            },
            onRequestMicPermission = { micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO) },
            hasMicPermission = hasMicPermission
        )
    }

    // Dialog uprawnienia mikrofonu
    if (showMicRationale) {
        AlertDialog(
            onDismissRequest = { showMicRationale = false },
            title = { Text(stringResource(R.string.mic_rationale_title)) },
            text = { Text(stringResource(R.string.mic_rationale_desc)) },
            confirmButton = {
                Button(onClick = {
                    showMicRationale = false
                    micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }) {
                    Text(stringResource(R.string.btn_grant_mic))
                }
            },
            dismissButton = {
                TextButton(onClick = { showMicRationale = false }) {
                    Text(stringResource(R.string.btn_cancel))
                }
            }
        )
    }
}
