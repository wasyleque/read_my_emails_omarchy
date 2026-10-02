package io.github.wasyleque.mailvoice.background

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationContentTest {
    private fun mail(sender: String = "Anna Nowak <anna@firma.pl>", subject: String = "Termin", suspicious: Boolean = false) =
        MailBrief("1", sender, subject, 8, "pilne", suspicious)

    @Test
    fun singleImportantShowsNameNotAddress() {
        val n = NotificationContent.forNewImportant(listOf(mail()))
        assertTrue(n.title.contains("Anna Nowak"))
        assertFalse((n.title + n.text).contains("anna@firma.pl"))
    }

    @Test
    fun lockScreenTextHasNoPersonalData() {
        val n = NotificationContent.forNewImportant(listOf(mail(), mail(sender = "Jan <j@x.pl>")))
        assertEquals("Ważne maile: 2", n.publicText)
        assertFalse(n.publicText.contains("Anna"))
    }

    @Test
    fun urlsAreRemoved() {
        val n = NotificationContent.forNewImportant(listOf(mail(subject = "Kliknij https://zlosliwy.example/login teraz")))
        assertFalse(n.text.contains("zlosliwy"))
        assertTrue(n.text.contains("[link pominięty]"))
        assertFalse(NotificationContent.stripUrls("wejdź na www.bank-fake.pl/x lub bank.example.com/login").contains("bank"))
    }

    @Test
    fun suspiciousNeverShowsTheSubject() {
        val n = NotificationContent.forSuspicious(mail(subject = "Pilna weryfikacja hasła", suspicious = true))
        assertFalse(n.text.contains("weryfikacja"))
        assertTrue(n.title.startsWith("⚠"))
        assertEquals("Podejrzana wiadomość", n.publicText)
    }

    @Test
    fun senderWithoutNameFallsBackToAddress() {
        assertEquals("a@b.pl", NotificationContent.senderName("<a@b.pl>"))
        assertEquals("Anna", NotificationContent.senderName("\"Anna\" <a@b.pl>"))
    }

    @Test
    fun longTextIsClipped() {
        val n = NotificationContent.forNewImportant(listOf(mail(subject = "x".repeat(300))))
        assertTrue(n.text.length <= 80)
    }
}
