package io.github.wasyleque.mailvoice

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Straż podpięcia ekranów. Testów Compose nie da się tu uruchomić (brak emulatora), a ViewModel
 * przechodził testy, podczas gdy przycisk „VIP…” na liście nic nie robił (brak wywołania
 * `onVipClicked`) i okno VIP nigdy się nie wyświetlało. Ten test pilnuje, żeby akcje, które
 * ViewModel udostępnia, były faktycznie podpięte w MainActivity.
 */
class UiWiringTest {
    private fun source(path: String): String {
        val candidates = listOf(File("src/main/java/$path"), File("app/src/main/java/$path"))
        return candidates.first { it.exists() }.readText()
    }

    private val main = source("io/github/wasyleque/mailvoice/MainActivity.kt")

    @Test
    fun listScreenReceivesTheVipAction() {
        // lista i szczegóły — dwa miejsca, w których jest przycisk „VIP…”
        val wired = Regex("""onVipClicked\s*=\s*\{[^}]*openVipDialog""").findAll(main).count()
        assertTrue("onVipClicked musi być podpięty zarówno na liście, jak i w szczegółach ($wired)", wired >= 2)
    }

    @Test
    fun vipDialogIsActuallyRendered() {
        assertTrue(main.contains("vipDialogTarget"))
        assertTrue(main.contains("RuleDialogKind.VIP"))
        assertTrue(main.contains("confirmVip"))
        assertTrue(main.contains("dismissVipDialog"))
    }

    @Test
    fun everyViewModelActionOfIgnoreHasAVipCounterpartInTheActivity() {
        for (action in listOf("openIgnoreDialog", "dismissIgnoreDialog", "confirmIgnore")) {
            val vip = action.replace("Ignore", "Vip").replace("confirmVip", "confirmVip")
            assertTrue("brakuje wywołania $vip (lustro $action)", main.contains(vip))
        }
    }
}
