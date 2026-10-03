package io.github.wasyleque.mailvoice.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AboutLinksTest {
    @Test
    fun onlyTheTwoProjectUrlsAreAllowed() {
        assertTrue(AboutLinks.isAllowed(AboutLinks.PROJECT_URL))
        assertTrue(AboutLinks.isAllowed(AboutLinks.DONATE_URL))
        for (evil in listOf(
            "https://evil.example/login",
            "http://github.com/wasyleque/read_my_emails_omarchy",
            AboutLinks.PROJECT_URL + "/../x",
            "intent://scan/#Intent;end",
            "javascript:alert(1)",
            ""
        )) {
            assertFalse("odrzucić: $evil", AboutLinks.isAllowed(evil))
        }
    }

    @Test
    fun urlsAreHttpsOnTrustedHosts() {
        for (url in listOf(AboutLinks.PROJECT_URL, AboutLinks.DONATE_URL)) {
            assertTrue(url.startsWith("https://"))
        }
        assertTrue(AboutLinks.PROJECT_URL.startsWith("https://github.com/wasyleque/"))
        assertTrue(AboutLinks.DONATE_URL.startsWith("https://www.paypal.com/"))
        assertTrue(AboutLinks.DONATE_URL.contains("business=wasyl%40o2.pl"))
        assertEquals("wasyleque", AboutLinks.AUTHOR)
    }
}
