package io.github.wasyleque.mailvoice.voice

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale
import java.util.UUID

/**
 * Pomocnik integracji z systemowym silnikiem syntezy mowy Android (TextToSpeech).
 * Przed wywołaniem syntezy tekst jest ZAWSZE filtrowany za pomocą UrlSanitizer.
 */
class AndroidTtsHelper(
    context: Context,
    private val onInitResult: (success: Boolean, errorMessage: String?) -> Unit = { _, _ -> }
) {

    private var tts: TextToSpeech? = null
    var isInitialized: Boolean = false
        private set

    private var currentOnDoneCallback: (() -> Unit)? = null

    init {
        tts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val ttsInstance = tts
                if (ttsInstance != null) {
                    val plLocale = Locale("pl", "PL")
                    val result = ttsInstance.setLanguage(plLocale)
                    if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                        isInitialized = false
                        onInitResult(
                            false,
                            "Brak danych polskiego głosu w systemie. Doinstaluj polski pakiet mowy w Ustawieniach telefonu: Ułatwienia dostępu → Przetwarzanie tekstu na mowę."
                        )
                    } else {
                        isInitialized = true
                        onInitResult(true, null)
                    }
                }
            } else {
                isInitialized = false
                onInitResult(
                    false,
                    "Nie udało się zainicjalizować silnika syntezy mowy Android."
                )
            }
        }

        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}

            override fun onDone(utteranceId: String?) {
                val callback = currentOnDoneCallback
                currentOnDoneCallback = null
                callback?.invoke()
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                currentOnDoneCallback = null
            }

            override fun onError(utteranceId: String?, errorCode: Int) {
                currentOnDoneCallback = null
            }
        })
    }

    /**
     * Bezpiecznie czyta tekst głosem.
     * Zgodnie z SECURITY.md usuwa wszelkie adresy URL przed syntezą.
     */
    fun speak(text: String, onDone: (() -> Unit)? = null) {
        val safeText = UrlSanitizer.prepareForSpeech(text)
        if (safeText.isBlank()) {
            onDone?.invoke()
            return
        }

        currentOnDoneCallback = onDone
        val utteranceId = UUID.randomUUID().toString()
        val params = Bundle()

        tts?.speak(safeText, TextToSpeech.QUEUE_FLUSH, params, utteranceId)
    }

    fun stop() {
        currentOnDoneCallback = null
        tts?.stop()
    }

    fun shutdown() {
        currentOnDoneCallback = null
        tts?.stop()
        tts?.shutdown()
        tts = null
    }
}
