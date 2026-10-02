package io.github.wasyleque.mailvoice.background

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class EventParserTest {
    @Test
    fun parsesNewImportant() {
        val json = """{"type":"NewImportant","timestamp":"t","data":{"mails":[
            {"id":"a1","sender":"Klient <k@f.pl>","subject":"Pilne","importance":9,"why":"termin","suspicious":false}]}}"""
        val ev = EventParser.parse(json) as ServerEvent.NewImportant
        assertEquals(1, ev.mails.size)
        assertEquals("a1", ev.mails[0].id)
        assertEquals(9, ev.mails[0].importance)
    }

    @Test
    fun suspiciousAlwaysMarkedSuspiciousEvenIfFlagMissing() {
        val json = """{"type":"SuspiciousMail","data":{"mail":{"id":"x","sender":"s","subject":"t"},"reasons":["SPF fail"]}}"""
        val ev = EventParser.parse(json) as ServerEvent.Suspicious
        assertTrue(ev.mail.suspicious)
        assertEquals(listOf("SPF fail"), ev.reasons)
    }

    @Test
    fun parsesReminders() {
        assertEquals(ServerEvent.BeepReminder(2), EventParser.parse("""{"type":"BeepReminder","data":{"count":2}}"""))
        assertEquals(ServerEvent.AskReminder(3), EventParser.parse("""{"type":"AskReminder","data":{"count":3}}"""))
    }

    @Test
    fun garbageNeverThrows() {
        assertNull(EventParser.parse("to nie jest json"))
        assertNull(EventParser.parse("""{"type":"Nieznany"}"""))
        assertNull(EventParser.parse("""{"type":"NewImportant","data":{"mails":[]}}"""))
        assertNull(EventParser.parse("""{"type":"NewImportant","data":{"mails":[{"sender":"bez id"}]}}"""))
        assertNull(EventParser.parse("""{"type":"SuspiciousMail","data":{}}"""))
    }
}
