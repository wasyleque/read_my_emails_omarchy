package io.github.wasyleque.mailvoice.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UrlSanitizerTest {

    @Test
    fun testSanitizeHttpAndHttpsUrls() {
        val input = "Zobacz naszą ofertę na https://example.com/promo oraz http://insecure.site.pl/test?id=123"
        val sanitized = UrlSanitizer.sanitizeUrls(input)

        assertFalse(sanitized.contains("https://"))
        assertFalse(sanitized.contains("http://"))
        assertFalse(sanitized.contains("example.com"))
        assertFalse(sanitized.contains("insecure.site.pl"))
        assertTrue(sanitized.contains("[link pominięty]"))
    }

    @Test
    fun testSanitizeWwwAndDomains() {
        val input = "Napisz do nas lub wejdź na www.bank-logowanie.pl/panel."
        val sanitized = UrlSanitizer.sanitizeUrls(input)

        assertFalse(sanitized.contains("www.bank-logowanie.pl"))
        assertTrue(sanitized.contains("[link pominięty]"))
    }

    @Test
    fun testPrepareForSpeechRemovesBracketsAndDefangedTags() {
        val serverText = "Przesłano nową fakturę VAT [link pominięty] do opłacenia."
        val speechText = UrlSanitizer.prepareForSpeech(serverText)

        assertFalse(speechText.contains("["))
        assertFalse(speechText.contains("]"))
        assertTrue(speechText.contains("odnośnik pominięty"))
        assertEquals("Przesłano nową fakturę VAT odnośnik pominięty do opłacenia.", speechText)
    }

    @Test
    fun testPrepareForSpeechWithRawUrlReplacesWithSpokenPhrase() {
        val rawInput = "Kliknij tutaj https://zlosliwy-link.xyz/virus aby odebrać nagrodę."
        val speechText = UrlSanitizer.prepareForSpeech(rawInput)

        assertFalse(speechText.contains("https://"))
        assertFalse(speechText.contains("zlosliwy-link.xyz"))
        assertFalse(speechText.contains("["))
        assertTrue(speechText.contains("odnośnik pominięty"))
    }

    @Test
    fun testCleanTextWithoutUrlsRemainsUnchanged() {
        val plain = "Cześć Janie, spotkajmy się jutro o 10 w biurze."
        val result = UrlSanitizer.prepareForSpeech(plain)

        assertEquals(plain, result)
    }
}
