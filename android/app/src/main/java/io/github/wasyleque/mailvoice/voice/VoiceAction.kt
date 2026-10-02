package io.github.wasyleque.mailvoice.voice

/**
 * Zdefiniowane akcje komend głosowych obsługiwanych przez MailVoice.
 */
enum class VoiceAction {
    NEXT,
    REPEAT,
    SKIP,
    STOP,
    YES,
    NO,
    LOUDER,
    QUIETER,
    DIGEST,
    CONTACT,
    SEARCH,
    UNKNOWN;

    companion object {
        fun fromString(action: String?): VoiceAction {
            return when (action?.trim()?.lowercase()) {
                "next" -> NEXT
                "repeat" -> REPEAT
                "skip" -> SKIP
                "stop" -> STOP
                "yes" -> YES
                "no" -> NO
                "louder" -> LOUDER
                "quieter" -> QUIETER
                "digest" -> DIGEST
                "contact" -> CONTACT
                "search" -> SEARCH
                else -> UNKNOWN
            }
        }
    }
}
