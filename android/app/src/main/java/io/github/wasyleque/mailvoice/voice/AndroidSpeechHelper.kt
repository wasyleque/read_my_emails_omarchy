package io.github.wasyleque.mailvoice.voice

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * Pomocnik rozpoznawania mowy z mikrofonu przy użyciu SpeechRecognizer.
 * Preferuje rozpoznawanie bezpośrednio na urządzeniu (on-device) od API 31+,
 * nie wymaga i nie zakłada obecności Usług Google Play.
 */
class AndroidSpeechHelper(
    private val context: Context
) {

    private var speechRecognizer: SpeechRecognizer? = null

    val isAvailable: Boolean
        get() = SpeechRecognizer.isRecognitionAvailable(context)

    fun startListening(
        language: String = "pl-PL",
        onListeningStarted: () -> Unit = {},
        onResult: (String) -> Unit,
        onError: (String) -> Unit
    ) {
        if (!isAvailable) {
            onError("Rozpoznawanie mowy nie jest dostępne w Twoim systemie Android.")
            return
        }

        stopListening()

        // Wybór silnika rozpoznawania: on-device na API 31+, gdy dostępny
        val recognizer = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
        ) {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        } else {
            SpeechRecognizer.createSpeechRecognizer(context)
        }

        speechRecognizer = recognizer

        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {
                onListeningStarted()
            }

            override fun onBeginningOfSpeech() {}

            override fun onRmsChanged(rmsdB: Float) {}

            override fun onBufferReceived(buffer: ByteArray?) {}

            override fun onEndOfSpeech() {}

            override fun onError(error: Int) {
                val errorMessage = when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH -> "Nie rozpoznano mowy. Spróbuj powtórzyć."
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Brak sygnału mowy (czas minął)."
                    SpeechRecognizer.ERROR_AUDIO -> "Błąd nagrywania dźwięku."
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Brak uprawnienia do mikrofonu."
                    SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Błąd sieci podczas rozpoznawania mowy."
                    else -> "Błąd rozpoznawania mowy (kod: $error)."
                }
                onError(errorMessage)
            }

            override fun onResults(results: Bundle?) {
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val recognizedText = matches?.firstOrNull().orEmpty()
                onResult(recognizedText)
            }

            override fun onPartialResults(partialResults: Bundle?) {}

            override fun onEvent(eventType: Int, params: Bundle?) {}
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        try {
            recognizer.startListening(intent)
        } catch (e: Exception) {
            onError("Nie udało się uruchomić mikrofonu: ${e.localizedMessage ?: "błąd"}")
        }
    }

    fun stopListening() {
        try {
            speechRecognizer?.stopListening()
            speechRecognizer?.destroy()
        } catch (_: Exception) {}
        speechRecognizer = null
    }

    fun destroy() {
        stopListening()
    }
}
